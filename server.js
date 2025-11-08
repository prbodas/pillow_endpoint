// Zero-dependency Node HTTP server suitable for Render free plan
// Provides / and /tts with stream and non-stream modes
const http = require('node:http');
const { URL } = require('node:url');

const PORT = process.env.PORT || 8787;

const server = http.createServer(async (req, res) => {
  try {
    if (!req.url) {
      res.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('Bad Request');
      return;
    }
    const url = new URL(req.url, `http://${req.headers.host}`);

    // Basic CORS support for hardware and browsers
    setCors(res);
    if (req.method === 'OPTIONS') {
      res.writeHead(204, corsHeaders());
      res.end();
      return;
    }

    if (url.pathname === '/' || url.pathname === '') {
      const usage = `TTS Node Server\n\nGET /tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20\n- Returns audio/mpeg of speech.\n- Default text: "I love my waifu".\n- Default stream: false.\n`;
      res.writeHead(200, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
      res.end(usage);
      return;
    }

    if (url.pathname === '/health') {
      res.writeHead(200, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
      res.end('ok');
      return;
    }

    if (url.pathname === '/tts') {
      const streamParam = (url.searchParams.get('stream') || 'false').toLowerCase();
      const stream = ['1', 'true', 'yes'].includes(streamParam);
      const text = (url.searchParams.get('text') || 'I love my waifu').trim();
      const voice = url.searchParams.get('voice') || 'Brian';
      const ttsUrl = `https://api.streamelements.com/kappa/v2/speech?voice=${encodeURIComponent(voice)}&text=${encodeURIComponent(text)}`;

      const upstream = await fetch(ttsUrl, { headers: { 'user-agent': 'tts-node/1.0' } });
      if (!upstream.ok || !upstream.body) {
        const msg = await safeText(upstream);
        res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
        res.end(`TTS upstream error: ${upstream.status} ${upstream.statusText}\n${msg}`);
        return;
      }

      const contentType = upstream.headers.get('content-type') || 'audio/mpeg';

      if (stream) {
        const chunkSize = clampInt(url.searchParams.get('chunk'), 1024, 1024 * 1024, 32 * 1024);
        const gapMs = clampInt(url.searchParams.get('gap'), 0, 2000, 20);
        const buf = new Uint8Array(await upstream.arrayBuffer());

        res.writeHead(200, {
          'content-type': contentType,
          'cache-control': 'no-store',
          'transfer-encoding': 'chunked',
          'connection': 'keep-alive',
          'x-accel-buffering': 'no',
          'x-stream-mock': '1',
          ...corsHeaders(),
        });
        let offset = 0;
        while (offset < buf.length) {
          const end = Math.min(offset + chunkSize, buf.length);
          const chunk = buf.subarray(offset, end);
          res.write(chunk);
          offset = end;
          if (gapMs > 0 && offset < buf.length) {
            await delay(gapMs);
          }
        }
        res.end();
        return;
      } else {
        const arr = await upstream.arrayBuffer();
        res.writeHead(200, {
          'content-type': contentType,
          'content-length': String(arr.byteLength),
          'cache-control': 'no-store',
          ...corsHeaders(),
        });
        res.end(Buffer.from(arr));
        return;
      }
    }

    res.writeHead(404, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  } catch (err) {
    res.writeHead(500, { ...corsHeaders(), 'content-type': 'text/plain; charset=utf-8' });
    res.end('Server error');
    console.error(err);
  }
});

server.listen(PORT, () => {
  console.log(`Server listening on http://0.0.0.0:${PORT}`);
});

// Increase keep-alive to help proxies with chunked streams
server.keepAliveTimeout = 65_000;
server.headersTimeout = 66_000;

function clampInt(value, min, max, fallback) {
  const n = value ? parseInt(String(value), 10) : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function delay(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

async function safeText(resp) {
  try {
    return await resp.text();
  } catch {
    return '';
  }
}

function corsHeaders() {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,OPTIONS,HEAD',
    'access-control-allow-headers': '*',
  };
}

function setCors(res) {
  const headers = corsHeaders();
  for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
}
