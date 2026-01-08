#!/bin/bash
set -eu

LOG=$(mktemp /tmp/migration_log.XXXXXX.log)

BODY=$(cat <<'EOF'
This cronjob mirrors the current production User App database to the new
database server in the CHTC Transition Project.

Failure means that the mirroring did not complete successfully, and manual
intervention is required. Until the mirroring is complete the data is not correctly
synchronized between the two databases.
EOF
)

cleanup() {
  rm -f "$LOG"
}
trap cleanup EXIT

on_err() {
  rc=$?
  # Send failure email: include BODY as the message and attach the log for details.
  python3 send_email.py --from "chtc-cron-mailto@chtc.io" --to "clock@wisc.edu" --subject "🔥🔥🔥🔥🔥 - User App Database Failed Mirroring" --text "$BODY" --file "$LOG" || true
  exit $rc
}
trap on_err ERR

# Run migration and capture stdout/stderr to the log
python3 migrate.py > "${LOG}" 2>&1

# Success: send success email with the same log attached
python3 send_email.py --from "chtc-cron-mailto@chtc.io" --to "clock@wisc.edu" --subject "✅✅✅✅✅ - User App Database Mirrored" --text "$BODY" || true

exit 0