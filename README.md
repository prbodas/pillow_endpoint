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

Local Dev
- Install deps: `npm i`
- Start server: `npm start`
- Test: `curl -L "http://localhost:8787/tts?stream=false" --output waifu.mp3`

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
     - Play via Python client: `python3 scripts/play_waifu.py --base https://<your-app>.onrender.com --server-parts 3 --multipart`

 Python Client
 - `scripts/play_waifu.py` can target any host. Examples:
   - Render: `python3 scripts/play_waifu.py --base https://<your-app>.onrender.com`
  - Local: `python3 scripts/play_waifu.py --base http://localhost:8787`
