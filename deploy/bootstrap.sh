#!/usr/bin/env bash
# Provision a fresh Raspberry Pi OS (64-bit) host and start speedmonitor. Idempotent.
# Run from the Mac:  ssh pi.internal.accapehart.com 'bash -s' < deploy/bootstrap.sh
# If ~/speedmonitor-legacy.db exists on the Pi, its history is backfilled once.
set -euo pipefail

# Wrapped in main so bash parses the whole script before running it: under `bash -s`,
# any command that reads stdin would otherwise swallow the rest of the script.
main() {
  REPO=https://github.com/capehart/speedmonitor.git
  BRANCH=${BRANCH:-main}
  DIR=$HOME/speedmonitor
  LEGACY_DB=$HOME/speedmonitor-legacy.db

  # Docker's own apt repo: Debian's packages lag and split compose/buildx inconsistently.
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -q
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq git docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  docker() { sudo docker "$@"; }  # group membership only applies to new logins

  if [[ -d $DIR/.git ]]; then
    git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q "$BRANCH" && git -C "$DIR" pull -q --ff-only
  else
    git clone -q --branch "$BRANCH" "$REPO" "$DIR"
  fi
  cd "$DIR"

  touch .env && chmod 600 .env
  for var in GRAFANA_ADMIN_PASSWORD RENDERER_TOKEN; do
    if ! grep -q "^$var=" .env; then
      printf '%s=%s\n' "$var" "$(openssl rand -hex 16)" >> .env
      echo "Generated $var in $DIR/.env"
    fi
  done

  docker compose version >/dev/null
  docker compose build -q
  docker compose pull -q

  if [[ -f $LEGACY_DB && ! -f data/.backfilled ]]; then
    mkdir -p data
    PYTHONPATH=src python3 -m speedmonitor.backfill "$LEGACY_DB" data/history.om
    docker compose run --rm -T --no-deps -v "$DIR/data:/backfill:ro" --entrypoint promtool prometheus \
      tsdb create-blocks-from openmetrics --max-block-duration=744h /backfill/history.om /prometheus
    rm data/history.om
    touch data/.backfilled
  fi

  docker compose up -d --remove-orphans
  docker compose ps
}

main "$@"
