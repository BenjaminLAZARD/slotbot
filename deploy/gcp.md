# Deploying on Google Cloud (scale to zero)

> Written 2026-10-07, **not yet run end to end**. Expect small fixes on the first deploy; record
> them in HISTORY.md.

```
Cloud Scheduler (daily) ─► POST /jobs/sync ─┐
Cloud Tasks (opens−5min) ─► POST /jobs/race/{id} ─► Cloud Run "slotbot" (min instances 0) ─► Neon Postgres
You ─► gcloud run services proxy ─► UI                  └─► Google Calendar, Nominatim, Madrid site
```

- **Cloud Run** runs the container only while a request is in flight. A race is one request held open
  by Cloud Tasks (≤ 30 min), so the CPU stays allocated for the 1-second polling.
- **Cloud Tasks** delivers a one-off HTTP call at an exact time (up to 30 days ahead): this is the
  "trigger 5 minutes before opening".
- **Cloud Scheduler** is cron-as-a-service for the daily sync.
- **Region** `europe-southwest1` is Madrid: lowest latency to the booking site during the race.
- Expected cost at personal volume: ~€0 (free tiers), but a billing account is required.

## 1. Project, APIs, identity

```bash
PROJECT=your-project-id
REGION=europe-southwest1
SA=slotbot@$PROJECT.iam.gserviceaccount.com

gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudtasks.googleapis.com cloudscheduler.googleapis.com \
  calendar-json.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud iam service-accounts create slotbot --display-name slotbot   # skip if you made it for local dev
for role in roles/cloudtasks.enqueuer roles/cloudtasks.taskDeleter roles/run.invoker roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA --role $role
done
# Cloud Tasks signs requests as the same service account:
gcloud iam service-accounts add-iam-policy-binding $SA --member serviceAccount:$SA --role roles/iam.serviceAccountUser
```

Your calendar is already shared with `$SA` if you set up local dev; the Cloud Run service runs *as*
that account, so no key file is needed in the cloud.

## 2. Database (Neon)

Create a project at <https://neon.tech> (region: Frankfurt `aws-eu-central-1` is closest). Take the
connection string and rewrite it for asyncpg:
`postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require` (asyncpg uses `ssl=`, not `sslmode=`).

## 3. Secrets

```bash
printf '%s' "postgresql+asyncpg://...?ssl=require" | gcloud secrets create slotbot-database-url --data-file=-
printf '%s' "$(cd backend && uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  | gcloud secrets create slotbot-secret-key --data-file=-
printf '%s' "$(openssl rand -hex 24)" | gcloud secrets create slotbot-job-token --data-file=-
```

Reuse your local `SLOTBOT_SECRET_KEY` instead if you migrate local data (it decrypts stored credentials).

## 4. Queue

```bash
gcloud tasks queues create slotbot --location $REGION --max-attempts 1
```

`--max-attempts 1`: a race is not safely retryable blindly (it might have booked); the app records
failures and offers a manual retry instead.

## 5. Deploy

```bash
gcloud run deploy slotbot --source . --region $REGION --service-account $SA \
  --no-allow-unauthenticated --min-instances 0 --max-instances 2 --timeout 3600 \
  --set-secrets SLOTBOT_DATABASE_URL=slotbot-database-url:latest,SLOTBOT_SECRET_KEY=slotbot-secret-key:latest,SLOTBOT_JOB_TOKEN=slotbot-job-token:latest \
  --set-env-vars SLOTBOT_TRIGGERS=cloudtasks,SLOTBOT_CLOUD_TASKS_QUEUE=projects/$PROJECT/locations/$REGION/queues/slotbot,SLOTBOT_CONTACT_EMAIL=you@example.com
URL=$(gcloud run services describe slotbot --region $REGION --format 'value(status.url)')
gcloud run services update slotbot --region $REGION --update-env-vars SLOTBOT_PUBLIC_URL=$URL
```

`--source .` builds the root `Dockerfile` (last stage `prod`: API + built UI) with Cloud Build.
Migrations run at container start.

## 6. Daily sync

```bash
gcloud scheduler jobs create http slotbot-sync --location $REGION \
  --schedule "7 8 * * *" --time-zone Europe/Madrid \
  --uri $URL/jobs/sync --http-method POST \
  --oidc-service-account-email $SA --oidc-token-audience $URL \
  --headers X-Job-Token=$(gcloud secrets versions access latest --secret slotbot-job-token)
```

## 7. Open the UI

The service is private (no login screen yet; that comes with multi-user). Open it through an
authenticated local proxy:

```bash
gcloud run services proxy slotbot --region $REGION --port 8080   # then http://localhost:8080
```
