variable "project" {
  type = string
}

variable "region" {
  description = "Cloud Run region (Madrid: closest to the booking site)."
  type        = string
  default     = "europe-southwest1"
}

variable "tasks_region" {
  description = "Cloud Tasks and Cloud Scheduler region (Cloud Tasks isn't offered in Madrid)."
  type        = string
  default     = "europe-west1"
}

variable "billing_account" {
  type = string
}

variable "budget_eur" {
  description = "Monthly cap: alerts at 10/50/100 %, billing detached at 100 % (kill switch)."
  type        = number
  default     = 10
}

variable "github_repository" {
  description = "owner/name of the repository allowed to deploy (GitHub Actions, main branch only)."
  type        = string
}

variable "env" {
  description = "Plain SLOTBOT_* settings of the Cloud Run service (secrets are wired separately)."
  type        = map(string)
  default     = {}
}

variable "public" {
  description = "Let anyone reach the site (sign-in then guards the app). False = only allowed accounts, via the proxy."
  type        = bool
  default     = false
}
