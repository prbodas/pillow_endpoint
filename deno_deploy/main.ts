// Deno Deploy entrypoint
// Endpoint behavior mirrors the Cloudflare Worker: / and /tts with stream/non-stream
export default {
  fetch: async (request: Request): Promise<Response> => {
    const url = new URL(request.url);

    if (url.pathname === "/" || url.pathname === "") {
      const usage = `TTS Deno Deploy\n\nGET /tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20\n- Returns audio/mpeg of speech.\n- Default text: "I love my waifu".\n- Default stream: false.\n`;
      return new Response(usage, { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    if (url.pathname === "/tts") {
      const streamParam = (url.searchParams.get("stream") || "false").toLowerCase();
      const stream = ["1", "true", "yes"].includes(streamParam);
      const text = url.searchParams.get("text")?.trim() || "I love my waifu";
      const voice = url.searchParams.get("voice") || "Brian";
      const ttsUrl = `https://api.streamelements.com/kappa/v2/speech?voice=${encodeURIComponent(voice)}&text=${encodeURIComponent(text)}`;

      const upstream = await fetch(ttsUrl, { headers: { "user-agent": "tts-deno/1.0" } });
      if (!upstream.ok || !upstream.body) {
        const msg = await safeText(upstream);
        return new Response(`TTS upstream error: ${upstream.status} ${upstream.statusText}\n${msg}`, {
          status: 502,
          headers: { "content-type": "text/plain; charset=utf-8" },
        });
      }

      const contentType = upstream.headers.get("content-type") || "audio/mpeg";

      if (stream) {
        const chunkSize = clampInt(url.searchParams.get("chunk"), 1024, 1024 * 1024, 32 * 1024);
        const gapMs = clampInt(url.searchParams.get("gap"), 0, 2000, 20);
        const buf = await upstream.arrayBuffer();
        const u8 = new Uint8Array(buf);
        const rs = new ReadableStream<Uint8Array>({
          async start(controller) {
            let offset = 0;
            while (offset < u8.length) {
              const end = Math.min(offset + chunkSize, u8.length);
              controller.enqueue(u8.slice(offset, end));
              offset = end;
              if (gapMs > 0 && offset < u8.length) {
                await delay(gapMs);
              }
            }
            controller.close();
          },
        });
        const headers = new Headers();
        headers.set("content-type", contentType);
        headers.set("cache-control", "no-store");
        headers.set("x-stream-mock", "1");
        return new Response(rs, { status: 200, headers });
      } else {
        const arrayBuf = await upstream.arrayBuffer();
        const headers = new Headers();
        headers.set("content-type", contentType);
        headers.set("content-length", String(arrayBuf.byteLength));
        headers.set("cache-control", "no-store");
        return new Response(arrayBuf, { status: 200, headers });
      }
    }

    return new Response("Not found", { status: 404 });
  },
};

function clampInt(value: string | null, min: number, max: number, fallback: number): number {
  const n = value ? parseInt(value, 10) : NaN;
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function delay(ms: number) {
  return new Promise((res) => setTimeout(res, ms));
}

async function safeText(resp: Response): Promise<string> {
  try {
    return await resp.text();
  } catch {
    return "";
  }
}

