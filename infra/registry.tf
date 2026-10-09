# Images built by `gcloud run deploy --source` (repository created by gcloud on the first deploy).
# Keep the last 2, delete older ones after a day: storage beyond 0.5 GB is billed.
resource "google_artifact_registry_repository" "images" {
  repository_id = "cloud-run-source-deploy"
  location      = var.region
  format        = "DOCKER"
  description   = "Cloud Run Source Deployments"

  cleanup_policies {
    id     = "keep-last-2"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }

  cleanup_policies {
    id     = "delete-older"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "86400s"
    }
  }
}
