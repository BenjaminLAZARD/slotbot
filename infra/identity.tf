# The bot's own identity: Cloud Run runs as it, and it signs the calls of Cloud Tasks, Cloud
# Scheduler and the Pub/Sub budget push. Calendars are shared with its email.
resource "google_service_account" "slotbot" {
  account_id   = "slotbot"
  display_name = "SlotBot"
}

locals {
  slotbot_roles = [
    "roles/billing.projectManager", # kill switch: detach billing at the budget
    "roles/cloudtasks.enqueuer",    # schedule races
    "roles/cloudtasks.taskDeleter", # cancel them
    "roles/run.invoker",            # be allowed to call the (private) service
    "roles/secretmanager.secretAccessor",
  ]
}

resource "google_project_iam_member" "slotbot" {
  for_each = toset(local.slotbot_roles)
  project  = var.project
  role     = each.value
  member   = google_service_account.slotbot.member
}

# Cloud Tasks / Scheduler mint tokens "as" the bot when the bot creates them.
resource "google_service_account_iam_member" "slotbot_acts_as_itself" {
  service_account_id = google_service_account.slotbot.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.slotbot.member
}

# Pub/Sub's own agent signs the budget push as the bot (needed on projects created before 2021).
resource "google_service_account_iam_member" "pubsub_signs_as_slotbot" {
  service_account_id = google_service_account.slotbot.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
