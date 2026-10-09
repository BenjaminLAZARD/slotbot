#!/usr/bin/env sh
# Pause, resume or inspect the cloud bot.  Usage: deploy/bot.sh pause|resume|status|ui
#
# Cloud Run only runs when called, so pausing its two callers stops the bot: the hourly calendar
# scan (Cloud Scheduler) and the race triggers (Cloud Tasks; paused tasks are kept and fire, late,
# on resume). The budget kill switch keeps working. `ui` = deploy/proxy.sh (the site while private).
set -eu
PROJECT=${SLOTBOT_GCP_PROJECT:-divine-camera-228017}
TASKS_REGION=europe-west1
REGION=europe-southwest1
G="--project $PROJECT --location $TASKS_REGION"

case "${1:-status}" in
  pause)
    gcloud scheduler jobs pause slotbot-sync $G
    gcloud tasks queues pause slotbot $G ;;
  resume)
    gcloud scheduler jobs resume slotbot-sync $G
    gcloud tasks queues resume slotbot $G ;;
  status)
    echo "calendar scan: $(gcloud scheduler jobs describe slotbot-sync $G --format 'value(state,scheduleTime)')"
    echo "race triggers: $(gcloud tasks queues describe slotbot $G --format 'value(state)')"
    gcloud tasks list --queue slotbot $G --format 'value(scheduleTime)' | sed 's/^/  queued race at /' ;;
  ui)
    exec "$(dirname "$0")/proxy.sh" ;;
  *)
    echo "usage: $0 pause|resume|status|ui" >&2; exit 2 ;;
esac
