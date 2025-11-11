#!/usr/bin/env bash
set -euo pipefail

MODEL_URL=${MODEL_URL:-"https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"}
MODEL_NAME=${MODEL_NAME:-"vosk-model-small-en-us-0.15"}
PYTHON_BIN=${PYTHON_BIN:-python3}

echo "[1/5] Creating virtualenv .venv"
${PYTHON_BIN} -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

echo "[2/5] Installing Python deps (vosk, sounddevice, numpy)"
pip install vosk sounddevice numpy

echo "[3/5] Ensuring ffmpeg is installed (optional, used for conversions)"
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Homebrew found. Installing ffmpeg via brew (may prompt)..."
    brew install ffmpeg || true
  else
    echo "ffmpeg not found and Homebrew not available. Please install ffmpeg manually for best compatibility."
  fi
fi

echo "[4/5] Downloading Vosk model to models/ (${MODEL_NAME})"
mkdir -p models
cd models
if [ ! -d "${MODEL_NAME}" ]; then
  curl -L -o ${MODEL_NAME}.zip "${MODEL_URL}"
  unzip -o ${MODEL_NAME}.zip
else
  echo "Model ${MODEL_NAME} already present; skipping download."
fi
cd ..

echo "[5/5] Writing helper runner scripts"
cat > scripts/run_local.sh << 'EOS'
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
EOS
chmod +x scripts/run_local.sh

echo "Done. Start the server with: scripts/run_local.sh"
echo "Then test: curl -s http://127.0.0.1:8787/health"
