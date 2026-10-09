# infra: the Google Cloud setup as code (OpenTofu)

Everything slotbot runs on in Google Cloud is described here and applied with
[OpenTofu](https://opentofu.org) (the open-source fork of Terraform: same language, same commands).
You change a `.tf` file or `terraform.tfvars`, `plan` shows exactly what would change in the cloud,
`apply` does it. Nothing else should change these resources (no `gcloud run services update`),
otherwise the next `plan` shows the difference ("drift") and `apply` puts it back.

```bash
infra/tofu.sh plan     # what would change (nothing, normally)
infra/tofu.sh apply    # do it, after showing the plan and asking "yes"
infra/tofu.sh output   # values GitHub Actions needs
```

`tofu.sh` runs `tofu` as your active gcloud account (`gcloud auth login`); install OpenTofu with
`brew install opentofu`.

| File | What it holds |
|---|---|
| `versions.tf` | provider, state location, quota project |
| `variables.tf`, `terraform.tfvars` | project, regions, billing account, **service settings** (`env`), `public` |
| `apis.tf` | the Google APIs slotbot uses (never switched off by OpenTofu) |
| `identity.tf` | the bot's service account and its permissions |
| `secrets.tf` | Secret Manager secrets (containers only, see below) |
| `service.tf` | the Cloud Run service: scaling, timeout, env, secrets; public access when `public = true` |
| `jobs.tf` | the race queue (Cloud Tasks) and the hourly scan (Cloud Scheduler) |
| `budget.tf` | €10 budget, its Pub/Sub topic and the push to the kill switch |
| `registry.tf` | the image repository and its cleanup policy |
| `deploy.tf` | keyless deploys from GitHub Actions (Workload Identity Federation) |

## What is deliberately *not* here

- **Secret values.** OpenTofu creates the secrets; values are added by hand
  (`printf '%s' "$VALUE" | gcloud secrets versions add slotbot-… --data-file=-`) so they never enter
  git. The job token is read back (the scheduler and the budget push must send it), so it is in the
  state file: the state bucket is private and only project owners can read it.
- **The container image.** Deploys own it (GitHub Actions, or `gcloud run deploy --source .`).
- **The race tasks.** One per booking, created and deleted by the app at runtime.
- **Pause / resume** of the scan and the queue: `deploy/bot.sh` (ignored by OpenTofu).
- **The Google sign-in OAuth client**: console only for projects without an organization.
- **Neon** (the database) and **Resend** (email): other providers, configured in their consoles.

## State

OpenTofu remembers which real resource each block manages in a *state file*, kept in the private,
versioned bucket `gs://divine-camera-228017-tofu-state` (a few KB: effectively free). That bucket is
the one thing created outside this code (chicken and egg):

```bash
gcloud storage buckets create gs://$PROJECT-tofu-state --project $PROJECT --location europe-southwest1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$PROJECT-tofu-state --versioning
```

The resources were first created by hand with gcloud (deploy/gcp.md, 2026-10-08) and adopted on
2026-10-09 with `import` blocks: 32 imported with zero changes.
