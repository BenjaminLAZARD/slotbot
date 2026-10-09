#!/usr/bin/env sh
# Open the private cloud site on your Mac:  deploy/proxy.sh [port]   (default 8090, Ctrl-C to stop)
# then browse http://localhost:8090
#
# Why it's needed: the Cloud Run service is deployed *private* (--no-allow-unauthenticated). Google's
# front end rejects every request that doesn't carry an identity token from an account allowed to
# invoke the service, so opening the run.app URL in a browser gives "permission denied".
# `gcloud run services proxy` runs a small server on your Mac that adds *your* identity token (from
# `gcloud auth login`) to each request and forwards it to Cloud Run. Nobody else can use it: it
# listens on localhost only. Not needed once the site is public with Google sign-in (deploy/gcp.md §9).
#
# The token it adds lasts about an hour and the proxy doesn't renew it (you'd get "401 Unauthorized"
# after a while), so this script restarts the proxy every 50 minutes, with a gap of a second or two.
set -eu
PROJECT=${SLOTBOT_GCP_PROJECT:-divine-camera-228017}
REGION=europe-southwest1
PORT=${1:-8090}
pid=""

stop() { [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; }
trap 'stop; exit 0' INT TERM

echo "slotbot on http://localhost:$PORT (Ctrl-C to stop)"
while :; do
  gcloud run services proxy slotbot --project "$PROJECT" --region "$REGION" --port "$PORT" &
  pid=$!
  i=0
  while [ "$i" -lt 600 ]; do # 600 x 5 s = 50 min
    if ! kill -0 "$pid" 2>/dev/null; then # the proxy quit by itself (port busy, not logged in...)
      wait "$pid" || exit $?
      exit 0
    fi
    sleep 5
    i=$((i + 1))
  done
  stop
  wait "$pid" 2>/dev/null || true
  echo "$(date +%H:%M) renewing the proxy's Google token"
done
