#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://tts-waifu.onrender.com}"
TEXT="I love my waifu"
VOICE="Brian"
STREAM="false"
# Where to store fetched audio. Use -d or -o to override.
OUTDIR="${OUTDIR:-./tts_downloads}"
OUTFILE=""
# Default ALSA device (Raspberry Pi typical). Can override with -A or env ALSA_DEV
ALSA_DEV="${ALSA_DEV:-plughw:1,0}"
# Endpoint path and AI params
PATHNAME="/tts"
SESSION="prod"
MODEL="gemini-2.0-flash"

usage() {
  cat <<EOF
Usage: $(basename "$0") [-b base_url] [-t text] [-v voice] [-S] [-d out_dir] [-o out_file] [-A alsa_device] [-P path] [-s session] [-M model]

Options:
  -b  Base URL (default: ${BASE})
  -t  Text to synthesize (default: "${TEXT}")
  -v  Voice name/id (default: ${VOICE})
  -S  Stream=true (default: false) — downloads then plays if false
  -d  Output directory (default: ${OUTDIR})
  -o  Output file path (overrides -d)
  -A  ALSA device for aplay (default: ${ALSA_DEV})
  -P  Endpoint path (default: ${PATHNAME}). Use /llm_tts for direct audio from LLM.
  -s  Session id (for /llm_tts, default: ${SESSION})
  -M  LLM model (for /llm_tts, default: ${MODEL})

Examples:
  $(basename "$0") -t "Hello from curl" -v Joanna
  $(basename "$0") -b https://tts-waifu.onrender.com -t "Good morning" -v Brian
EOF
}

while getopts ":b:t:v:d:o:A:P:s:M:Sh" opt; do
  case "$opt" in
    b) BASE="$OPTARG" ;;
    t) TEXT="$OPTARG" ;;
    v) VOICE="$OPTARG" ;;
    d) OUTDIR="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    A) ALSA_DEV="$OPTARG" ;;
    P) PATHNAME="$OPTARG" ;;
    s) SESSION="$OPTARG" ;;
    M) MODEL="$OPTARG" ;;
    S) STREAM="true" ;;
    h) usage; exit 0 ;;
    :) echo "Missing value for -$OPTARG" >&2; usage; exit 2 ;;
    \?) echo "Unknown option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

# Allow positional text without -t
if [[ $# -gt 0 ]]; then
  TEXT="$*"
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found" >&2
  exit 2
fi

if [[ -n "$OUTFILE" ]]; then
  OUT="$OUTFILE"
  mkdir -p "$(dirname "$OUT")"
else
  mkdir -p "$OUTDIR"
  # Unique filename in target directory
  if command -v mktemp >/dev/null 2>&1; then
    OUT=$(mktemp -p "$OUTDIR" tts_XXXXXXXX.mp3)
  else
    OUT="$OUTDIR/tts_$(date +%Y%m%d_%H%M%S).mp3"
  fi
fi

echo "Fetching audio from: $BASE$PATHNAME"
if [[ "$PATHNAME" == "/llm_tts" ]]; then
  # POST JSON for LLM → TTS
  json_payload=$(node -e "const p=process; const t=p.argv.slice(1).join(' '); console.log(JSON.stringify({text:t, voice:'$VOICE', session:'$SESSION', llm_model:'$MODEL'}));" "$TEXT")
  curl -fsSL -X POST \
    -H 'Content-Type: application/json' \
    -d "$json_payload" \
    "${BASE%/}${PATHNAME}" -o "$OUT"
else
  curl -fsSLG \
    --data-urlencode "stream=${STREAM}" \
    --data-urlencode "text=${TEXT}" \
    --data-urlencode "voice=${VOICE}" \
    "${BASE%/}${PATHNAME}" -o "$OUT"
fi

echo "Saved: $OUT"

# Prefer ffmpeg → aplay when available (works well on Raspberry Pi/ALSA)
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
  # sox
  play -q "$OUT"
else
  echo "No supported audio player found. Install one of: ffmpeg+aplay (recommended), mpg123, vlc (cvlc), ffmpeg (ffplay), or sox (play)." >&2
  exit 2
fi
