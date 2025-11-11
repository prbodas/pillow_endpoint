#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
# Source optional local env for secrets (not checked in)
if [ -f "$ROOT_DIR/.env.local" ]; then
  set -a
  source "$ROOT_DIR/.env.local"
  set +a
fi
VENV_PY="$ROOT_DIR/.venv/bin/python3"
DEFAULT_MODEL_DIR="$ROOT_DIR/models/vosk-model-small-en-us-0.15"

# Prefer a valid model dir; if env is set but invalid, fall back to default in repo
if [ -n "${VOSK_MODEL_DIR:-}" ] && [ -f "$VOSK_MODEL_DIR/conf/model.conf" ]; then
  export VOSK_MODEL_DIR="$VOSK_MODEL_DIR"
else
  if [ -f "$DEFAULT_MODEL_DIR/conf/model.conf" ]; then
    export VOSK_MODEL_DIR="$DEFAULT_MODEL_DIR"
  else
    export VOSK_MODEL_DIR="${VOSK_MODEL_DIR:-$DEFAULT_MODEL_DIR}"
  fi
fi
export VOSK_PYTHON="$VENV_PY"
echo "Using VOSK_MODEL_DIR=$VOSK_MODEL_DIR"
echo "Using VOSK_PYTHON=$VOSK_PYTHON"
# Note: OpenRouter no longer used
if [ -n "${GEMINI_API_KEY:-}" ]; then
  echo "GEMINI_API_KEY is set (length ${#GEMINI_API_KEY})"
else
  echo "GEMINI_API_KEY not set — /llm and llm_tts will fail"
fi
node "$ROOT_DIR/server.js"
