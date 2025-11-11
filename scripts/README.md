Scripts overview

- mic_convo.py: Hands-free, sessioned mic → ASR → LLM → TTS chat.
- mic_transcribe.py: Simple mic capture → /transcribe, optional TTS playback.
- llm_chat.py: Quick CLI to hit /llm without audio.
- vosk_transcribe.py: Internal helper called by server.js to run Vosk.
- run_local.sh: Start server with local env.
- setup_vosk.sh: Convenience setup for Vosk model/ffmpeg.

Examples (moved to scripts/examples/)
- call_transcribe.py: File-based request to /transcribe with multipart parsing.
- play_waifu.py: Streaming/non-streaming TTS client demo.

Notes
- These utilities are optional. The primary interface is the Node server endpoints.
- Keep Python deps isolated via your virtualenv (.venv) as needed.

