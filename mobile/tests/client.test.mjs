import assert from 'node:assert/strict';
import test from 'node:test';
import { request, ApiError } from '../src/api/client.ts';

test('transport preserves API errors, rejects version mismatch, never invents an offline response', async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response(JSON.stringify({ contract_version: '1.2', recommendations: [] }), { status: 200 });
  assert.deepEqual((await request('/fake')).recommendations, []);
  globalThis.fetch = async () => new Response(JSON.stringify({ contract_version: '1.0' }), { status: 200 });
  await assert.rejects(request('/fake'), /API 1.2/);
  globalThis.fetch = async () => new Response('not found', { status: 503 });
  await assert.rejects(request('/fake'), (error) => error instanceof ApiError && error.status === 503);
  globalThis.fetch = async () => { throw new TypeError('network down'); };
  await assert.rejects(request('/fake'), /Нет связи/);
  globalThis.fetch = async () => { throw new DOMException('aborted', 'AbortError'); };
  await assert.rejects(request('/fake'), /3,5 секунды/);
});
