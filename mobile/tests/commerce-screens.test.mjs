// Execute the actual screen components and press handlers, not regex snapshots.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import * as mealFlow from '../src/domain/mealFlow.ts';
import * as copy from '../src/domain/copy.ts';

function screen(name, state) {
  const routes = [];
  const jsx = (type, props) => ({ type, props });
  const modules = {
    'react/jsx-runtime': { jsx, jsxs: jsx },
    react: { useEffect: () => {}, useState: (v) => [v, () => {}], useRef: (v) => ({ current: v }) },
    'react-native': { View: 'View', Text: 'Text', Image: 'Image', ScrollView: 'ScrollView', Pressable: 'Pressable',
      StyleSheet: { create: (s) => s }, useWindowDimensions: () => ({ height: 844 }),
      Animated: { Value: class {}, spring: () => ({ start() {} }) } },
    'expo-router': { useRouter: () => ({ push: (path) => routes.push(path), replace: (path) => routes.push(path) }) },
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '../state/DemoContext': { useDemo: () => state },
    '../domain/mealFlow': mealFlow, '../domain/copy': copy,
    '../theme/tokens': { color: {} }, '../fixtures/recipeDetails': { recipeDetails: {} },
    '../components/FlowControls': { Choice: 'Choice', PrimaryAction: 'PrimaryAction', ActionNotice: 'ActionNotice', flowStyles: {} },
  };
  const exports = {};
  const source = readFileSync(new URL(`../src/app/${name}.tsx`, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  runInNewContext(compiled, { exports, require: (id) => {
    if (id in modules) return modules[id];
    if (id.endsWith('.png')) return id;
    if (id.startsWith('../components/')) {
      const name = id.split('/').at(-1); return { [name]: name };
    }
    assert.fail(`Unexpected screen import ${id}`);
  } });
  const nodes = [];
  function visit(node) {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== 'object') return;
    nodes.push(node); visit(node.props?.children);
  }
  visit(exports.default());
  return { nodes, routes, button: (label) => nodes.find((n) =>
    n.props?.accessibilityLabel === label || n.props?.label === label)?.props };
}
const meal = { title: 'Meal', available_routes: ['cook'], cook_variant: {
  recipe_id: 'recipe', ingredients: [], missing_count: 1, fulfillment_options: ['delivery'],
}, ready_variant: null };
const state = { selectedMeal: meal, route: 'cook', fulfillment: 'delivery', markdown: true,
  choices: {}, basket: { products: [{ sku_id: 'sku' }], total: 30, savings: 0, error: null },
  kitchenItems: [], equipped: {}, editable: true, busy: false, cooking: false, plan: null };

test('actual basket button only hands off checkout, never saves/confirms/cooks/navigates itself', () => {
  let calls = 0;
  const tree = screen('products', { ...state, checkout: () => { calls++; },
    savePlan: () => assert.fail('No save UI'), confirmPurchase: () => assert.fail('No receipt UI'),
    startCooking: () => assert.fail('Cooking belongs to Kitchen') });
  const button = tree.button('К оформлению');
  assert.equal(button.disabled, false); button.onPress();
  assert.equal(calls, 1); assert.deepEqual(tree.routes, []);
});

test('default PoC visibly discloses the simulated purchase before tapping checkout', () => {
  const warning = 'Демо: оформление и покупка моделируются.';
  const copy = (tree) => tree.nodes.filter((node) => node.type === 'Text')
    .map((node) => [node.props.children].flat(Infinity).filter((item) => typeof item === 'string').join('')).join('\n');
  assert.ok(copy(screen('products', { ...state, isDemoCheckout: true })).includes(warning));
  assert.equal(copy(screen('products', { ...state, isDemoCheckout: false })).includes(warning), false);
});

test('actual basket button is disabled for invalid/empty carts and purchased/completed tasks', () => {
  for (const patch of [
    { basket: { ...state.basket, error: 'Unavailable' } },
    { basket: { ...state.basket, products: [] } },
    { plan: { status: 'collected' } }, { plan: { status: 'completed' } }, { busy: true },
  ]) assert.equal(screen('products', { ...state, ...patch }).button('К оформлению').disabled, true);
});

test('Kitchen resumes cooking using existing task action; ready task opens progress, not cooking', () => {
  let starts = 0;
  const cooked = screen('index', { ...state, plan: { selected_route: 'cook', status: 'collected' },
    startCooking: () => { starts++; } });
  cooked.button('Готовить →').onPress();
  assert.equal(starts, 1); assert.deepEqual(cooked.routes, []);
  const ready = screen('index', { ...state, plan: { selected_route: 'ready', status: 'completed' },
    startCooking: () => assert.fail('Ready never cooks') });
  ready.button('Мой прогресс →').onPress();
  assert.deepEqual(ready.routes, ['/profile']);
});

test('Kitchen can reopen unsaved cart or activate home-only cooking without checkout', () => {
  const draft = screen('index', state);
  draft.button('Мой план →').onPress(); assert.deepEqual(draft.routes, ['/products']);
  let activated = 0;
  const home = screen('index', { ...state, basket: { ...state.basket, products: [] },
    savePlanAndCook: () => { activated++; } });
  home.button('Готовить →').onPress(); assert.equal(activated, 1);
});
