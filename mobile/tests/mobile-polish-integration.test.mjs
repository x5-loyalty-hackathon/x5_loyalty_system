import assert from 'node:assert/strict';
import test from 'node:test';
import { providerHarness } from './helpers/providerHarness.mjs';
import { DEMO_PROFILES } from '../src/fixtures/recommendationRequest.ts';

const meal = {
  offer_id: 'server-offer', meal_id: 'home_meal', title: 'Блюдо дома', mode: 'current',
  default_route: 'cook', available_routes: ['cook'], ready_variant: null,
  cook_variant: { recipe_id: 'home_meal', missing_count: 0, store_selection: null,
    fulfillment_options: ['next_visit'], ingredients: [
      { ingredient_id: 'pasta', required: true, source: 'home', product_options: [] },
    ] },
};
const base = {
  getHealth: async () => ({ contract_version: '1.3' }),
  getRecommendations: async () => ({ contract_version: '1.3', recommendations: [meal],
    challenge_selection: { available_modes: ['current'], explicit_choice_required: [] } }),
  getRecipeBook: async () => ({ saved_recipe_ids: [] }),
  submitReceipt: () => assert.fail('The shortcut must not fabricate a purchase'),
  completeCook: () => assert.fail('Opening cooking must not confirm completion'),
};
async function selected(overrides) {
  const render = providerHarness({ ...base, ...overrides });
  await render().loadRecipes(); render().selectMeal(meal.meal_id);
  return render;
}
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test('cook shortcut opens from fresh server plan, preserves offer, never creates a receipt or XP', async () => {
  const requests = [];
  const render = await selected({ saveMealPlan: async (request) => {
    requests.push(request);
    return { status: 'created', plan: { ...request, status: 'collected' } };
  } });
  assert.equal(render().plan, null);
  assert.equal(await render().savePlanAndCook(), true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].offer_id, 'server-offer');
  assert.equal(requests[0].user_id, DEMO_PROFILES[0].userId);
  assert.equal(requests[0].selected_product_ids.length, 0);
  assert.equal(render().plan.status, 'collected');
  assert.equal(render().cooking, true);
  assert.equal(render().progress, null);
});

for (const status of ['saved', 'cancelled', 'completed']) {
  test(`cook shortcut respects non-cookable server status: ${status}`, async () => {
    const render = await selected({ saveMealPlan: async (request) => ({ status: 'created',
      plan: { ...request, status, selected_product_ids: ['still-needs-proof'] } }) });
    assert.equal(await render().savePlanAndCook(), false);
    assert.equal(render().cooking, false);
    assert.match(render().actionError, /Сначала соберите/);
  });
}

test('cook shortcut retries exact plan after lost response and ignores business rejection', async () => {
  const requests = [];
  const render = await selected({ saveMealPlan: async (request) => {
    requests.push(request);
    if (requests.length === 1) throw new Error('response lost');
    return { status: 'duplicate', plan: { ...request, status: 'collected' } };
  } });
  assert.equal(await render().savePlanAndCook(), false);
  assert.equal(render().cooking, false);
  assert.equal(await render().savePlanAndCook(), true);
  assert.deepEqual(requests[0], requests[1]);
  const rejected = await selected({ saveMealPlan: async () => ({ status: 'rejected', plan: null }) });
  assert.equal(await rejected().savePlanAndCook(), false);
  assert.equal(rejected().cooking, false);
});

test('cook shortcut is serialized and a late response cannot open another profile kitchen', async () => {
  const held = deferred(); let calls = 0, request;
  const render = await selected({ saveMealPlan: (value) => { calls++; request = value; return held.promise; } });
  const staleHandler = render().savePlanAndCook;
  const pending = staleHandler();
  assert.equal(await render().savePlanAndCook(), false);
  assert.equal(calls, 1);
  render().switchProfile(DEMO_PROFILES[1].id);
  render().switchProfile(DEMO_PROFILES[0].id);
  held.resolve({ status: 'created', plan: { ...request, status: 'collected' } });
  assert.equal(await pending, false);
  assert.equal(await staleHandler(), false);
  assert.equal(render().cooking, false);
  assert.equal(render().plan, null);
  assert.equal(render().notice, null);
});

test('local cosmetic selection never migrates to a different demo profile', async () => {
  const render = providerHarness(base);
  render().toggleUpgrade('sage-tier/shelf-decor');
  assert.equal(render().equipped['sage-tier/shelf-decor'], true);
  render().switchProfile(DEMO_PROFILES[1].id);
  assert.equal(Object.keys(render().equipped).length, 0);
});
