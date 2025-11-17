Scripts overview

- mic_convo.py: Hands-free, sessioned mic → ASR → LLM → TTS chat.
- mic_transcribe.py: Simple mic capture → /transcribe, optional TTS playback.
- llm_chat.py: Quick CLI to hit /llm without audio.
- vosk_transcribe.py: Internal helper called by server.js to run Vosk.
- run_local.sh: Start server with local env.
- setup_vosk.sh: Convenience setup for Vosk model/ffmpeg.
- curl_play.sh: Fetch speech from /tts (basic TTS demo) and play it.
- curl_llm_tts.sh: Call /llm_tts (Gemini → TTS direct audio) and play.

Examples (moved to scripts/examples/)
- call_transcribe.py: File-based request to /transcribe with multipart parsing.
- play_waifu.py: Streaming/non-streaming TTS client demo.

Notes
- These utilities are optional. The primary interface is the Node server endpoints.
- Keep Python deps isolated via your virtualenv (.venv) as needed.

Quick usage
- Basic TTS demo: `./scripts/curl_play.sh -b https://tts-waifu.onrender.com -t "hello" -v Brian`
- Gemini reply as audio: `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -t "say hi" -v Brian`
