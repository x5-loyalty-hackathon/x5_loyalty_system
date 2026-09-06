import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

// Модули с косметикой тянут PNG через require и потому не исполняются в Node.
// Разбираем исходник текстом — тем же приёмом, что verify-kitchen-layers.mjs.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const upgradesSrc = readFileSync(resolve(root, 'src/data/kitchenUpgrades.ts'), 'utf8');
const layersSrc = readFileSync(resolve(root, 'src/data/kitchenLayers.ts'), 'utf8');

const upgrades = [...upgradesSrc.matchAll(
  /id: `\$\{SAGE\}\/([\w-]+)`, layer: '([\w-]+)', level: (\d+),/g,
)].map(([, id, layer, level]) => ({ id, layer, level: Number(level) }));

const layerIds = new Set(
  [...layersSrc.matchAll(/\{ id: '([\w-]+)', rect:/g)].map(([, id]) => id),
);

test('каталог косметики разобран', () => {
  assert.equal(upgrades.length, 10);
  assert.ok(layerIds.size >= 10);
});

test('каждый предмет подменяет существующий слой комнаты', () => {
  for (const upgrade of upgrades) {
    assert.ok(layerIds.has(upgrade.layer), `нет слоя ${upgrade.layer} для ${upgrade.id}`);
  }
});

test('один слой не занят двумя предметами одного набора', () => {
  const layers = upgrades.map((upgrade) => upgrade.layer);
  assert.equal(new Set(layers).size, layers.length);
});

test('лестница идёт через уровень и заканчивается печью', () => {
  const levels = upgrades.map((upgrade) => upgrade.level);
  assert.deepEqual(levels, [...levels].sort((a, b) => a - b), 'уровни должны расти');
  for (let index = 1; index < levels.length; index += 1) {
    assert.equal(levels[index] - levels[index - 1], 2, 'предметы открываются через уровень');
  }
  assert.equal(levels[0], 2, 'первый предмет — на втором уровне');
  assert.equal(upgrades.at(-1).layer, 'stove', 'печь открывается последней');
});

test('разблокировка по уровню растёт по одному', () => {
  const openedAt = (level) => upgrades.filter((upgrade) => level >= upgrade.level).length;
  assert.equal(openedAt(1), 0, 'на первом уровне не открыто ничего');
  assert.equal(openedAt(2), 1);
  assert.equal(openedAt(5), 2, 'нечётный уровень не открывает новое');
  assert.equal(openedAt(20), upgrades.length);
});
