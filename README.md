TTS Endpoint (Multiple Hosts)

Endpoints
- GET `/api`:
  - Usage text.
- GET `/api/tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20`:
  - Returns `audio/mpeg` speech of text. Defaults to “I love my waifu”.
  - `stream=true` streams timed chunks (mock streaming). Tunables: `chunk` bytes, `gap` ms.

Local Dev
- Install deps: `npm i` (already done)
- Run with Vercel CLI: `npx vercel dev`
- Test: `curl -L "http://localhost:3000/api/tts?stream=false" --output waifu.mp3`

Render (Node server) — no phone number
1) Push this repo to GitHub (or GitLab).
2) One-click deploy: https://render.com/deploy?repo=https://github.com/prbodas/pillow_endpoint
   - Or on https://render.com, create a “Web Service”.
   - Connect repo, pick the main branch.
   - Runtime: Node, Build command: `echo no build`, Start command: `node server.js`.
3) After deploy, your public URL will be like `https://tts-waifu.onrender.com`.
   - Test non-stream: `curl -L "https://<your-app>.onrender.com/tts?stream=false" --output waifu.mp3`
   - Test stream: `curl -L "https://<your-app>.onrender.com/tts?stream=true&chunk=32768&gap=20" --output waifu_stream.mp3`

Deno Deploy (edge function) — no phone number
1) Go to https://dash.deno.com → New Project → Link GitHub repo.
2) Set entrypoint to `deno_deploy/main.ts` and deploy.
3) Your URL will be like `https://<project>.deno.dev/tts?...`.

Vercel (Edge) — optional
If you already use Vercel, endpoints are under `/api`. See `api/` and `vercel.json`.

Python Client
- `scripts/play_waifu.py` can target any host. Examples:
  - Render: `python3 scripts/play_waifu.py --base https://<your-app>.onrender.com`
  - Deno: `python3 scripts/play_waifu.py --base https://<project>.deno.dev`
  - Local: `python3 scripts/play_waifu.py --base http://localhost:8787` (Node) or `--base http://localhost:3000/api` (Vercel dev)
