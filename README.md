TTS Endpoint (Render)

Endpoints
- GET `/`:
  - Usage text.
- GET `/tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20`:
  - Optional `parts`: repeat the audio N times in one stream (default 1).
  - Optional `partgap`: ms delay between parts (default 150).
  - Returns `audio/mpeg` speech of text. Defaults to “I love my waifu”.
  - `stream=true` streams timed chunks (mock streaming). Tunables: `chunk` bytes, `gap` ms.
  - Optional `multipart=1`: respond with `multipart/mixed` and emit N separate parts in one HTTP response.
 - GET `/transcribe`:
   - Returns a small JSON guide for how to call the POST endpoint.
 - POST `/transcribe?return=original|tts|none&voice=Brian` with raw audio body:
   - Uses local Vosk to transcribe the audio (no external calls for ASR).
   - Returns `multipart/mixed`: part 1 is JSON transcript, part 2 is audio.
   - `return` controls the audio part: `original` (echo input), `tts` (speech of transcript via proxy TTS), or `none` (JSON only).

Local Dev
- Install deps: `npm i`
- Start server: `npm start`
- Test: `curl -L "http://localhost:8787/tts?stream=false" --output waifu.mp3`

Vosk setup (offline, private ASR)
- Install Python deps: `pip3 install vosk sounddevice numpy`
- Install ffmpeg (for audio conversion): macOS `brew install ffmpeg` (or your OS package manager)
- Download a Vosk model (small English example): https://alphacephei.com/vosk/models
  - Unzip and set env var to the model directory, e.g. `export VOSK_MODEL_DIR=/path/to/vosk-model-small-en-us-0.15`

Transcription test
- JSON only: `curl -s -X POST --data-binary @sample.wav -H 'Content-Type: audio/wav' 'http://127.0.0.1:8787/transcribe?return=none' | jq .`
- Multipart with original audio echo: `python3 scripts/examples/call_transcribe.py --file sample.wav --play`
- Multipart with TTS audio of the transcript: `python3 scripts/examples/call_transcribe.py --file sample.wav --return tts --play`

Mic capture + transcribe (local)
- macOS will announce and capture from default mic, then transcribe:
  - `python3 scripts/mic_transcribe.py --play`
  - Options: `--max-seconds 10`, `--return tts`, `--voice Brian`
  - Grant Terminal mic permissions if prompted.

LLM talkback (Gemini)
- Keep your API key private. Do NOT commit it. Create `.env.local` with:
  - `GEMINI_API_KEY=AIza...`
- Start with `scripts/run_local.sh` so the env is loaded.
- File-based (persistent session): `python3 scripts/call_transcribe.py --file sample.wav --return llm_tts --voice Brian --session cli1`
- Mic-based (persistent session): `python3 scripts/mic_transcribe.py --return llm_tts --voice Brian --session mic1 --play`
- Hands-free voice chat loop (female voice): `python3 scripts/mic_convo.py --voice Joanna --session mic1`
  - Commands inside the tool: press Enter to speak, `/reset` to clear, `/voice Amy` to switch voice, `/quit` to exit.
- Test LLM completion alone (no audio):
  - One-shot: `python3 scripts/llm_chat.py --text "Hey there!"`
  - Interactive: `python3 scripts/llm_chat.py --session chat1`
  - Reset history: add `&reset=1` to the transcribe URL or change session id.

Render (Node server) — no phone number
1) Push this repo to GitHub (or GitLab).
2) One-click deploy: https://render.com/deploy?repo=https://github.com/prbodas/pillow_endpoint
   - Or on https://render.com, create a “Web Service”.
   - Connect repo, pick the main branch.
   - Runtime: Node, Build command: `echo no build`, Start command: `node server.js`.
3) After deploy, your public URL will be like `https://tts-waifu.onrender.com`.
  - Test non-stream: `curl -L "https://<your-app>.onrender.com/tts?stream=false" --output waifu.mp3`
   - Test stream (single audio stream): `curl -L "https://<your-app>.onrender.com/tts?stream=true&chunk=32768&gap=20&parts=3&partgap=150" --output waifu_stream.mp3`
  - Test multipart (3 distinct parts):
     - `curl -v "https://<your-app>.onrender.com/tts?stream=true&parts=3&multipart=1" -o multipart.bin`
     - Play via Python client: `python3 scripts/examples/play_waifu.py --base https://<your-app>.onrender.com --server-parts 3 --multipart`

Prod AI Service
- render.yaml now defines two services:
  - `tts-waifu`: demo TTS streaming and non-stream (existing basic endpoint).
  - `ai-waifu`: AI endpoint for ASR + LLM + TTS with persistent sessions.
- Configure secrets on Render for `ai-waifu`:
  - Add env var `GEMINI_API_KEY` (secret).
  - Add env var `VOSK_MODEL_DIR` pointing to your Vosk model path if hosting ASR on the service. Hosting models may require a paid plan and/or persistent disk.
    - Alternative: run the ASR locally and only use `/llm` remotely.
- Endpoints (ai-waifu):
  - `POST /llm?session=...&llm_model=...&system=...&reset=1` with `{ "text": "..." }` → `{ ok, reply }`.
  - `POST /transcribe?return=original|tts|llm_tts&voice=...&session=...&llm_model=...&system=...` with binary audio body → `multipart/mixed` parts: JSON transcript (+ assistant text when llm_tts), then audio.
  - Aliases: `/ai/llm` and `/ai/transcribe` are available for clarity.

Prod Client
- Minimal client aimed at lightweight devices:
  - `scripts/prod_mic_convo.py` records locally and sends to `ai-waifu` (`/transcribe?return=llm_tts`). All compute runs on the server.
  - Example: `python3 scripts/prod_mic_convo.py --base https://<ai-service>.onrender.com --session dev1 --voice Joanna`
  - Set default base via env: `export AI_BASE=https://<ai-service>.onrender.com`

 Python Client
 - `scripts/examples/play_waifu.py` can target any host. Examples:
   - Render: `python3 scripts/examples/play_waifu.py --base https://<your-app>.onrender.com`
   - Local: `python3 scripts/examples/play_waifu.py --base http://localhost:8787`

Testing
- Uses Node's built-in test runner (no extra deps).
- Run: `npm test`
- Covers Gemini checks via unit tests: verifies error on missing `GEMINI_API_KEY` and request shaping/response flattening with a mocked `fetch`.

Scripts cleanup
- Demo utilities moved to `scripts/examples/` to declutter.
- See `scripts/README.md` for an overview of available scripts.
