# The Cloud Run service (API + UI in one container, scale to zero). OpenTofu owns its settings;
# the image belongs to deploys (GitHub Actions or `gcloud run deploy --source .`), hence ignore_changes.
locals {
  url   = "https://slotbot-${data.google_project.this.number}.${var.region}.run.app"
  queue = "projects/${var.project}/locations/${var.tasks_region}/queues/slotbot"

  env = merge(
    {
      SLOTBOT_TRIGGERS          = "cloudtasks"
      SLOTBOT_CLOUD_TASKS_QUEUE = local.queue
      SLOTBOT_GCP_PROJECT       = var.project # budget kill switch
      SLOTBOT_PUBLIC_URL        = local.url
    },
    # Once public, /jobs/* checks the Google token of the bot's own account itself.
    var.public ? { SLOTBOT_JOB_CALLER = google_service_account.slotbot.email } : {},
    var.env,
  )
  secret_env = {
    SLOTBOT_DATABASE_URL   = "database_url"
    SLOTBOT_SECRET_KEY     = "secret_key"
    SLOTBOT_JOB_TOKEN      = "job_token"
    SLOTBOT_RESEND_API_KEY = "resend_api_key"
  }
}

resource "google_cloud_run_v2_service" "slotbot" {
  name                = "slotbot"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account                  = google_service_account.slotbot.email
    timeout                          = "3600s" # a race is one request, held open by Cloud Tasks
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = 1 # one bot: never two copies racing for the same court
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" # placeholder until the first deploy

      ports {
        name           = "http1"
        container_port = 8080
      }

      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true # CPU (and billing) only while a request is in flight
        startup_cpu_boost = true
      }

      startup_probe {
        failure_threshold = 1
        period_seconds    = 240
        timeout_seconds   = 240
        tcp_socket {
          port = 8080
        }
      }

      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.s[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      build_config,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.public ? 1 : 0
  name     = google_cloud_run_v2_service.slotbot.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
