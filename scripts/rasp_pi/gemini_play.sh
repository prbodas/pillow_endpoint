#!/usr/bin/env bash
set -euo pipefail

# Raspberry Pi helper — send text to /llm_tts on Render and play audio via ALSA.

BASE="${BASE:-${PI_BASE:-https://tts-waifu.onrender.com}}"
TEXT=""
VOICE="${VOICE:-Brian}"
SESSION="${SESSION:-pi}"
MODEL="${MODEL:-gemini-2.0-flash}"
ALSA_DEV="${ALSA_DEV:-plughw:1,0}"
OUTFILE="${OUTFILE:-}"
NOPLAY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [-b base_url] [-t text] [-v voice] [-s session] [-M model] [-A alsa_dev] [-o outfile] [-n]

Options:
  -b  Base URL (default: ${BASE})
  -t  Text to send (default: prompt for input if omitted)
  -v  Voice (default: ${VOICE})
  -s  Session id (default: ${SESSION})
  -M  LLM model id (default: ${MODEL})
  -A  ALSA device for aplay (default: ${ALSA_DEV})
  -o  Output file path (saves MP3)
  -n  No playback (save only)

Examples:
  $(basename "$0") -b https://tts-waifu.onrender.com -t "hello from pi" -A plughw:1,0
  $(basename "$0") -b https://tts-waifu.onrender.com -o ~/audio/reply.mp3 "tell me a joke"
EOF
}

while getopts ":b:t:v:s:M:A:o:nh" opt; do
  case "$opt" in
    b) BASE="$OPTARG" ;;
    t) TEXT="$OPTARG" ;;
    v) VOICE="$OPTARG" ;;
    s) SESSION="$OPTARG" ;;
    M) MODEL="$OPTARG" ;;
    A) ALSA_DEV="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    n) NOPLAY=true ;;
    h) usage; exit 0 ;;
    :) echo "Missing value for -$OPTARG" >&2; usage; exit 2 ;;
    \?) echo "Unknown option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done
shift $((OPTIND-1)) || true

# Allow positional text
if [[ -z "$TEXT" && $# -gt 0 ]]; then
  TEXT="$*"
fi

if [[ -z "$TEXT" ]]; then
  read -rp "Enter text: " TEXT
fi

mkdir -p ./tts_downloads
if [[ -n "$OUTFILE" ]]; then
  OUT="$OUTFILE"; mkdir -p "$(dirname "$OUT")"
else
  if command -v mktemp >/dev/null 2>&1; then OUT=$(mktemp -p ./tts_downloads pi_XXXXXXXX.mp3)
  else OUT=./tts_downloads/pi_$(date +%Y%m%d_%H%M%S).mp3; fi
fi

if ! command -v curl >/dev/null 2>&1; then echo "curl not found" >&2; exit 2; fi

# Build JSON using Python to handle any characters safely
json_payload=$(LLM_TEXT="$TEXT" LLM_VOICE="$VOICE" LLM_SESSION="$SESSION" LLM_MODEL="$MODEL" python3 - <<'PY'
import json, os
payload = {
  'text': os.environ.get('LLM_TEXT',''),
  'voice': os.environ.get('LLM_VOICE','Brian'),
  'session': os.environ.get('LLM_SESSION','pi'),
  'llm_model': os.environ.get('LLM_MODEL','gemini-2.0-flash'),
}
print(json.dumps(payload))
PY
)

echo "POST /llm_tts → ${BASE}"
curl -fsSL -X POST \
  -H 'Content-Type: application/json' \
  -d "$json_payload" \
  "${BASE%/}/llm_tts" -o "$OUT"

echo "Saved: $OUT"

$NOPLAY && exit 0

# Playback on Pi: prefer ffmpeg→aplay
if command -v aplay >/dev/null 2>&1 && command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -loglevel error -i "$OUT" -f wav - 2>/dev/null | aplay -q -D "${ALSA_DEV}"
  exit 0
fi

if command -v mpg123 >/dev/null 2>&1; then
  mpg123 -q "$OUT"; exit 0
fi

if command -v cvlc >/dev/null 2>&1; then
  cvlc --play-and-exit --no-video "$OUT"; exit 0
fi

if command -v ffplay >/dev/null 2>&1; then
  ffplay -nodisp -autoexit -loglevel quiet "$OUT"; exit 0
fi

echo "No supported audio player found. Install ffmpeg+aplay (recommended) or mpg123/vlc." >&2
exit 2

