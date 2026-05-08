variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "cloud_sql_instance_name" {
  description = "Name of the existing Cloud SQL instance"
  type        = string
}

variable "cloud_sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance)"
  type        = string
}

variable "artifact_registry_repo" {
  description = "Artifact Registry repository name (existing)"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database password for pulse_user"
  type        = string
  sensitive   = true
}

variable "refresh_interval_minutes" {
  description = "How often to refresh feeds (minutes)"
  type        = number
  default     = 30
}
