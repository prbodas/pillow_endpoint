// Dedicated AI server (no /tts demo). Exposes /health, /llm, /transcribe.
const http = require('node:http');
const { URL } = require('node:url');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const PORT = process.env.PORT || 8787;

const convoStore = new Map();
const MAX_HISTORY_MESSAGES = 20;
const DEFAULT_SYSTEM = "Return plain text only. No markdown, emojis, code blocks, or lists. Keep replies short (1-2 sentences) unless asked otherwise.";

const server = http.createServer(async (req, res) => {
  try {
    if (!req.url) {
      res.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('Bad Request');
      return;
    }
    const url = new URL(req.url, `http://${req.headers.host}`);

    setCors(res);
    if (req.method === 'OPTIONS') {
      res.writeHead(204, corsHeaders());
      res.end();
      return;
    }
    const isHead = req.method === 'HEAD';

    if (url.pathname === '/' || url.pathname === '') {
      const usage = `AI Node Server\n\nPOST /llm — chat with persistent sessions (Gemini)\nPOST /transcribe — ASR (Vosk) + JSON transcript; supports llm_tts to speak replies.\n`;
      res.writeHead(200, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
      if (isHead) return res.end();
      res.end(usage);
      return;
    }

    if (url.pathname === '/health' || url.pathname === '/health/' || url.pathname === '/healthz' || url.pathname === '/readyz') {
      res.writeHead(200, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
      if (isHead) return res.end();
      res.end('ok');
      return;
    }

    // Support /ai/* aliases for clarity
    const pathName = url.pathname.startsWith('/ai/') ? url.pathname.slice(3) : url.pathname;

    if (pathName === '/llm') {
      if (req.method === 'GET') {
        const help = {
          method: 'POST',
          path: '/llm',
          body: { text: 'your plain text' },
          query: {
            session: 'conversation id (optional, default: default)',
            llm_model: 'Gemini model id (default: gemini-2.0-flash)',
            system: 'optional system prompt',
            reset: 'true to clear history for session',
          },
          note: 'Uses Google Gemini with server-side API key.'
        };
        res.writeHead(200, { ...corsHeaders(), 'content-type': 'application/json' });
        return res.end(JSON.stringify(help, null, 2));
      }
      if (req.method !== 'POST') {
        res.writeHead(405, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end('Method Not Allowed');
      }

      let data = {};
      try { data = await readJson(req); } catch (e) {
        res.writeHead(400, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end('Invalid JSON');
      }
      const userText = (data && typeof data.text === 'string') ? data.text : '';
      const sessionId = url.searchParams.get('session') || data.session || 'default';
      const model = url.searchParams.get('llm_model') || data.llm_model || 'gemini-2.0-flash';
      const systemParam = url.searchParams.get('system') || data.system || '';
      const reset = ['1','true','yes'].includes((url.searchParams.get('reset') || data.reset || '').toString().toLowerCase());
      if (reset) convoStore.delete(sessionId);

      try {
        const messages = buildMessages(sessionId, systemParam, userText);
        const sysText = systemParam || (convoStore.get(sessionId)?.system) || '';
        const mergedSystem = [sysText, DEFAULT_SYSTEM].filter(Boolean).join("\n\n");
        const reply = await callGemini({ model, system: mergedSystem, messages });
        appendHistory(sessionId, systemParam, userText, reply);
        res.writeHead(200, { ...corsHeaders(), 'content-type': 'application/json' });
        return res.end(JSON.stringify({ ok: true, provider: 'gemini', session: sessionId, model, user: userText, reply }, null, 2));
      } catch (e) {
        const payload = { ok: false, error: String(e?.message || e) };
        res.writeHead(502, { ...corsHeaders(), 'content-type': 'application/json' });
        return res.end(JSON.stringify(payload));
      }
    }

    if (pathName === '/transcribe') {
      if (req.method === 'GET') {
        const help = {
          method: 'POST',
          path: '/transcribe',
          expects: 'binary audio body (e.g., audio/mpeg or audio/wav) or any audio/*',
          query: {
            return: 'original | tts | none | llm_tts (default: original)',
            voice: 'TTS voice (when return=tts/llm_tts, default Brian)'
          },
          env: { VOSK_MODEL_DIR: 'Path to local Vosk model directory (required for ASR)' }
        };
        res.writeHead(200, { ...corsHeaders(), 'content-type': 'application/json' });
        return res.end(JSON.stringify(help, null, 2));
      }
      if (req.method !== 'POST') {
        res.writeHead(405, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end('Method Not Allowed');
      }

      const modelDir = process.env.VOSK_MODEL_DIR;
      if (!modelDir) {
        res.writeHead(500, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end('VOSK_MODEL_DIR is not set');
      }
      try {
        const conf = path.join(modelDir, 'conf', 'model.conf');
        if (!fs.existsSync(conf)) throw new Error(`Missing model files at ${conf}`);
      } catch (e) {
        res.writeHead(500, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end(`VOSK model path invalid: ${String(e?.message || e)}`);
      }

      const chunks = [];
      let size = 0;
      await new Promise((resolve, reject) => {
        req.on('data', (c) => { chunks.push(c); size += c.length; });
        req.on('end', resolve);
        req.on('error', reject);
      });
      const body = Buffer.concat(chunks, size);
      const ctypeIn = (req.headers['content-type'] || 'application/octet-stream').toString();
      const suffix = guessExt(ctypeIn);
      const tmp = await writeTemp(body, suffix);

      let transcript;
      try { transcript = await runVosk(tmp.path, modelDir); }
      catch (e) {
        res.writeHead(500, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
        return res.end('Transcription error: ' + String(e?.message || e));
      }

      const returnMode = (url.searchParams.get('return') || 'original').toLowerCase();
      if (returnMode === 'none') {
        res.writeHead(200, { ...corsHeaders(), 'content-type': 'application/json', 'cache-control': 'no-store, no-transform' });
        return res.end(JSON.stringify({ transcript }, null, 2));
      }

      let outAudio = body;
      let outType = ctypeIn;
      let llm = null;
      if (returnMode === 'tts') {
        const text = (transcript && transcript.text) ? String(transcript.text).trim() || 'I love my waifu' : 'I love my waifu';
        const voice = url.searchParams.get('voice') || 'Brian';
        try {
          const { audio, contentType } = await fetchTTS(voice, text);
          outAudio = audio; outType = contentType;
        } catch (_) { outAudio = body; outType = ctypeIn; }
      } else if (returnMode === 'llm_tts' || returnMode === 'llm-tts') {
        const sessionId = getSessionId(url, req);
        const model = url.searchParams.get('llm_model') || 'gemini-2.0-flash';
        const systemParam = url.searchParams.get('system') || '';
        const reset = ['1', 'true', 'yes'].includes((url.searchParams.get('reset')||'').toLowerCase());
        if (reset) convoStore.delete(sessionId);
        const userText = (transcript && transcript.text) ? String(transcript.text).trim() : '';
        const voice = url.searchParams.get('voice') || 'Brian';
        try {
          const messages = buildMessages(sessionId, systemParam, userText);
          const sysText = systemParam || (convoStore.get(sessionId)?.system) || '';
          const mergedSystem = [sysText, DEFAULT_SYSTEM].filter(Boolean).join("\n\n");
          const reply = await callGemini({ model, system: mergedSystem, messages });
          appendHistory(sessionId, systemParam, userText, reply);
          llm = reply;
          const { audio, contentType } = await fetchTTS(voice, reply || 'I love my waifu');
          outAudio = audio; outType = contentType;
        } catch (_) { outAudio = body; outType = ctypeIn; }
      }

      const boundary = `trans-${Date.now().toString(16)}`;
      res.writeHead(200, {
        ...corsHeaders(),
        'content-type': `multipart/mixed; boundary=${boundary}`,
        'cache-control': 'no-store, no-transform',
        'x-boundary': boundary,
      });
      res.write(Buffer.from(`--${boundary}\r\nContent-Type: application/json; charset=utf-8\r\n\r\n`, 'utf8'));
      res.write(Buffer.from(JSON.stringify({ transcript, llm }, null, 2), 'utf8'));
      res.write(Buffer.from(`\r\n--${boundary}\r\nContent-Type: ${outType}\r\nContent-Length: ${outAudio.length}\r\n\r\n`, 'utf8'));
      res.write(outAudio);
      res.write(Buffer.from(`\r\n--${boundary}--\r\n`, 'utf8'));
      return res.end();
    }

    res.writeHead(404, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  } catch (err) {
    res.writeHead(500, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
    res.end('Server error');
    console.error(err);
  }
});

if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`AI Server listening on http://0.0.0.0:${PORT}`);
  });
  server.keepAliveTimeout = 65_000;
  server.headersTimeout = 66_000;
}

function clampInt(value, min, max, fallback) {
  const n = value ? parseInt(String(value), 10) : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function delay(ms) { return new Promise((res) => setTimeout(res, ms)); }

async function safeText(resp) { try { return await resp.text(); } catch { return ''; } }

function corsHeaders() {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS,HEAD',
    'access-control-allow-headers': '*',
  };
}

function setCors(res) { const headers = corsHeaders(); for (const [k, v] of Object.entries(headers)) res.setHeader(k, v); }

function readJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', (c) => { chunks.push(c); size += c.length; });
    req.on('end', () => {
      try { const buf = Buffer.concat(chunks, size); const j = JSON.parse(buf.toString('utf8')); resolve(j); }
      catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

function guessExt(ctype) {
  const t = (ctype || '').toLowerCase();
  if (t.includes('wav')) return '.wav';
  if (t.includes('mpeg') || t.includes('mp3')) return '.mp3';
  if (t.includes('ogg')) return '.ogg';
  if (t.includes('aac')) return '.aac';
  return '.bin';
}

function writeTemp(buf, suffix) {
  return new Promise((resolve, reject) => {
    const p = path.join(os.tmpdir(), `in-${Date.now().toString(16)}${suffix || ''}`);
    fs.writeFile(p, buf, (err) => { if (err) return reject(err); resolve({ path: p }); });
  });
}

function runVosk(inputPath, modelDir) {
  return new Promise((resolve, reject) => {
    const venvPy = process.env.VOSK_PYTHON || path.join(process.cwd(), '.venv', 'bin', 'python3');
    const pythonCmd = fs.existsSync(venvPy) ? venvPy : 'python3';
    const proc = spawn(pythonCmd, [path.join(__dirname, 'scripts', 'vosk_transcribe.py'), '--model', modelDir, '--input', inputPath], {
      env: process.env, stdio: ['ignore', 'pipe', 'pipe']
    });
    let out = ''; let err = '';
    proc.stdout.setEncoding('utf8'); proc.stdout.on('data', (d) => out += d);
    proc.stderr.setEncoding('utf8'); proc.stderr.on('data', (d) => err += d);
    proc.on('close', (code) => {
      if (code !== 0) return reject(new Error(err || `vosk script exited ${code}`));
      try { const j = JSON.parse(out); resolve(j); } catch (e) { reject(e); }
    });
  });
}

async function callGemini({ model, system, messages, temperature = 0.9, maxTokens = 256, topP = 0.95 }) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error('GEMINI_API_KEY not set');
  const api = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(key)}`;
  const contents = [];
  for (const m of messages) {
    const role = m.role === 'assistant' ? 'model' : 'user';
    contents.push({ role, parts: [{ text: String(m.content || '') }] });
  }
  const body = { contents, generationConfig: { temperature, maxOutputTokens: maxTokens, topP }, ...(system ? { systemInstruction: { role: 'system', parts: [{ text: String(system) }] } } : {}) };
  const res = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) { const txt = await res.text(); throw new Error(`Gemini ${res.status}: ${txt}`); }
  const json = await res.json().catch(() => ({}));
  const parts = json?.candidates?.[0]?.content?.parts || [];
  const texts = Array.isArray(parts) ? parts.map((p) => (typeof p?.text === 'string' ? p.text : '')).filter(Boolean) : [];
  const text = texts.join(' ').trim();
  return text;
}

async function fetchTTS(voice, text) {
  const t = await fetch(`https://api.streamelements.com/kappa/v2/speech?voice=${encodeURIComponent(voice)}&text=${encodeURIComponent(text)}`, { headers: { 'user-agent': 'tts-node/1.0' } });
  const arr = await t.arrayBuffer();
  return { audio: Buffer.from(arr), contentType: t.headers.get('content-type') || 'audio/mpeg' };
}

function getSessionId(url, req) { return url.searchParams.get('session') || req.headers['x-session-id'] || 'default'; }
function buildMessages(sessionId, systemParam, userText) {
  const state = convoStore.get(sessionId) || { system: '', messages: [] };
  const system = systemParam || state.system || '';
  const msgs = []; if (system) msgs.push({ role: 'system', content: system });
  for (const m of state.messages || []) msgs.push(m);
  if (userText) msgs.push({ role: 'user', content: userText });
  return msgs;
}
function appendHistory(sessionId, systemParam, userText, assistantText) {
  const prev = convoStore.get(sessionId) || { system: '', messages: [] };
  const system = systemParam || prev.system || '';
  const messages = prev.messages.slice();
  if (userText) messages.push({ role: 'user', content: userText });
  if (assistantText) messages.push({ role: 'assistant', content: assistantText });
  const trimmed = messages.slice(-MAX_HISTORY_MESSAGES);
  convoStore.set(sessionId, { system, messages: trimmed, updatedAt: Date.now() });
}

module.exports = { server, callGemini, buildMessages, appendHistory, convoStore, DEFAULT_SYSTEM };

