// Node built-in test runner, no external deps
const test = require('node:test');
const assert = require('node:assert');

// Import helpers from the server without starting the listener
const {
  callGemini,
} = require('../server');

test('callGemini throws without GEMINI_API_KEY', async () => {
  const origKey = process.env.GEMINI_API_KEY;
  delete process.env.GEMINI_API_KEY;
  try {
    await assert.rejects(
      () => callGemini({ model: 'gemini-2.0-flash', system: '', messages: [] }),
      /GEMINI_API_KEY not set/
    );
  } finally {
    if (origKey) process.env.GEMINI_API_KEY = origKey;
  }
});

test('callGemini builds correct request and flattens response', async () => {
  const origFetch = global.fetch;
  const origKey = process.env.GEMINI_API_KEY;
  process.env.GEMINI_API_KEY = 'test-key';

  let captured = null;
  global.fetch = async (url, init) => {
    captured = { url, init };
    // Minimal Gemini-like response with parts text
    const body = {
      candidates: [
        { content: { parts: [{ text: 'Hello' }, { text: 'world' }] } }
      ]
    };
    return {
      ok: true,
      status: 200,
      headers: new Map(),
      json: async () => body,
      text: async () => JSON.stringify(body),
    };
  };

  try {
    const messages = [
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'yo' },
    ];
    const text = await callGemini({ model: 'gemini-2.0-flash', system: 'sys extra', messages });
    assert.strictEqual(text, 'Hello world');
    assert.ok(captured, 'fetch should be called');
    assert.match(String(captured.url), /generativelanguage\.googleapis\.com/);
    assert.match(String(captured.url), /gemini-2\.0-flash:generateContent/);
    assert.strictEqual(captured.init.method, 'POST');
    assert.match(captured.init.headers['Content-Type'] || captured.init.headers['content-type'], /application\/json/);
    const sent = JSON.parse(captured.init.body);
    // Ensure messages mapped to Gemini roles (assistant -> model)
    assert.deepStrictEqual(sent.contents.map(c => c.role), ['user', 'model']);
    assert.ok(sent.generationConfig.maxOutputTokens > 0);
    // systemInstruction is only present when provided
    assert.ok(sent.systemInstruction);
  } finally {
    if (origFetch) global.fetch = origFetch; else delete global.fetch;
    if (origKey) process.env.GEMINI_API_KEY = origKey; else delete process.env.GEMINI_API_KEY;
  }
});
