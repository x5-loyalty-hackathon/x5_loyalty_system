import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import { kitchenProducts, mergeKitchenProducts, purchasedKitchenProducts } from '../src/domain/kitchen.ts';

// Exercise the actual TSX and retained PanResponder closures. These hook/RN
// doubles are intentionally not a native layout or gesture recognizer test.
function sheetHarness() {
  const refs = [];
  let cursor = 0;
  const jsx = (type, props) => ({ type, props });
  const mocks = {
    react: { useRef: (value) => {
      const index = cursor++;
      return refs[index] ?? (refs[index] = { current: value });
    } },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'react-native': {
      Animated: { View: 'AnimatedView' }, Pressable: 'Pressable', View: 'View',
      StyleSheet: { create: (value) => value },
      PanResponder: { create: (handlers) => ({ panHandlers: handlers }) },
    },
    '../theme/tokens': { color: {} },
  };
  const source = readFileSync(new URL('../src/components/KitchenSheet.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: (id) => {
    assert.ok(id in mocks, `Unexpected import: ${id}`); return mocks[id];
  } });
  const height = { value: 220, setValue(value) { this.value = value; },
    stopAnimation(callback) { callback(this.value); } };
  return {
    height,
    render(props) {
      cursor = 0;
      return exports.KitchenSheet({ height, collapsedHeight: 220, expandedHeight: 221,
        expanded: false, children: null, ...props }).props.children[0].props;
    },
  };
}

test('kitchen sheet uses measured height and latest callback, not first-render limits', () => {
  const harness = sheetHarness();
  let obsoleteCalls = 0;
  const calls = [];
  const original = harness.render({ onChange: () => obsoleteCalls++ });
  const measured = harness.render({ expandedHeight: 450, onChange: (next) => calls.push(next) });
  assert.equal(measured.onPanResponderMove, original.onPanResponderMove);
  original.onPanResponderGrant();
  original.onPanResponderMove(null, { dy: -100 });
  assert.equal(harness.height.value, 320, 'must not be clamped to initial 221');
  original.onPanResponderRelease(null, { dy: -100, vy: 0 });
  assert.deepEqual(calls, [false], 'must use the new midpoint (335)');
  assert.equal(obsoleteCalls, 0);
});

test('kitchen sheet clamps after resize and snaps interrupted drags to current state', () => {
  const harness = sheetHarness();
  const calls = [];
  const handle = harness.render({ expandedHeight: 600, onChange: (next) => calls.push(next) });
  harness.render({ expandedHeight: 400, expanded: true, onChange: (next) => calls.push(next) });
  handle.onPanResponderGrant();
  handle.onPanResponderMove(null, { dy: -900 });
  assert.equal(harness.height.value, 400);
  handle.onPanResponderMove(null, { dy: 900 });
  assert.equal(harness.height.value, 220);
  handle.onPanResponderRelease(null, { dy: 0, vy: -1 });
  assert.deepEqual(calls, [true]);
  handle.onPanResponderTerminate();
  assert.equal(harness.height.value, 400);
});

test('kitchen handle also works without a drag', () => {
  const harness = sheetHarness();
  let expanded = false;
  const handle = harness.render({ onChange: (next) => { expanded = next; } });
  assert.equal(handle.accessibilityRole, 'button');
  assert.equal(handle.accessibilityState.expanded, false);
  handle.onPress();
  assert.equal(expanded, true);
});

test('kitchen receipt list keeps unknown art IDs and deduplicates without stock claims', () => {
  const items = [
    { name: 'Томаты', ingredient_ids: ['tomato'] },
    { name: 'Другие томаты', ingredient_ids: ['tomato'] },
    { name: 'Без рисунка', ingredient_ids: ['not_in_sprites'] },
  ];
  const before = structuredClone(items);
  assert.deepEqual(kitchenProducts(items), [
    { id: 'tomato', name: 'Томаты' }, { id: 'not_in_sprites', name: 'Без рисунка' },
  ]);
  assert.deepEqual(items, before);
});

test('purchased kitchen display maps only selected SKU; ready is not raw ingredients', () => {
  const product = { sku_id: 'onion_sale', name: 'Лук, 500 г' };
  const meal = { cook_variant: { ingredients: [
    { ingredient_id: 'onion', product_options: [product] },
  ] } };
  assert.deepEqual(purchasedKitchenProducts(meal, 'cook', [product]), [{ id: 'onion', name: product.name }]);
  const ready = purchasedKitchenProducts(meal, 'ready', [{ sku_id: 'ready_soup', name: 'Готовый суп' }]);
  assert.deepEqual(ready, [{ id: 'ready:ready_soup', name: 'Готовый суп' }]);
  assert.deepEqual(purchasedKitchenProducts(meal, 'cook', [{ sku_id: 'unmapped', name: 'Товар' }]),
    [{ id: 'sku:unmapped', name: 'Товар' }]);
  const before = [{ id: 'onion', name: 'Прежний лук' }];
  const updated = mergeKitchenProducts(before, purchasedKitchenProducts(meal, 'cook', [product]));
  assert.equal(updated.length, 1);
  assert.equal(updated[0].name, product.name);
  assert.equal(before[0].name, 'Прежний лук');
});

test('incoming slot fallback preserves every display item and fits unique slots deterministically', () => {
  const cache = {};
  function load(name) {
    if (cache[name]) return cache[name];
    assert.ok(['kitchenPlacement', 'kitchenSlots', 'productSprites'].includes(name));
    const source = readFileSync(new URL(`../src/data/${name}.ts`, import.meta.url), 'utf8');
    const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
    const exports = {};
    runInNewContext(compiled, { exports, require: (id) => {
      if (id.endsWith('.png')) {
        assert.ok(readFileSync(new URL(`../src/data/${id}`, import.meta.url)).length);
        return id;
      }
      assert.ok(id.startsWith('./')); return load(id.slice(2));
    } });
    cache[name] = exports;
    return exports;
  }
  const { placeProducts } = load('kitchenPlacement');
  const { visibleSlots } = load('kitchenSlots');
  const products = Array.from({ length: 30 }, (_, i) => ({ id: `new_${i}`, name: `Товар ${i}` }));
  const result = placeProducts(products);
  assert.ok(result.placed.length > 0, 'unknown artwork still has a symbolic fallback');
  assert.equal(result.placed.length, visibleSlots().length);
  assert.equal(result.placed.length + result.skipped.length, products.length);
  assert.equal(new Set(result.placed.map((item) => item.slot.id)).size, result.placed.length);
  for (const item of result.placed) {
    assert.equal(item.sprite.size[0], item.slot.rect[2]);
    assert.equal(item.sprite.size[1], item.slot.rect[3]);
  }
  assert.deepEqual(result, placeProducts(products));
  assert.equal(products.length, 30);
});
