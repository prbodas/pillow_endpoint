#!/usr/bin/env bash
set -euo pipefail

# Raspberry Pi helper — send text to /llm_tts on Render and play audio via ALSA.

BASE="${BASE:-${PI_BASE:-https://tts-waifu.onrender.com}}"
TEXT=""
VOICE="${VOICE:-Brian}"
SESSION="${SESSION:-pi}"
MODEL="${MODEL:-gemini-2.0-flash}"
ALSA_DEV="${ALSA_DEV:-plughw:0,1}"
OUTFILE="${OUTFILE:-}"
NOPLAY=false
FILE=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [-b base_url] [-t text] [-f audio_file] [-v voice] [-s session] [-M model] [-A alsa_dev] [-o outfile] [-n]

Options:
  -b  Base URL (default: ${BASE})
  -t  Text to send (default: prompt for input if omitted)
  -f  Audio file to send (audio in → audio out). If set, -t is ignored.
  -v  Voice (default: ${VOICE})
  -s  Session id (default: ${SESSION})
  -M  LLM model id (default: ${MODEL})
  -A  ALSA device for aplay (default: ${ALSA_DEV})
  -o  Output file path (saves MP3)
  -n  No playback (save only)

Examples:
  $(basename "$0") -b https://tts-waifu.onrender.com -t "hello from pi" -A plughw:1,0
  $(basename "$0") -b https://tts-waifu.onrender.com -o ~/audio/reply.mp3 "tell me a joke"
  $(basename "$0") -f tts_downloads/pi_vg0LGE9D.mp3 -v Brian
EOF
}

while getopts ":b:t:f:v:s:M:A:o:nh" opt; do
  case "$opt" in
    b) BASE="$OPTARG" ;;
    t) TEXT="$OPTARG" ;;
    f) FILE="$OPTARG" ;;
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

if [[ -z "$BASE" || "$BASE" == "https://"*".onrender.com" && "$BASE" == *"/" ]]; then
  # minimal sanity; user can override with -b
  :
fi

# Allow positional text
if [[ -z "$TEXT" && -z "$FILE" && $# -gt 0 ]]; then
  TEXT="$*"
fi

if [[ -z "$TEXT" && -z "$FILE" ]]; then
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

echo "POST /llm_tts → ${BASE}"

if [[ -n "$FILE" ]]; then
  # Verify file exists
  if [[ ! -f "$FILE" ]]; then
    echo "Error: Audio file not found: $FILE" >&2
    exit 2
  fi
  # Send audio file as binary; set content-type based on extension
  ext="${FILE##*.}"; ext="${ext,,}"
  ctype="application/octet-stream"
  case "$ext" in
    wav) ctype="audio/wav";;
    mp3) ctype="audio/mpeg";;
    ogg) ctype="audio/ogg";;
    aac) ctype="audio/aac";;
  esac
  if ! curl -sS -X POST \
    -H "Content-Type: ${ctype}" \
    --data-binary @"$FILE" \
    "${BASE%/}/llm_tts?debug=1&voice=$(printf %s "$VOICE" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')&session=$(printf %s "$SESSION" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')&llm_model=$(printf %s "$MODEL" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')" \
    -o "$OUT" -w "\nHTTP Status: %{http_code}\n"; then
    echo "Error: curl request failed" >&2
    if [[ -f "$OUT" && -s "$OUT" ]]; then
      echo "Server response:" >&2
      cat "$OUT" >&2
    fi
    exit 1
  fi
else
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

  curl -fsSL -X POST \
    -H 'Content-Type: application/json' \
    -d "$json_payload" \
    "${BASE%/}/llm_tts" -o "$OUT"
fi

echo "Saved: $OUT"

$NOPLAY && exit 0

# Playback on Pi: prefer ffmpeg→aplay
if command -v aplay >/dev/null 2>&1 && command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -loglevel error -i "$OUT" -f wav - 2>/dev/null | aplay -q -D "$ALSA_DEV"
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

