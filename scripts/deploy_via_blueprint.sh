#!/usr/bin/env bash
set -euo pipefail

# Launches Render's "Deploy from Blueprint" flow for this repo.
# This uses render.yaml in the repo to create/update services.

REPO_URL=${REPO_URL:-$(git config --get remote.origin.url 2>/dev/null || echo "")}
if [[ -z "$REPO_URL" ]]; then
  echo "Could not determine repo URL. Set REPO_URL=https://github.com/<user>/<repo>" >&2
  exit 2
fi

# Normalize SSH to HTTPS
if [[ "$REPO_URL" =~ ^git@([^:]+):(.+)$ ]]; then
  host=${BASH_REMATCH[1]}
  path=${BASH_REMATCH[2]}
  REPO_URL="https://${host}/${path}"
fi
# Drop .git suffix for the deploy URL
REPO_URL_NO_GIT=${REPO_URL%.git}

DEPLOY_URL="https://render.com/deploy?repo=${REPO_URL_NO_GIT}"
echo "Open this URL to deploy via Render Blueprint:"
echo "$DEPLOY_URL"

# Try to open the browser on macOS/Linux with xdg-open
if command -v open >/dev/null 2>&1; then
  open "$DEPLOY_URL" || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$DEPLOY_URL" || true
fi

echo "In the Render UI:"
echo "- Add env var GEMINI_API_KEY on the tts-waifu service"
echo "- The Docker blueprint includes Python/ffmpeg/Vosk for audio-in already"
