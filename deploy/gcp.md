# Deploying on Google Cloud (scale to zero)

> Run end to end on 2026-10-08 (see HISTORY.md, v0.7). The commands below are the ones that worked,
> with the fixes found on the way.

```
Cloud Scheduler (hourly) ──► POST /jobs/sync ─────┐
Cloud Tasks (opens−5min) ──► POST /jobs/race/{id} ─┼─► Cloud Run "slotbot" (0..1 instance) ─► Neon Postgres
Budget ─► Pub/Sub push ────► POST /jobs/budget ────┘        └─► Google Calendar, Nominatim, Madrid site, Resend
You ─► gcloud run services proxy ─► UI
```

- **Cloud Run** runs the container only while a request is in flight. A race is one request held open
  by Cloud Tasks (≤ 30 min), so the CPU stays allocated for the 1-second polling.
- **Cloud Tasks** delivers a one-off HTTP call at an exact time (up to 30 days ahead): this is the
  "trigger 5 minutes before opening".
- **Cloud Scheduler** is cron-as-a-service: the hourly calendar scan.
- **Budget + Pub/Sub** is the spending cap: Google only *alerts* on budgets, so the app itself
  detaches billing from the project when spend reaches the budget (`/jobs/budget`).
- **Region** `europe-southwest1` is Madrid (lowest latency to the booking site). Cloud Tasks is not
  offered there, so the queue (and, to keep them together, the scheduler job) live in `europe-west1`.
- Cost at personal volume: €0 so far (free tiers); a billing account is still required.

Always pass `--project`: if your gcloud default project is another one (e.g. work), commands
silently land there. Budgets also need `--billing-project $PROJECT` when your
application-default credentials carry another quota project.

## 1. Project, APIs, identity

```bash
PROJECT=your-project-id
REGION=europe-southwest1        # Cloud Run
TASKS_REGION=europe-west1       # Cloud Tasks + Cloud Scheduler
SA=slotbot@$PROJECT.iam.gserviceaccount.com
NUM=$(gcloud projects describe $PROJECT --format 'value(projectNumber)')

gcloud services enable --project $PROJECT run.googleapis.com cloudtasks.googleapis.com \
  cloudscheduler.googleapis.com calendar-json.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com pubsub.googleapis.com \
  billingbudgets.googleapis.com cloudbilling.googleapis.com
gcloud iam service-accounts create slotbot --project $PROJECT   # skip if made for local dev
for role in roles/cloudtasks.enqueuer roles/cloudtasks.taskDeleter roles/run.invoker \
            roles/secretmanager.secretAccessor roles/billing.projectManager; do
  gcloud projects add-iam-policy-binding $PROJECT --member serviceAccount:$SA --role $role
done
# Cloud Tasks and Cloud Scheduler sign their calls as this same account:
gcloud iam service-accounts add-iam-policy-binding $SA --project $PROJECT \
  --member serviceAccount:$SA --role roles/iam.serviceAccountUser
# Pub/Sub push signs as it too; projects created before 2021 must allow the Pub/Sub agent to:
gcloud iam service-accounts add-iam-policy-binding $SA --project $PROJECT \
  --member serviceAccount:service-$NUM@gcp-sa-pubsub.iam.gserviceaccount.com \
  --role roles/iam.serviceAccountTokenCreator
```

`roles/billing.projectManager` is what lets the kill switch detach billing. Your calendar is already
shared with `$SA` if you set up local dev; Cloud Run runs *as* that account, so no key file is needed.

## 2. Database (Neon)

Create a project at <https://neon.tech> (Frankfurt `aws-eu-central-1` is closest). Use the
**direct** endpoint, not the pooled one (host without `-pooler`): the pooler (PgBouncer in
transaction mode) hands out shared sessions, which broke `pg_restore` (empty `search_path`) and
does not suit asyncpg's prepared statements. Rewrite the URL for asyncpg:
`postgresql+asyncpg://USER:PASSWORD@HOST/DB?ssl=require` (asyncpg takes `ssl=`, not `sslmode=`).

Moving local data across (keep the same `SLOTBOT_SECRET_KEY`: it decrypts the stored credentials):

```bash
docker compose exec -T db pg_dump -U slotbot -Fc slotbot > /tmp/slotbot.dump
pg_restore --no-owner --no-acl -d "postgresql://USER:PASSWORD@HOST/DB?sslmode=require" /tmp/slotbot.dump
```

## 3. Secrets

```bash
printf '%s' "postgresql+asyncpg://...?ssl=require" | gcloud secrets create slotbot-database-url --project $PROJECT --data-file=-
printf '%s' "$LOCAL_SECRET_KEY"     | gcloud secrets create slotbot-secret-key     --project $PROJECT --data-file=-
printf '%s' "$(openssl rand -hex 24)" | gcloud secrets create slotbot-job-token    --project $PROJECT --data-file=-
printf '%s' "$RESEND_API_KEY"       | gcloud secrets create slotbot-resend-api-key --project $PROJECT --data-file=-
```

## 4. Queue

```bash
gcloud tasks queues create slotbot --project $PROJECT --location $TASKS_REGION --max-attempts 1
```

`--max-attempts 1`: a race is not safely retryable blindly (it might have booked); the app records
failures and offers a manual retry instead.

## 5. Deploy

```bash
gcloud run deploy slotbot --project $PROJECT --source . --region $REGION --service-account $SA \
  --no-allow-unauthenticated --min-instances 0 --max-instances 1 --timeout 3600 \
  --set-secrets SLOTBOT_DATABASE_URL=slotbot-database-url:latest,SLOTBOT_SECRET_KEY=slotbot-secret-key:latest,SLOTBOT_JOB_TOKEN=slotbot-job-token:latest,SLOTBOT_RESEND_API_KEY=slotbot-resend-api-key:latest \
  --set-env-vars SLOTBOT_TRIGGERS=cloudtasks,SLOTBOT_CLOUD_TASKS_QUEUE=projects/$PROJECT/locations/$TASKS_REGION/queues/slotbot,SLOTBOT_GCP_PROJECT=$PROJECT,SLOTBOT_MADRID_OPENS_AT=00:00
URL=https://slotbot-$NUM.$REGION.run.app
gcloud run services update slotbot --project $PROJECT --region $REGION --update-env-vars SLOTBOT_PUBLIC_URL=$URL
```

- `--source .` builds the root `Dockerfile` (last stage `prod`: API + built UI) with Cloud Build;
  `.gcloudignore` keeps `.env`, `secrets/`, `.git` and build caches out of the upload.
- `--max-instances 1`: one bot, never two copies racing for the same slot.
- Migrations (`alembic upgrade head`) run at each container start.
- Health check: `GET /health`. Not `/healthz`: Cloud Run's front end reserves that path (404).
- Re-deploy after a code change: the same `gcloud run deploy` line (secrets and env are kept).

## 6. Hourly calendar scan

```bash
gcloud scheduler jobs create http slotbot-sync --project $PROJECT --location $TASKS_REGION \
  --schedule "7 * * * *" --time-zone Europe/Madrid \
  --uri $URL/jobs/sync --http-method POST \
  --oidc-service-account-email $SA --oidc-token-audience $URL \
  --headers X-Job-Token=$(gcloud secrets versions access latest --secret slotbot-job-token --project $PROJECT)
gcloud scheduler jobs run slotbot-sync --project $PROJECT --location $TASKS_REGION   # try it now
```

Two layers of auth on every machine call: the OIDC token gets the request past Cloud Run's IAM
(`--no-allow-unauthenticated`), and the job token proves it is one of *our* jobs.

## 7. Spending cap (budget + kill switch)

```bash
gcloud pubsub topics create slotbot-budget --project $PROJECT
gcloud billing budgets create --billing-account $BILLING_ACCOUNT --billing-project $PROJECT \
  --display-name "slotbot cap 10 EUR" --budget-amount 10EUR --filter-projects projects/$PROJECT \
  --threshold-rule percent=0.1 --threshold-rule percent=0.5 --threshold-rule percent=1.0 \
  --notifications-rule-pubsub-topic projects/$PROJECT/topics/slotbot-budget
TOKEN=$(gcloud secrets versions access latest --secret slotbot-job-token --project $PROJECT)
gcloud pubsub subscriptions create slotbot-budget-push --project $PROJECT --topic slotbot-budget \
  --push-endpoint "$URL/jobs/budget?token=$TOKEN" \
  --push-auth-service-account $SA --push-auth-token-audience $URL \
  --ack-deadline 60 --message-retention-duration 1h --expiration-period never
```

- Threshold rules send **emails** to the billing account's admins (€1, €5, €10 here).
- Independently of thresholds, Google publishes the budget's status to the topic several times a
  day; `/jobs/budget` detaches billing once `costAmount ≥ budgetAmount`. Billing data lags by hours,
  so the cap is approximate. Detaching billing stops every paid service of the project (the bot
  included); re-link the billing account in the console to resume.
- Pub/Sub push cannot set headers, hence the job token in the query string; the audience is pinned
  to the bare service URL because Cloud Run rejects an audience that carries the query.
- Test without risk (below the cap):
  `gcloud pubsub topics publish slotbot-budget --project $PROJECT --message '{"costAmount":0.5,"budgetAmount":10,"currencyCode":"EUR"}'`
  then look for `budget notification: 0.50 / 10.00 EUR` in the service logs.

## 8. Keep the image registry small

Each deploy pushes an image to Artifact Registry (storage beyond 0.5 GB is billed):

```bash
cat > /tmp/cleanup.json <<'EOF'
[{"name": "keep-last-2", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
 {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"tagState": "ANY", "olderThan": "1d"}}]
EOF
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --project $PROJECT \
  --location $REGION --policy /tmp/cleanup.json --no-dry-run
```

## 9. Sign-in, then going public

1. **OAuth client** (console only for projects without an organization):
   <https://console.cloud.google.com/auth/overview?project=$PROJECT> → *Get started* (app name,
   support email, audience **External**) → *Clients* → *Create client* → *Web application*,
   authorized JavaScript origins `$URL` and `http://localhost:5173` → copy the Client ID (public,
   not a secret) → *Audience* → *Publish app* (only the basic `openid email profile` scopes: no review).
2. **Deploy with sign-in on**, still private:
   ```bash
   gcloud run services update slotbot --project $PROJECT --region $REGION \
     --update-env-vars SLOTBOT_GOOGLE_CLIENT_ID=$CLIENT_ID,SLOTBOT_ALLOWED_EMAILS=you@gmail.com
   ```
   Commas separate invites, so add friends with `--env-vars-file` or the console. The first address
   owns the profiles created before sign-in existed.
3. **Go public**: `/jobs/*` must now check Google's token itself, then Cloud Run stops checking:
   ```bash
   gcloud run services update slotbot --project $PROJECT --region $REGION --update-env-vars SLOTBOT_JOB_CALLER=$SA
   gcloud run services add-iam-policy-binding slotbot --project $PROJECT --region $REGION \
     --member allUsers --role roles/run.invoker
   ```
   Then check: `gcloud scheduler jobs run slotbot-sync …` and the budget test message still answer 200.
   Back to private: `gcloud run services remove-iam-policy-binding … --member allUsers --role roles/run.invoker`.

Strangers then see the landing page and `401` on the API, which is rejected from the signed cookie
alone (no database read, so junk traffic never wakes Neon). `max-instances 1` and the €10 kill
switch bound the worst case.

## 10. Open the UI (while private)

The service is private (no login screen yet; that comes with multi-user). Open it through an
authenticated local proxy:

```bash
gcloud run services proxy slotbot --project $PROJECT --region $REGION --port 8090   # http://localhost:8090
```

Stop the local `docker compose` API when the cloud takes over: two bots would race each other for
the same slot (the `db` container can stay).

## Pause / resume

`deploy/bot.sh pause` pauses the hourly scan and the race queue (Cloud Run only runs when called, so
the bot is then fully stopped and costs nothing); `resume` restarts both, and queued races that
came due meanwhile fire at once. `status` shows both and the queued races; `ui` opens the proxy.

## Logs

```bash
gcloud logging read 'resource.labels.service_name="slotbot"' --project $PROJECT --freshness 1h --limit 50 \
  --format 'value(timestamp,httpRequest.requestUrl,httpRequest.status,textPayload)'
```
