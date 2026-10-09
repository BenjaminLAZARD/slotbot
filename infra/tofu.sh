#!/usr/bin/env sh
# Run OpenTofu as your active gcloud account:  infra/tofu.sh plan | apply | output ...
# (The Google provider would otherwise use "application default credentials", which may be another
# account or absent; a short-lived token from `gcloud auth print-access-token` avoids that.)
set -eu
cd "$(dirname "$0")"
GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
export GOOGLE_OAUTH_ACCESS_TOKEN
exec tofu "$@"
