import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';

const root = new URL('../', import.meta.url);
const baseline = JSON.parse(readFileSync(new URL('./fixtures/mobile-polish-visual-baseline.json', import.meta.url), 'utf8'));

test('mobile-polish visuals stay byte-identical except explicitly approved overrides', () => {
  const changed = [];
  const expectedHashes = { ...baseline.git_blob_sha1 };
  for (const [path, approval] of Object.entries(baseline.approved_overrides ?? {})) {
    assert.ok(approval.reason && approval.approved_on, `Missing approval record: ${path}`);
    expectedHashes[path] = approval.git_blob_sha1;
  }
  for (const [path, expected] of Object.entries(expectedHashes)) {
    const bytes = readFileSync(new URL(path, root));
    // Git blob digest works offline, including a source archive without .git.
    const actual = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
    if (actual !== expected) changed.push(path);
  }
  assert.deepEqual(changed, [], 'Review with vxofi before changing the visual baseline; do not auto-update hashes');
});

test('demo selector is explicitly labelled and only mounted at bottom of Profile', () => {
  const profile = readFileSync(new URL('src/app/profile.tsx', root), 'utf8');
  assert.match(profile, /<DemoProfileSelector \/>\s*<\/ScrollView>/);
  const selector = readFileSync(new URL('src/components/DemoProfileSelector.tsx', root), 'utf8');
  assert.match(selector, /Только для демонстрации — синтетические покупатели/);
  for (const path of readdirSync(new URL('src/app/', root)).filter((path) => path.endsWith('.tsx') && path !== 'profile.tsx')) {
    assert.doesNotMatch(readFileSync(new URL(`src/app/${path}`, root), 'utf8'), /DemoProfileSelector/);
  }
});

test('integration does not silently add or remove screens', () => {
  const expected = Object.keys(baseline.git_blob_sha1)
    .filter((path) => path.startsWith('src/app/')).map((path) => path.slice('src/app/'.length)).sort();
  const actual = readdirSync(new URL('src/app/', root)).filter((path) => path.endsWith('.tsx')).sort();
  assert.deepEqual(actual, expected);
});
