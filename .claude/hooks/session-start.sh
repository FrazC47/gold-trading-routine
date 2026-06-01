#!/bin/bash
set -euo pipefail

# Only run in Claude Code remote (web) sessions
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install Python dependencies
pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt"

# Write Google Service Account credentials from environment variable
if [ -n "${GOOGLE_CREDENTIALS_JSON:-}" ]; then
  echo "$GOOGLE_CREDENTIALS_JSON" > "$CLAUDE_PROJECT_DIR/credentials.json"
  echo "[session-start] credentials.json written from GOOGLE_CREDENTIALS_JSON"
else
  echo "[session-start] GOOGLE_CREDENTIALS_JSON not set — Google Sheets write-back will be skipped"
fi
