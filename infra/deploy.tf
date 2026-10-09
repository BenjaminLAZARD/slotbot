# Automatic deploys from GitHub Actions without any stored key (Workload Identity Federation):
# GitHub signs a token saying "this run is repo X, branch main"; Google trusts that issuer for
# this one repository and lets the run act as the deployer account below.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "slotbot"
  display_name                       = "slotbot repository"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "slotbot-deployer"
  display_name = "slotbot deployer (GitHub Actions)"
}

resource "google_service_account_iam_member" "github_is_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

locals {
  deployer_roles = [
    "roles/run.sourceDeveloper",               # gcloud run deploy --source: upload, build, deploy
    "roles/serviceusage.serviceUsageConsumer", # use the project's APIs
    "roles/logging.viewer",                    # stream the build log
  ]
  # A deploy runs the build as the default compute account and the service as the bot.
  deployer_acts_as = {
    slotbot = google_service_account.slotbot.name
    builder = "projects/${var.project}/serviceAccounts/${data.google_project.this.number}-compute@developer.gserviceaccount.com"
  }
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(local.deployer_roles)
  project  = var.project
  role     = each.value
  member   = google_service_account.deployer.member
}

resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each           = local.deployer_acts_as
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}

output "github_variables" {
  description = "Repository variables the deploy workflow reads (not secrets)."
  value = {
    GCP_PROJECT      = var.project
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER     = google_service_account.deployer.email
  }
}
