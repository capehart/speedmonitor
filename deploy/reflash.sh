#!/usr/bin/env bash
# Mac-side halves of reflashing the Pi's only SD card. See "Deploying to the Pi" in the README.
#   deploy/reflash.sh before   # save the final legacy DB, then power the Pi off
#   deploy/reflash.sh after    # once the reflashed Pi boots: trust it, copy history, bootstrap
set -euo pipefail

PI=${PI:-pi.internal.accapehart.com}
BRANCH=${BRANCH:-main}
cd "$(dirname "$0")/.."
LEGACY_DB=data/speedmonitor-legacy.db

case "${1:-}" in
  before)
    mkdir -p data
    scp "$PI:development/speedmonitor/speedmonitor.db" "$LEGACY_DB"
    sqlite3 "$LEGACY_DB" "PRAGMA integrity_check; SELECT count(*) || ' legacy tests saved' FROM bandwidth;"
    ssh "$PI" sudo poweroff || true
    echo "Pi is shutting down. Wait for the green LED to stop blinking, then pull the card."
    ;;
  after)
    [[ -f $LEGACY_DB ]] || { echo "missing $LEGACY_DB; run '$0 before' first" >&2; exit 1; }
    ssh-keygen -R "$PI" >/dev/null 2>&1 || true
    echo "Waiting for $PI to accept SSH..."
    until ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$PI" true 2>/dev/null; do sleep 5; done
    scp "$LEGACY_DB" "$PI:speedmonitor-legacy.db"
    ssh "$PI" "BRANCH=$BRANCH bash -s" < deploy/bootstrap.sh
    ;;
  *)
    echo "usage: $0 before|after" >&2
    exit 2
    ;;
esac
