import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../', import.meta.url);
const baseline = JSON.parse(readFileSync(new URL('./fixtures/mobile-polish-visual-baseline.json', import.meta.url), 'utf8'));

test('approved mobile-polish screens, components, layout data and assets stay byte-identical', () => {
  const changed = [];
  for (const [path, expected] of Object.entries(baseline.git_blob_sha1)) {
    const bytes = readFileSync(new URL(path, root));
    // Git blob digest works offline, including a source archive without .git.
    const actual = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
    if (actual !== expected) changed.push(path);
  }
  assert.deepEqual(changed, [], 'Review with vxofi before changing the visual baseline; do not auto-update hashes');
});

test('integration does not silently add or remove screens', () => {
  const expected = Object.keys(baseline.git_blob_sha1)
    .filter((path) => path.startsWith('src/app/')).map((path) => path.slice('src/app/'.length)).sort();
  const actual = readdirSync(new URL('src/app/', root)).filter((path) => path.endsWith('.tsx')).sort();
  assert.deepEqual(actual, expected);
});
