import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import * as mealFlow from '../src/domain/mealFlow.ts';
import * as fixtures from '../src/fixtures/recommendationRequest.ts';
import * as kitchen from '../src/domain/kitchen.ts';

const meal = {
  offer_id: 'offered-home-meal',
  meal_id: 'home_meal', title: 'Блюдо дома', mode: 'current', default_route: 'cook',
  available_routes: ['cook'], ready_variant: null, cook_variant: {
    recipe_id: 'home_meal', missing_count: 0, store_selection: null,
    fulfillment_options: ['next_visit'], ingredients: [
      { ingredient_id: 'pasta', required: true, source: 'receipt', product_options: [] },
    ],
  },
};
const response = {
  contract_version: '1.3', recommendations: [meal],
  challenge_selection: { default_mode: 'current', available_modes: ['current'], explicit_choice_required: [] },
};

// Real provider code with deterministic hook slots and controlled API outcomes.
// Covers state transitions, not React scheduling or rendered phone navigation.
function providerHarness(recommendations = response) {
  const slots = [];
  let cursor = 0;
  let completeResult = async () => { throw new Error('connection lost'); };
  let completionCalls = 0;
  let purchaseResult = async () => { assert.fail('Cooking must not synthesize a purchase'); };
  const receipts = [];
  const react = {
    createContext: () => ({ Provider: 'Provider' }), useContext: () => null,
    useCallback: (fn) => fn,
    useRef: (value) => {
      const index = cursor++;
      return slots[index] ?? (slots[index] = { current: value });
    },
    useState: (initial) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (next) => { slots[index] = typeof next === 'function' ? next(slots[index]) : next; }];
    },
  };
  const jsx = (type, props) => ({ type, props });
  const api = {
    getHealth: async () => ({ contract_version: '1.3' }),
    getRecommendations: async () => recommendations,
    getRecipeBook: async () => ({ saved_recipe_ids: [] }),
    saveMealPlan: async (request) => ({ status: 'created', plan: { ...request,
      status: request.selected_product_ids.length ? 'saved' : 'collected' } }),
    completeCook: async () => { completionCalls++; return completeResult(); },
    submitReceipt: async (receipt) => { receipts.push(receipt); return purchaseResult(receipt); },
  };
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx }, '../api/endpoints': api,
    '../fixtures/recommendationRequest': fixtures, '../domain/mealFlow': mealFlow, '../domain/kitchen': kitchen,
  };
  const source = readFileSync(new URL('../src/state/DemoContext.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: (id) => {
    assert.ok(id in modules, `Unexpected import: ${id}`); return modules[id];
  } });
  return {
    render() { cursor = 0; return exports.DemoProvider({ children: null }).props.value; },
    completion(fn) { completeResult = fn; },
    purchase(fn) { purchaseResult = fn; },
    receipts,
    calls: () => completionCalls,
  };
}

async function begin(harness) {
  assert.equal(harness.render().startCooking(), false);
  await harness.render().loadRecipes();
  harness.render().selectMeal('home_meal');
  assert.equal(await harness.render().savePlan(), true);
  assert.equal(harness.render().startCooking(), true);
  assert.equal(harness.render().cooking, true);
}

test('failed completion stays in cooking; successful retry updates progress without a receipt', async () => {
  const harness = providerHarness();
  await begin(harness);
  assert.equal(await harness.render().confirmCooking(), false);
  assert.equal(harness.render().cooking, true);
  assert.equal(harness.render().actionError, 'connection lost');
  assert.equal(harness.render().progress, null);
  harness.completion(async () => ({ status: 'completed',
    plan: { ...harness.render().plan, status: 'completed', reward: { status: 'no_purchase_evidence', xp: 0 } },
    progress: { avatar_xp: 0 } }));
  assert.equal(await harness.render().confirmCooking(), true);
  assert.equal(harness.render().cooking, false);
  assert.equal(harness.render().progress.avatar_xp, 0);
  assert.equal(harness.render().actionError, null);
  assert.equal(harness.render().busy, false);
});

test('HTTP-success business rejection is not cooking success; overlapping calls are suppressed', async () => {
  const harness = providerHarness();
  await begin(harness);
  let release;
  harness.completion(() => new Promise((resolve) => { release = resolve; }));
  const pending = harness.render().confirmCooking();
  assert.equal(harness.render().busy, true);
  assert.equal(await harness.render().confirmCooking(), false);
  assert.equal(harness.calls(), 1);
  release({ status: 'not_ready', plan: harness.render().plan, progress: { avatar_xp: 0 } });
  assert.equal(await pending, false);
  assert.equal(harness.render().cooking, true);
  assert.ok(harness.render().actionError);
  assert.equal(harness.render().busy, false);
});

test('new recommendation query clears the previous cooking session and plan', async () => {
  const harness = providerHarness();
  await begin(harness);
  await harness.render().loadRecipes({ anchor: 'work' });
  assert.equal(harness.render().cooking, false);
  assert.equal(harness.render().selectedMeal, null);
  assert.equal(harness.render().plan, null);
});

async function purchaseHarness() {
  const product = {
    sku_id: 'onion_sale', name: 'Лук, 500 г', category: 'vegetable',
    store_id: 'store_17', price: 29.9, original_price: 49.9,
    source: 'markdown', fulfillment_options: ['next_visit'], distance_km: 0.4,
  };
  const topup = { ...meal, cook_variant: { ...meal.cook_variant, missing_count: 1,
    store_selection: { selected_store_id: 'store_17' }, ingredients: [
      ...meal.cook_variant.ingredients,
      { ingredient_id: 'onion', required: true, source: 'markdown', product_options: [product] },
    ],
  } };
  const harness = providerHarness({ ...response, recommendations: [topup] });
  await harness.render().loadRecipes();
  harness.render().selectMeal('home_meal');
  harness.render().chooseMarkdown(true);
  assert.equal(await harness.render().savePlan(), true);
  return harness;
}

function purchaseResponse(harness, status = 'verified') {
  return { status, progress: { avatar_xp: 0 },
    meal_plan: { ...harness.render().plan, status: 'collected' } };
}

test('kitchen changes after accepted purchase, not during request; retries and cooking keep items', async () => {
  const harness = await purchaseHarness();
  const initial = harness.render().kitchenItems;
  let release;
  harness.purchase(() => new Promise((resolve) => { release = resolve; }));
  const pending = harness.render().confirmPurchase();
  assert.deepEqual(harness.render().kitchenItems, initial);
  assert.equal(await harness.render().confirmPurchase(), false);
  assert.equal(harness.receipts.length, 1);
  release(purchaseResponse(harness));
  assert.equal(await pending, true);
  assert.deepEqual(harness.render().kitchenItems, [...initial, { id: 'onion', name: 'Лук, 500 г' }]);
  harness.purchase(async () => purchaseResponse(harness, 'duplicate'));
  assert.equal(await harness.render().confirmPurchase(), true);
  assert.deepEqual(harness.receipts[0], harness.receipts[1]);
  assert.equal(harness.render().kitchenItems.length, initial.length + 1);
  assert.equal(harness.render().basket.products.length, 1, 'retry keeps the locked basket');
  assert.equal(harness.render().startCooking(), true);
  harness.completion(async () => ({ status: 'completed',
    plan: { ...harness.render().plan, status: 'completed' }, progress: { avatar_xp: 20 } }));
  await harness.render().confirmCooking();
  assert.equal(harness.render().kitchenItems.length, initial.length + 1, 'no whole-pack deletion');
});

test('rejected/review/unknown receipt outcomes do not populate kitchen or erase basket', async () => {
  const harness = await purchaseHarness();
  const initial = harness.render().kitchenItems;
  for (const status of ['rejected', 'pending_review', 'unknown_status']) {
    harness.purchase(async () => ({ status, progress: { avatar_xp: 0 }, meal_plan: null }));
    assert.equal(await harness.render().confirmPurchase(), false, status);
    assert.deepEqual(harness.render().kitchenItems, initial);
    assert.equal(harness.render().basket.products.length, 1);
    assert.ok(harness.render().actionError);
  }
});

test('lost purchase response leaves kitchen unchanged; server duplicate recovers it once', async () => {
  const harness = await purchaseHarness();
  const initial = harness.render().kitchenItems;
  harness.purchase(async () => { throw new Error('response lost'); });
  assert.equal(await harness.render().confirmPurchase(), false);
  assert.deepEqual(harness.render().kitchenItems, initial);
  harness.purchase(async () => purchaseResponse(harness, 'duplicate'));
  assert.equal(await harness.render().confirmPurchase(), true);
  assert.deepEqual(harness.receipts[0], harness.receipts[1]);
  assert.equal(harness.render().kitchenItems.length, initial.length + 1);
});
