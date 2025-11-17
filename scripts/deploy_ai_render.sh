#!/usr/bin/env bash
set -euo pipefail

# Deploy the AI server (server_ai.js) to Render via REST API.
# Requirements: curl, jq. Provide RENDER_API_KEY and GEMINI_API_KEY.

API="https://api.render.com/v1"
SERVICE_NAME="ai-waifu"
REPO_URL=${REPO_URL:-$(git config --get remote.origin.url 2>/dev/null || echo "")}
BRANCH=${BRANCH:-main}

if ! command -v curl >/dev/null 2>&1; then echo "curl is required" >&2; exit 2; fi
if ! command -v jq >/dev/null 2>&1; then echo "jq is required (sudo apt-get install -y jq)" >&2; exit 2; fi

if [[ -z "${RENDER_API_KEY:-}" ]]; then
  echo "Set RENDER_API_KEY in your environment." >&2
  echo "  export RENDER_API_KEY=..." >&2
  exit 2
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "Set GEMINI_API_KEY in your environment (for the service)." >&2
  echo "  export GEMINI_API_KEY=..." >&2
  exit 2
fi

if [[ -z "$REPO_URL" ]]; then
  echo "Could not determine repo URL. Set REPO_URL explicitly:" >&2
  echo "  REPO_URL=https://github.com/<user>/<repo>.git $0" >&2
  exit 2
fi

echo "Creating/updating Render service: $SERVICE_NAME from $REPO_URL (branch $BRANCH)"

AUTH=( -H "Authorization: Bearer ${RENDER_API_KEY}" -H "Content-Type: application/json" )

# Try to find an existing service by name
echo "Looking up existing service..."
EXISTING=$(curl -fsSL "${API}/services?limit=100" "${AUTH[@]}" | jq -r ".[] | select(.name==\"${SERVICE_NAME}\") | .id" || true)

if [[ -n "$EXISTING" ]]; then
  echo "Service exists (id=$EXISTING). Updating environment variables..."
  # Upsert GEMINI_API_KEY
  curl -fsSL -X PUT "${API}/services/${EXISTING}/env-vars" "${AUTH[@]}" \
    -d "$(jq -n --arg k GEMINI_API_KEY --arg v "$GEMINI_API_KEY" '[{key:$k,value:$v}]')" >/dev/null
  echo "Triggering deploy..."
  curl -fsSL -X POST "${API}/services/${EXISTING}/deploys" "${AUTH[@]}" -d '{}' >/dev/null
  echo "Done. Visit the service in the Render dashboard to find the URL."
  exit 0
fi

echo "Creating new service..."
CREATE_BODY=$(jq -n \
  --arg name "$SERVICE_NAME" \
  --arg repo "$REPO_URL" \
  --arg branch "$BRANCH" \
  '{
    type: "web",
    name: $name,
    env: "node",
    repo: $repo,
    branch: $branch,
    buildCommand: "echo no build",
    startCommand: "node server_ai.js",
    healthCheckPath: "/health",
    autoDeploy: true,
    envVars: [
      { key: "NODE_VERSION", value: "18" },
      { key: "GEMINI_API_KEY", value: env.GEMINI_API_KEY }
    ]
  }')

RESP=$(curl -fsSL -X POST "${API}/services" "${AUTH[@]}" -d "$CREATE_BODY" || true)
if [[ -z "$RESP" ]]; then
  echo "Service creation failed. Check your API key/permissions." >&2
  exit 1
fi

ID=$(echo "$RESP" | jq -r '.id // empty')
URL=$(echo "$RESP" | jq -r '.serviceDetails.url // empty')
if [[ -z "$ID" ]]; then
  echo "Unexpected API response:" >&2
  echo "$RESP" | jq . >&2
  exit 1
fi

echo "Created service id=$ID"
echo "Render may take a minute to build and start the service."
if [[ -n "$URL" ]]; then
  echo "Once live: $URL"
fi

