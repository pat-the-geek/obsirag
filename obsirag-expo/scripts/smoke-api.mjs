import assert from 'node:assert/strict';

const baseUrl = process.env.OBSIRAG_BACKEND_URL || 'http://localhost:8000';

async function request(path, init = {}) {
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, init);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`Backend unreachable at ${baseUrl}. Start the API server or set OBSIRAG_BACKEND_URL. Original error: ${reason}`);
  }
  const text = await response.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = text;
  }
  return { response, payload };
}

async function main() {
  const health = await request('/api/v1/health');
  assert.equal(health.response.status, 200);
  assert.equal(health.payload.status, 'ok');

  const session = await request('/api/v1/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accessToken: '' }),
  });
  assert.equal(session.response.status, 200);
  assert.equal(session.payload.authenticated, true);

  const conversation = await request('/api/v1/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  assert.equal(conversation.response.status, 200);
  assert.ok(conversation.payload.id);

  console.log(`Smoke API OK on ${baseUrl}`);
  console.log(`Conversation created: ${conversation.payload.id}`);
}

main().catch((error) => {
  console.error('Smoke API failed');
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});