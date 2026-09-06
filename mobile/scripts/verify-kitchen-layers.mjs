import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PNG } from 'pngjs';

const mobileRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = resolve(mobileRoot, 'src/data/kitchenLayers.ts');
const sourcePath = resolve(mobileRoot, 'assets/kitchen/kitchen-full.png');
const manifest = readFileSync(manifestPath, 'utf8');
const source = PNG.sync.read(readFileSync(sourcePath));

const layerPattern = /\{ id: '([^']+)', rect: \[(\d+), (\d+), (\d+), (\d+)\], source: require\('([^']+)'\) \}/g;
const layers = [...manifest.matchAll(layerPattern)].map((match) => ({
  id: match[1],
  rect: match.slice(2, 6).map(Number),
  path: resolve(dirname(manifestPath), match[6]),
}));

assert.ok(layers.length > 1, 'kitchen layer manifest was not parsed');
const assembled = new PNG({ width: source.width, height: source.height });

for (const layer of layers) {
  const image = PNG.sync.read(readFileSync(layer.path));
  const [cellX, cellY, cellWidth, cellHeight] = layer.rect;
  assert.equal(image.width, cellWidth * 10, `${layer.id}: unexpected width`);
  assert.equal(image.height, cellHeight * 10, `${layer.id}: unexpected height`);

  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      const from = (y * image.width + x) * 4;
      if (image.data[from + 3] === 0) continue;
      assert.equal(image.data[from + 3], 255, `${layer.id}: partial alpha is not grid-exact`);
      const targetX = cellX * 10 + x;
      const targetY = cellY * 10 + y;
      const to = (targetY * assembled.width + targetX) * 4;
      assert.equal(assembled.data[to + 3], 0, `${layer.id}: overlaps another base layer`);
      assembled.data.set(image.data.subarray(from, from + 4), to);
    }
  }
}

assert.equal(assembled.data.length, source.data.length);
let changedBytes = 0;
for (let index = 0; index < source.data.length; index += 1) {
  if (source.data[index] !== assembled.data[index]) changedBytes += 1;
}
assert.equal(changedBytes, 0, 'assembled kitchen differs from kitchen-full.png');
console.log(`Kitchen layers: ${layers.length}; changed bytes: ${changedBytes}`);
