#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
VENV_PY="$ROOT_DIR/.venv/bin/python3"
MODEL_DIR="$ROOT_DIR/models/vosk-model-small-en-us-0.15"
export VOSK_MODEL_DIR="$MODEL_DIR"
export VOSK_PYTHON="$VENV_PY"
echo "Using VOSK_MODEL_DIR=$VOSK_MODEL_DIR"
echo "Using VOSK_PYTHON=$VOSK_PYTHON"
node "$ROOT_DIR/server.js"
