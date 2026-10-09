terraform {
  required_version = ">= 1.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6"
    }
  }

  # State lives in a private, versioned bucket (created once by hand, see README.md).
  backend "gcs" {
    bucket = "divine-camera-228017-tofu-state"
    prefix = "slotbot"
  }
}

provider "google" {
  project = var.project
  region  = var.region
  # Charge API quota to this project, whatever project your gcloud setup defaults to.
  billing_project       = var.project
  user_project_override = true
}

data "google_project" "this" {}
