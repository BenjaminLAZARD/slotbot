# Secret *containers* only. Values are added by hand (`gcloud secrets versions add`, see
# deploy/gcp.md) so they never land in this repository; the job token is read back below because
# the scheduler and the budget push must send it.
locals {
  secrets = {
    database_url   = "slotbot-database-url"
    secret_key     = "slotbot-secret-key"
    job_token      = "slotbot-job-token"
    resend_api_key = "slotbot-resend-api-key"
  }
}

resource "google_secret_manager_secret" "s" {
  for_each  = local.secrets
  secret_id = each.value
  replication {
    auto {}
  }
}

data "google_secret_manager_secret_version" "job_token" {
  secret = google_secret_manager_secret.s["job_token"].id
}
