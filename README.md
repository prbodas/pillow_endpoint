TTS + Gemini Audio Endpoint

Endpoints
- GET `/`:
  - Usage text.
- GET `/tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20`:
  - Returns `audio/mpeg` speech of text. Defaults to “I love my waifu”.
  - `stream=true` streams timed chunks. Tunables: `chunk` bytes, `gap` ms.
- POST `/llm_tts` (direct audio of LLM reply):
  - JSON: `{ text, voice?, session?, llm_model?, system? }` → `audio/mpeg`
  - Audio-in: send binary audio (`audio/wav|mpeg|ogg`) with optional `voice`, `session`, `llm_model`, `system` → server transcribes (Vosk), calls Gemini, returns TTS.

Local Dev
- Install deps: `npm i`
- Start server: `npm start`
- Test TTS: `curl -L "http://localhost:8787/tts?stream=false" --output waifu.mp3`
- Test LLM→TTS (text): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -t "say hello" -v Brian`
- Test LLM→TTS (audio file): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -f sample.wav -v Brian`
- Mic → LLM→TTS (python): mac: `python3 scripts/mic_llm_tts.py`; Pi: `python3 scripts/mic_llm_tts.py --pi --alsa-dev plughw:1,0`

Deploy to Render (Docker)
- One‑click Blueprint: https://render.com/deploy?repo=https://github.com/prbodas/pillow_endpoint
  - Dockerfile bundles Python + ffmpeg + a small Vosk model, so audio-in works.
  - After create, add env var `GEMINI_API_KEY` to the `tts-waifu` service.
  - Subsequent pushes to `main` auto-deploy.
- Script helper: `./scripts/deploy_via_blueprint.sh` opens the prefilled Blueprint page.

Clients
- Curl:
  - `/tts`: `./scripts/curl_play.sh -b https://tts-waifu.onrender.com -t "hello" -v Brian`
  - `/llm_tts` (text): `./scripts/curl_llm_tts.sh -b https://tts-waifu.onrender.com -t "say hello" -v Joanna`
  - `/llm_tts` (mic): `./scripts/curl_llm_tts.sh -b https://tts-waifu.onrender.com -m -v Brian`
- Python mic client: `python3 scripts/mic_llm_tts.py` (add `--pi --alsa-dev plughw:1,0` on Raspberry Pi)

Testing
- Node built-in test runner: `npm test`
- Unit tests cover Gemini client behavior.
