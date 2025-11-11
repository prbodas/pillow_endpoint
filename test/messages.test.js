const test = require('node:test');
const assert = require('node:assert');

const {
  buildMessages,
  appendHistory,
  convoStore,
} = require('../server');

test('buildMessages composes system, history, and user message', () => {
  const session = 's1';
  convoStore.clear();
  // No history yet; include system and user
  let msgs = buildMessages(session, 'sys1', 'hello');
  assert.deepStrictEqual(msgs.map(m => m.role), ['system', 'user']);
  assert.strictEqual(msgs[0].content, 'sys1');
  assert.strictEqual(msgs[1].content, 'hello');

  // Append an assistant reply and another user turn
  appendHistory(session, 'sys1', 'hello', 'hi there');
  appendHistory(session, '', 'how are you?', 'fine');
  msgs = buildMessages(session, '', 'next');
  // Should include: (system from store), user, assistant, user, assistant, and current user
  assert.deepStrictEqual(msgs.map(m => m.role), ['system', 'user', 'assistant', 'user', 'assistant', 'user']);
});
