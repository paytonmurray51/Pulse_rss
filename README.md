# Pulse — AI-Curated RSS Reader

A self-hosted RSS and YouTube feed reader that uses Claude Haiku to score, summarize, and filter articles based on your interests. The more you interact (likes, dislikes, saves), the better it gets at surfacing what you actually want to read.

## What it does

- **Aggregates** RSS feeds and YouTube channels into a single ranked feed
- **Scores** every article 0-10 using Claude Haiku (relevance to your interests × quality)
- **Summarizes** articles in 1-2 sentences so you can decide what's worth opening
- **Filters** spam, clickbait, and blocked topics/sources before they reach your feed
- **Learns** from your likes, dislikes, and reading behavior to improve scoring over time
- **Self-hosts** cleanly on GCP Cloud Run with zero config once deployed

## Architecture

```
                          ┌─────────────────────────┐
                          │      Cloud Run (GCP)     │
  Browser ──HTTPS──►      │  ┌───────────────────┐  │
                          │  │   FastAPI + React  │  │
                          │  │   (single container│  │
                          │  └────────┬──────────-┘  │
                          │           │               │
                          │  ┌────────▼──────────┐   │
                          │  │   APScheduler     │   │
                          │  │ (feed refresh job)│   │
                          │  └────────┬──────────┘   │
                          └───────────│───────────────┘
                                      │
             ┌────────────────────────┼──────────────────────┐
             │                        │                      │
     ┌───────▼──────┐      ┌──────────▼──────────┐  ┌───────▼──────┐
     │  RSS / YouTube│      │  Claude Haiku (API)  │  │  Cloud SQL   │
     │  feeds (HTTP) │      │  (score + summarize) │  │  PostgreSQL  │
     └───────────────┘      └─────────────────────-┘  └──────────────┘
```

## Prerequisites

- GCP project with billing enabled
- Cloud SQL PostgreSQL instance (existing)
- Artifact Registry repository (existing, e.g. `pulse`)
- GCS bucket for Terraform state (must be globally unique — prefix with your project ID)
- Service account with roles: Cloud Run Admin, Cloud SQL Client, Secret Manager Admin, Artifact Registry Writer, Storage Admin
- Anthropic API key

## One-time GCP setup

```bash
export PROJECT_ID=utopian-hearth-161821
export REGION=us-central1

# Create Terraform state bucket (name must match the backend block in infra/main.tf)
gsutil mb -p $PROJECT_ID -l $REGION gs://${PROJECT_ID}-pulse-tfstate
gsutil versioning set on gs://${PROJECT_ID}-pulse-tfstate
```

If you use a different bucket name, update the `backend "gcs"` block in `infra/main.tf` to match —
Terraform backends can't read variables, so it has to be hardcoded.

## GitHub repository setup

Create a repository and add the following **Secrets** (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | JSON key for the GCP service account |
| `GCP_PROJECT_ID` | Your GCP project ID |
| `CLOUD_SQL_INSTANCE_NAME` | Cloud SQL instance name (not connection name) |
| `CLOUD_SQL_CONNECTION_NAME` | `project:region:instance` format |
| `ARTIFACT_REGISTRY_REPO` | Artifact Registry repo name (e.g. `pulse`) |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `PULSE_DB_PASSWORD` | Password for the `pulse_user` database user |
| `OWNER_EMAIL` | Your Google address — auto-invited and made admin |
| `GOOGLE_CLIENT_ID` | OAuth client ID (`...apps.googleusercontent.com`) |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret (`GOCSPX-...`) |
| `SESSION_SECRET` | `openssl rand -base64 48` — changing it signs everyone out |
| `RESEND_API_KEY` | Resend API key for suggestion emails |
| `PUBLIC_URL` | Service URL, e.g. `https://pulse-xxxx.run.app` (no trailing slash) |

## First deploy

```bash
git clone https://github.com/YOUR_ORG/pulse.git
cd pulse
git push origin main   # triggers GitHub Actions deploy
```

The workflow will:
1. Build the multi-stage Docker image and push to Artifact Registry
2. Run `terraform apply` to provision Cloud SQL DB + user, Secret Manager secrets, service account, and Cloud Run service

## Accounts and sign-in

Pulse is invite-only and signs in with Google. The owner is created
automatically on first boot from `OWNER_EMAIL`; everyone else is invited from
**Settings → Members**.

Each member gets their own interests, score threshold, blocks, saved items and
**their own AI scores** — relevance depends on whose interests are being
matched, so an article can be a 9 for one person and a 2 for another.

### Creating the Google OAuth client

1. Go to console.cloud.google.com → **APIs & Services → OAuth consent screen**
   - User type **External**, publishing status **Testing** is fine for a family
   - Add each family Gmail address under **Test users**
2. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorised redirect URI: `https://YOUR-SERVICE-URL/api/auth/callback`
     (must match `PUBLIC_URL` exactly — no trailing slash)
3. Copy the client ID and client secret into GitHub Secrets

### Scoring costs

Scoring runs **on request**: pressing Refresh fetches new articles and scores
them for whoever pressed it. Nobody is charged for a family member who never
signs in. An admin can additionally enable a scheduled sync in
**Settings → Scheduled sync**, which scores for everyone seen in the last 14
days.

## Suggestions

Any member can send a suggestion from **Settings → Suggest an improvement**.
It is stored first and emailed to `OWNER_EMAIL` through Resend, so a mail
outage never loses feedback — failures show as "not emailed" in the admin
inbox. `onboarding@resend.dev` works without domain verification; set
`RESEND_FROM` once you verify your own domain.

## First use

1. Open the service URL from Terraform output
2. Go to **Settings** → add your interests → Save
3. Go to **Sources** → add RSS feeds or YouTube channels → Save
4. Click **Refresh** in the top bar to trigger the first fetch + AI scoring
5. Your ranked feed appears on the home page

## YouTube channels

Paste any of these URL formats:
- `https://www.youtube.com/@channelhandle`
- `https://www.youtube.com/channel/UCxxxxxxx`
- `https://www.youtube.com/user/username`

The app will resolve the channel to its RSS feed URL automatically.

## How the feedback loop works

Every time you click **Refresh**, the AI re-reads your recent interactions:

- **Liked** articles → Claude scores similar content higher
- **Disliked** articles → Claude scores similar content lower
- **Saved + opened 2+ times** → treated as implicit like
- **Blocked sources/topics** → excluded before AI ever sees them

There's no persistent memory between runs — Claude recalibrates from scratch each refresh using your latest behavior. This keeps the model honest and prevents drift.

## Local development

```bash
# Backend
cd app/backend
pip install -r requirements.txt
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/pulse" \
ANTHROPIC_API_KEY="sk-ant-..." \
uvicorn main:app --reload --port 8080

# Frontend (separate terminal)
cd app/frontend
npm install
npm run dev   # proxies /api to localhost:8080
```

Visit `http://localhost:5173`.

## Moving to Kubernetes later

The Docker image is Kubernetes-ready. When you outgrow Cloud Run:

1. Deploy the image as a `Deployment` with 1+ replicas
2. Add a Cloud SQL Auth Proxy sidecar for database connectivity
3. Mount `ANTHROPIC_API_KEY` and `DATABASE_URL` from Kubernetes Secrets
4. The APScheduler runs inside the FastAPI process — for multi-replica deployments, consider extracting the scheduler to a dedicated worker pod to avoid duplicate refreshes
