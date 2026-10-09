project           = "divine-camera-228017"
billing_account   = "0119BD-7A2780-C77110"
github_repository = "BenjaminLAZARD/slotbot"

# Settings of the Cloud Run service; change them here, not with `gcloud run services update`.
env = {
  SLOTBOT_CONTACT_EMAIL        = ""
  SLOTBOT_MADRID_OPENS_AT      = "00:00"
  SLOTBOT_MADRID_REQUEST_LIGHT = "false"
}
