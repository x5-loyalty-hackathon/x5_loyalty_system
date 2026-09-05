import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import { kitchenProducts } from '../src/domain/kitchen.ts';

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
