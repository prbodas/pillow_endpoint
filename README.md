TTS Endpoint (Render)

Endpoints (kept)
- GET `/`:
  - Usage text.
- GET `/tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20`:
  - Returns `audio/mpeg` speech of text. Defaults to “I love my waifu”.
  - `stream=true` streams timed chunks (mock streaming). Tunables: `chunk` bytes, `gap` ms.
- POST `/llm_tts` (direct audio of LLM reply):
  - JSON mode: `{ text, voice?, session?, llm_model?, system? }` → `audio/mpeg`
  - Audio-in mode: send binary audio (`audio/wav|mpeg|ogg`) with optional query `voice`, `session`, `llm_model`, `system`. Server transcribes (Vosk), calls Gemini, returns TTS.

Local Dev
- Install deps: `npm i`
- Start server: `npm start`
- Test: `curl -L "http://localhost:8787/tts?stream=false" --output waifu.mp3`

Vosk setup (offline ASR)
- Install Python deps: `pip3 install vosk sounddevice numpy`
- Install ffmpeg (for audio conversion): macOS `brew install ffmpeg` (or your OS package manager)
- Download a Vosk model (small English example): https://alphacephei.com/vosk/models
  - Unzip and set env var to the model directory, e.g. `export VOSK_MODEL_DIR=/path/to/vosk-model-small-en-us-0.15`

LLM→TTS tests
- JSON (local): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -t "say hello" -v Brian`
- Audio-in (local): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -f sample.wav -v Brian`

Mic → LLM→TTS
- mac default playback: `python3 scripts/mic_llm_tts.py`
- Pi ALSA playback: `python3 scripts/mic_llm_tts.py --pi --alsa-dev plughw:1,0`

Render (Node server)
1) Push this repo to GitHub (or GitLab).
2) One-click deploy: https://render.com/deploy?repo=https://github.com/prbodas/pillow_endpoint
   - Or on https://render.com, create a “Web Service”.
   - Connect repo, pick the main branch.
   - Runtime: Node, Build command: `echo no build`, Start command: `node server.js`.
3) After deploy, your public URL will be like `https://tts-waifu.onrender.com`.
  - Test non-stream: `curl -L "https://<your-app>.onrender.com/tts?stream=false" --output waifu.mp3`
   - Test stream (single audio stream): `curl -L "https://<your-app>.onrender.com/tts?stream=true&chunk=32768&gap=20&parts=3&partgap=150" --output waifu_stream.mp3`
  - LLM→TTS: `./scripts/curl_llm_tts.sh -b https://<ai-service>.onrender.com -t "say hello" -v Brian`

Prod AI Service
- render.yaml now defines two services:
  - `tts-waifu`: demo TTS streaming and non-stream (existing basic endpoint).
  - `ai-waifu`: AI endpoint for ASR + LLM + TTS with persistent sessions.
- Configure secrets on Render for `ai-waifu`:
  - Add env var `GEMINI_API_KEY` (secret).
  - Add env var `VOSK_MODEL_DIR` pointing to your Vosk model path if hosting ASR on the service. Hosting models may require a paid plan and/or persistent disk.
    - Alternative: run the ASR locally and only use `/llm` remotely.
- Endpoints (ai-waifu and local server.js):
  - `POST /llm?session=...&llm_model=...&system=...&reset=1` with `{ "text": "..." }` → `{ ok, reply }`.
  - `POST /transcribe?return=original|tts|llm_tts&voice=...&session=...&llm_model=...&system=...` with binary audio body → `multipart/mixed` parts: JSON transcript (+ assistant text when llm_tts), then audio.
  - Aliases: `/ai/llm` and `/ai/transcribe` are available for clarity (on server_ai.js).
  - Direct audio: `POST /llm_tts` → returns `audio/mpeg` of the assistant reply (no multipart). Two modes:
    - JSON: `{ text, voice?, session?, llm_model?, system? }`
    - Audio-in: send binary `audio/wav|mpeg|ogg` body with optional query `voice`, `session`, `llm_model`, `system`; server transcribes, calls Gemini, returns TTS.

Prod Clients
- Mic client (hands-free):
  - `python3 scripts/prod_mic_convo.py` (defaults to local base; flags optional)
  - Example remote: `python3 scripts/prod_mic_convo.py --base https://<ai-service>.onrender.com --session dev1 --voice Joanna`
- Curl helpers:
  - Basic TTS demo (/tts): `./scripts/curl_play.sh -b https://tts-waifu.onrender.com -t "hello" -v Brian`
- LLM→TTS direct audio (/llm_tts):
    - Local (text): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -t "say hello" -v Brian`
    - Local (audio): `./scripts/curl_llm_tts.sh -b http://127.0.0.1:8787 -f sample.wav -v Brian`
    - Render: `./scripts/curl_llm_tts.sh -b https://<ai-service>.onrender.com -t "say hello" -v Joanna`
  - Mic → LLM→TTS (python):
    - mac default playback: `python3 scripts/mic_llm_tts.py`
    - Pi ALSA playback: `python3 scripts/mic_llm_tts.py --pi --alsa-dev plughw:1,0`

 Scripts
 - TTS demo: `./scripts/curl_play.sh`
 - LLM→TTS: `./scripts/curl_llm_tts.sh` (text/file/mic)
 - Mic Python: `python3 scripts/mic_llm_tts.py`

Testing
- Uses Node's built-in test runner (no extra deps).
- Run: `npm test`
- Covers Gemini checks via unit tests: verifies error on missing `GEMINI_API_KEY` and request shaping/response flattening with a mocked `fetch`.

Scripts cleanup
- Demo utilities moved to `scripts/examples/` to declutter.
- See `scripts/README.md` for an overview of available scripts.
