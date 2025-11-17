#!/usr/bin/env bash
set -euo pipefail

# curl_llm_tts.sh — Hit the AI server's /llm_tts endpoint and play the reply.
# - Sends JSON { text, voice, session, llm_model } via POST
# - Saves MP3 to a stable location and plays it (ffmpeg→aplay, mpg123, cvlc, ffplay, afplay, or sox)

# Sensible defaults for local dev; override with flags.
BASE="${BASE:-http://127.0.0.1:8787}"
TEXT=${TEXT:-"Say hello in five words."}
VOICE=${VOICE:-Brian}
SESSION=${SESSION:-prod}
MODEL=${MODEL:-gemini-2.0-flash}
OUTDIR="${OUTDIR:-./tts_downloads}"
OUTFILE=""
ALSA_DEV="${ALSA_DEV:-plughw:1,0}"
NOPLAY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [-b base_url] [-t text] [-v voice] [-s session] [-M model] [-d out_dir] [-o out_file] [-A alsa_dev] [-n]

Sends a POST to /llm_tts and plays the returned MP3.

Options:
  -b  Base URL (default: ${BASE})
  -t  Text to send (default: "${TEXT}")
  -v  Voice (default: ${VOICE})
  -s  Session id (default: ${SESSION})
  -M  LLM model id (default: ${MODEL})
  -d  Output directory (default: ${OUTDIR})
  -o  Output file path (overrides -d)
  -A  ALSA device for aplay (default: ${ALSA_DEV})
  -n  No playback (save only)

Examples:
  $(basename "$0") -b http://127.0.0.1:8787 -t "What time is it?" -v Brian
  $(basename "$0") -b https://<ai-service>.onrender.com -t "Describe a cat" -v Joanna -s dev1
  $(basename "$0") -o ./tts_downloads/reply.mp3 "Tell me a joke"
EOF
}

while getopts ":b:t:v:s:M:d:o:A:nh" opt; do
  case "$opt" in
    b) BASE="$OPTARG" ;;
    t) TEXT="$OPTARG" ;;
    v) VOICE="$OPTARG" ;;
    s) SESSION="$OPTARG" ;;
    M) MODEL="$OPTARG" ;;
    d) OUTDIR="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    A) ALSA_DEV="$OPTARG" ;;
    n) NOPLAY=true ;;
    h) usage; exit 0 ;;
    :) echo "Missing value for -$OPTARG" >&2; usage; exit 2 ;;
    \?) echo "Unknown option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

# Allow positional text without -t
shift $((OPTIND-1)) || true
if [[ $# -gt 0 ]]; then TEXT="$*"; fi

if ! command -v curl >/dev/null 2>&1; then echo "curl not found" >&2; exit 2; fi

# Output path
if [[ -n "$OUTFILE" ]]; then
  OUT="$OUTFILE"; mkdir -p "$(dirname "$OUT")"
else
  mkdir -p "$OUTDIR"
  if command -v mktemp >/dev/null 2>&1; then OUT=$(mktemp -p "$OUTDIR" llmtts_XXXXXXXX.mp3)
  else OUT="$OUTDIR/llmtts_$(date +%Y%m%d_%H%M%S).mp3"; fi
fi

echo "POST /llm_tts → $BASE?debug=1"

# Build JSON payload robustly using Python (handles any characters)
json_payload=$(LLM_TEXT="$TEXT" LLM_VOICE="$VOICE" LLM_SESSION="$SESSION" LLM_MODEL="$MODEL" python3 - "$TEXT" <<'PY'
import json, os, sys
text = os.environ.get('LLM_TEXT', '')
payload = {
  'text': text,
  'voice': os.environ.get('LLM_VOICE','Brian'),
  'session': os.environ.get('LLM_SESSION','prod'),
  'llm_model': os.environ.get('LLM_MODEL','gemini-2.0-flash'),
}
print(json.dumps(payload))
PY
)

curl -fsSL -X POST \
  -H 'Content-Type: application/json' \
  -d "$json_payload" \
  "${BASE%/}/llm_tts?debug=1" -o "$OUT"

echo "Saved: $OUT"

$NOPLAY && exit 0

# Playback (prefers ffmpeg→aplay for Pi)
if command -v aplay >/dev/null 2>&1 && command -v ffmpeg >/dev/null 2>&1; then
  if [[ -n "$ALSA_DEV" ]]; then
    ffmpeg -loglevel error -i "$OUT" -f wav - 2>/dev/null | aplay -q -D "$ALSA_DEV"
  else
    ffmpeg -loglevel error -i "$OUT" -f wav - 2>/dev/null | aplay -q
  fi
elif command -v mpg123 >/dev/null 2>&1; then
  mpg123 -q "$OUT"
elif command -v cvlc >/dev/null 2>&1; then
  cvlc --play-and-exit --no-video "$OUT"
elif command -v ffplay >/dev/null 2>&1; then
  ffplay -nodisp -autoexit -loglevel quiet "$OUT"
elif command -v afplay >/dev/null 2>&1; then
  afplay "$OUT"
elif command -v play >/dev/null 2>&1; then
  play -q "$OUT"
else
  echo "No supported audio player found. Install ffmpeg+aplay (recommended), mpg123, vlc (cvlc), ffmpeg (ffplay), or sox (play)." >&2
  exit 2
fi
