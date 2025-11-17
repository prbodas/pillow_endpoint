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
FILE=""
REC=false
# REC_SECS=0 means interactive (press Enter to stop). Set >0 for timed recording.
REC_SECS=0
MIC_DEV=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [-b base_url] [-t text] [-v voice] [-s session] [-M model] [-d out_dir] [-o out_file] [-A alsa_dev] [-f file] [-m] [-R seconds] [-I mic_dev] [-n]

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
  -f  Audio file to send (audio in → audio out). If set, -t is ignored.
  -m  Record from mic (press Enter to stop). Uses ffmpeg/arecord/sox.
  -R  Record duration in seconds (default: ${REC_SECS}; 0 = press Enter to stop).
  -I  Mic device (Linux ALSA or ffmpeg input), e.g., hw:1,0 or plughw:1,0.
  -n  No playback (save only)

Examples:
  $(basename "$0") -b http://127.0.0.1:8787 -t "What time is it?" -v Brian
  $(basename "$0") -b https://<ai-service>.onrender.com -t "Describe a cat" -v Joanna -s dev1
  $(basename "$0") -o ./tts_downloads/reply.mp3 "Tell me a joke"
EOF
}

while getopts ":b:t:v:s:M:d:o:A:f:mR:I:nh" opt; do
  case "$opt" in
    b) BASE="$OPTARG" ;;
    t) TEXT="$OPTARG" ;;
    v) VOICE="$OPTARG" ;;
    s) SESSION="$OPTARG" ;;
    M) MODEL="$OPTARG" ;;
    d) OUTDIR="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    A) ALSA_DEV="$OPTARG" ;;
    f) FILE="$OPTARG" ;;
    m) REC=true ;;
    R) REC_SECS="$OPTARG" ;;
    I) MIC_DEV="$OPTARG" ;;
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

# Optional: capture from mic into a temp WAV if requested
TMPREC=""
if [[ "$REC" == "true" && -z "$FILE" ]]; then
  TMPREC=$(mktemp -t llmtts_rec_XXXXXX.wav)
  TMPLOG=$(mktemp -t llmtts_rec_log_XXXXXX.txt)
  os=$(uname -s)
  echo "Recording to $TMPREC ... (press Enter to stop)"
  if command -v ffmpeg >/dev/null 2>&1; then
    if [[ "$os" == "Darwin" ]]; then
      # macOS: avfoundation default audio input
      in_dev=":0"; [[ -n "$MIC_DEV" ]] && in_dev=":$MIC_DEV"
      ffmpeg -nostdin -y -f avfoundation -i "$in_dev" -ar 16000 -ac 1 -acodec pcm_s16le "$TMPREC" >>"$TMPLOG" 2>&1 &
    else
      # Linux: ALSA default or specified device
      in_dev="default"; [[ -n "$MIC_DEV" ]] && in_dev="$MIC_DEV"
      ffmpeg -nostdin -y -f alsa -i "$in_dev" -ar 16000 -ac 1 -acodec pcm_s16le "$TMPREC" >>"$TMPLOG" 2>&1 &
    fi
    rec_pid=$!
  elif command -v arecord >/dev/null 2>&1; then
    if [[ -n "$MIC_DEV" ]]; then
      arecord -D "$MIC_DEV" -f S16_LE -r 16000 -c 1 "$TMPREC" >>"$TMPLOG" 2>&1 &
    else
      arecord -f S16_LE -r 16000 -c 1 "$TMPREC" >>"$TMPLOG" 2>&1 &
    fi
    rec_pid=$!
  elif command -v rec >/dev/null 2>&1; then
    rec -q -r 16000 -c 1 "$TMPREC" >>"$TMPLOG" 2>&1 &
    rec_pid=$!
  else
    echo "No recorder found (ffmpeg/arecord/sox). Install one to use -m." >&2
    rm -f "$TMPREC"; TMPREC=""; rec_pid=""; rm -f "$TMPLOG" 2>/dev/null || true
  fi

  if [[ -n "${rec_pid:-}" ]]; then
    if [[ "$REC_SECS" -gt 0 ]]; then
      # Timed recording
      sleep "$REC_SECS"
    else
      # Interactive: press Enter to stop
      read -r _
    fi
    # Try graceful stop
    kill -INT "$rec_pid" >/dev/null 2>&1 || true
    # Wait a moment, then hard stop if needed
    sleep 0.3
    kill -TERM "$rec_pid" >/dev/null 2>&1 || true
    kill -KILL "$rec_pid" >/dev/null 2>&1 || true
    wait "$rec_pid" 2>/dev/null || true
  fi

  if [[ -n "$TMPREC" && -s "$TMPREC" ]]; then
    FILE="$TMPREC"
  else
    echo "Recording failed or empty file; continuing without audio input." >&2
    if [[ -n "$TMPLOG" && -s "$TMPLOG" ]]; then
      echo "Recorder log (last 20 lines):" >&2
      tail -n 20 "$TMPLOG" >&2 || true
    fi
    if [[ "$os" == "Darwin" ]] && command -v ffmpeg >/dev/null 2>&1; then
      echo "Available macOS devices (ffmpeg avfoundation):" >&2
      ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | sed -n '1,120p' >&2 || true
      echo "Tip: grant microphone access to your Terminal app under System Settings → Privacy & Security → Microphone." >&2
      echo "Use -I <index> to pick the audio device (shown in the list above)." >&2
    elif command -v arecord >/dev/null 2>&1; then
      echo "ALSA capture devices:" >&2
      arecord -l >&2 || true
      echo "Try -I hw:1,0 or -I plughw:1,0" >&2
    fi
    rm -f "$TMPREC" || true
    TMPREC=""
  fi
fi

if [[ -n "$FILE" ]]; then
  # Send audio file as binary; set content-type based on extension
  ext="${FILE##*.}"; ext="${ext,,}"
  ctype="application/octet-stream"
  case "$ext" in
    wav) ctype="audio/wav";;
    mp3) ctype="audio/mpeg";;
    ogg) ctype="audio/ogg";;
    aac) ctype="audio/aac";;
  esac
  curl -fsSL -X POST \
    -H "Content-Type: ${ctype}" \
    --data-binary @"$FILE" \
    "${BASE%/}/llm_tts?debug=1&voice=$(printf %s "$VOICE" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')&session=$(printf %s "$SESSION" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')&llm_model=$(printf %s "$MODEL" | python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))')" \
    -o "$OUT"
else
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
fi

echo "Saved: $OUT"

# Cleanup temp recording
if [[ -n "$TMPREC" ]]; then rm -f "$TMPREC"; fi
if [[ -n "${TMPLOG:-}" ]]; then rm -f "$TMPLOG" 2>/dev/null || true; fi

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
