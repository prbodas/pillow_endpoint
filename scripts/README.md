Scripts overview (kept)

- run_local.sh: Start server with local env (.env.local, VOSK model autodetect).
- setup_vosk.sh: Convenience setup for Vosk model/ffmpeg.
- vosk_transcribe.py: Internal helper invoked by the server for ASR.
- curl_play.sh: Fetch speech from /tts (basic TTS demo) and play it.
- curl_llm_tts.sh: Call /llm_tts (Gemini → TTS direct audio). Supports text, file, or mic capture (-m) and plays the reply.
- mic_llm_tts.py: Python mic client for /llm_tts (audio-in → audio-out). Default playback for mac; add --pi for Raspberry Pi ALSA.

Deprecated/removed
- Old /transcribe and /llm client scripts were removed in favor of /llm_tts.

Quick usage
- Basic TTS demo: `./scripts/curl_play.sh -b https://tts-waifu.onrender.com -t "hello" -v Brian`
- LLM→TTS (text): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -t "say hi" -v Brian`
- LLM→TTS (mic): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -m -v Brian`
- Python mic: `python3 scripts/mic_llm_tts.py` (press Enter to stop). On Pi: `--pi --alsa-dev plughw:1,0`.
