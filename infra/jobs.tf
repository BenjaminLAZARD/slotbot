# What wakes the bot: the race queue (one task per booking, created by the app) and the hourly scan.
resource "google_cloud_tasks_queue" "races" {
  name     = "slotbot"
  location = var.tasks_region

  retry_config {
    max_attempts = 1 # a blind retry could book twice; failures get a Retry button instead
  }

  lifecycle {
    ignore_changes = [desired_state] # deploy/bot.sh pause|resume owns this
  }
}

resource "google_cloud_scheduler_job" "sync" {
  name             = "slotbot-sync"
  region           = var.tasks_region
  schedule         = "7 * * * *"
  time_zone        = "Europe/Madrid"
  attempt_deadline = "600s"

  retry_config {
    retry_count = 0 # the next hourly run is the retry
  }

  http_target {
    http_method = "POST"
    uri         = "${local.url}/jobs/sync"
    headers = {
      "X-Job-Token" = data.google_secret_manager_secret_version.job_token.secret_data
    }
    oidc_token {
      service_account_email = google_service_account.slotbot.email
      audience              = local.url
    }
  }

  lifecycle {
    ignore_changes = [paused] # deploy/bot.sh pause|resume owns this
  }
}
