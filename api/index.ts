export const config = { runtime: "edge" };

export default async function handler(): Promise<Response> {
  const usage = `TTS Vercel Edge\n\n` +
    `GET /api/tts?stream=true|false&text=...&voice=...&chunk=32768&gap=20\n` +
    `- Returns audio/mpeg of speech.\n` +
    `- Default text: "I love my waifu".\n` +
    `- Default stream: false.\n`;
  return new Response(usage, { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } });
}

