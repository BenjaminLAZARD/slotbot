# Spending cap: email alerts at 10/50/100 %; Pub/Sub pushes the budget status to /jobs/budget, which
# detaches billing once spend reaches the cap (Google budgets only alert by themselves).
resource "google_pubsub_topic" "budget" {
  name = "slotbot-budget"
}

resource "google_pubsub_subscription" "budget_push" {
  name                       = "slotbot-budget-push"
  topic                      = google_pubsub_topic.budget.id
  ack_deadline_seconds       = 60
  message_retention_duration = "3600s"

  expiration_policy {
    ttl = "" # never
  }

  push_config {
    # Pub/Sub push can't set headers: the job token travels in the query string.
    push_endpoint = "${local.url}/jobs/budget?token=${data.google_secret_manager_secret_version.job_token.secret_data}"
    oidc_token {
      service_account_email = google_service_account.slotbot.email
      audience              = local.url # Cloud Run rejects an audience carrying the query
    }
  }
}

resource "google_billing_budget" "cap" {
  billing_account = var.billing_account
  display_name    = "slotbot cap ${var.budget_eur} EUR"

  budget_filter {
    projects               = ["projects/${data.google_project.this.number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.budget_eur)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.1, 0.5, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    pubsub_topic   = google_pubsub_topic.budget.id
    schema_version = "1.0"
  }
}
