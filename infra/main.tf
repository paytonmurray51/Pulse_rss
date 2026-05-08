terraform {
  required_version = ">= 1.8.0"

  backend "gcs" {
    bucket = "pulse-terraform-state"
    prefix = "terraform/state"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repo}/pulse:${var.image_tag}"
}

# ─── Database ────────────────────────────────────────────────────────────────

resource "google_sql_database" "pulse" {
  name     = "pulse"
  instance = var.cloud_sql_instance_name
}

resource "google_sql_user" "pulse" {
  name     = "pulse_user"
  instance = var.cloud_sql_instance_name
  password = var.db_password
}

# ─── Secrets ─────────────────────────────────────────────────────────────────

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "pulse-anthropic-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "pulse-db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

# ─── Service account ─────────────────────────────────────────────────────────

resource "google_service_account" "pulse_run" {
  account_id   = "pulse-cloudrun"
  display_name = "Pulse Cloud Run Service Account"
}

resource "google_project_iam_member" "pulse_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.pulse_run.email}"
}

resource "google_secret_manager_secret_iam_member" "anthropic_accessor" {
  secret_id = google_secret_manager_secret.anthropic_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pulse_run.email}"
}

resource "google_secret_manager_secret_iam_member" "db_password_accessor" {
  secret_id = google_secret_manager_secret.db_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pulse_run.email}"
}

# ─── Cloud Run ───────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "pulse" {
  name     = "pulse"
  location = var.region

  template {
    service_account = google_service_account.pulse_run.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.cloud_sql_connection_name]
      }
    }

    containers {
      image = local.image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "CLOUD_SQL_CONNECTION_NAME"
        value = var.cloud_sql_connection_name
      }

      env {
        name  = "DB_USER"
        value = "pulse_user"
      }

      env {
        name  = "DB_NAME"
        value = "pulse"
      }

      env {
        name  = "REFRESH_INTERVAL_MINUTES"
        value = tostring(var.refresh_interval_minutes)
      }

      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      liveness_probe {
        http_get {
          path = "/api/health"
        }
        initial_delay_seconds = 10
        period_seconds        = 30
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.anthropic_accessor,
    google_secret_manager_secret_iam_member.db_password_accessor,
    google_project_iam_member.pulse_sql_client,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.pulse.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
