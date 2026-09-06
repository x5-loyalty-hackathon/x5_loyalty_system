import assert from 'node:assert/strict';
import test from 'node:test';
import { DEMO_PROFILES, DEMO_NOW, DEMO_USER_ID, recentReceipt, buildRecommendationRequest } from '../src/fixtures/recommendationRequest.ts';
import { kitchenProducts } from '../src/domain/kitchen.ts';
import { providerHarness } from './helpers/providerHarness.mjs';

const [family, vegetable, soup] = DEMO_PROFILES;
test('demo profiles have separate IDs, past histories and the same reviewed catalog', () => {
  assert.equal(family.userId, DEMO_USER_ID);
  assert.deepEqual(buildRecommendationRequest().current_receipt, recentReceipt);
  const ids = new Set();
  for (const profile of DEMO_PROFILES) {
    assert.equal(ids.has(profile.userId), false); ids.add(profile.userId);
    const request = buildRecommendationRequest(null, 'home', null, profile);
    assert.equal(request.user.user_id, profile.userId);
    assert.deepEqual(request.recipe_catalog, buildRecommendationRequest().recipe_catalog);
    assert.equal(request.purchase_history.length, 4);
    for (const receipt of [...request.purchase_history, request.current_receipt]) {
      assert.equal(ids.has(receipt.receipt_id), false); ids.add(receipt.receipt_id);
      assert.ok(Date.parse(receipt.purchased_at) < Date.parse(DEMO_NOW));
    }
    assert.ok(request.purchase_history.every((r) => Date.parse(r.purchased_at) < Date.parse(request.current_receipt.purchased_at)));
    request.purchase_history[0].items[0].ingredient_ids.push('test-mutation');
    assert.equal(profile.purchaseHistory[0].items[0].ingredient_ids.includes('test-mutation'), false);
  }
});

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const meal = {
  offer_id: 'offered', meal_id: 'demo', title: 'Demo', mode: 'current', default_route: 'cook',
  available_routes: ['cook'], ready_variant: null, cook_variant: {
    recipe_id: 'demo', missing_count: 0, store_selection: null, fulfillment_options: ['next_visit'],
    ingredients: [{ ingredient_id: 'pasta', required: true, source: 'receipt', product_options: [] }],
  },
};
const response = (profile) => ({
  contract_version: '1.3', user_id: profile.userId, recommendations: [meal],
  challenge_selection: { default_mode: 'current', available_modes: ['current'], explicit_choice_required: [] },
});
const baseApi = {
  getHealth: async () => ({ contract_version: '1.3' }),
  getRecommendations: async (mode, anchor, store, profile) => response(profile),
  getRecipeBook: async (userId) => ({ user_id: userId, saved_recipe_ids: [] }),
  saveMealPlan: async (request) => ({ status: 'created', plan: { ...request, status: 'collected' } }),
};

test('profile switch rejects late recipe/book/progress responses, including A → B → A', async () => {
  const oldRecipes = deferred(), oldProgress = deferred();
  let first = true, bookCalls = 0;
  const render = providerHarness({ ...baseApi,
    getRecommendations: async (mode, anchor, store, profile) => {
      if (first) { first = false; return oldRecipes.promise; }
      return response(profile);
    },
    getRecipeBook: async (userId) => ({ user_id: userId, saved_recipe_ids: bookCalls++ ? [] : ['old'] }),
    getProgress: () => oldProgress.promise,
  });
  const recipes = render().loadRecipes();
  const progress = render().loadProgress();
  render().switchProfile(vegetable.id);
  assert.equal(render().progress, null);
  render().switchProfile(family.id);
  await render().loadRecipes();
  oldRecipes.resolve({ ...response(family), recommendations: [] });
  oldProgress.resolve({ user_id: family.userId, avatar_xp: 999 });
  await Promise.all([recipes, progress]);
  assert.equal(render().response.recommendations.length, 1);
  assert.deepEqual(Array.from(render().book), []);
  assert.equal(render().progress, null);
  assert.equal(render().progressStatus, 'idle');
});

for (const action of ['saveToBook', 'savePlan', 'confirmCooking']) {
  test(`profile switch discards late ${action} success and cannot unlock another pending action`, async () => {
    const old = deferred(), current = deferred();
    let hold = false;
    const api = { ...baseApi,
      saveRecipe: () => old.promise,
      saveMealPlan: (request) => hold ? current.promise : baseApi.saveMealPlan(request),
      completeCook: () => old.promise,
    };
    if (action === 'savePlan') api.saveMealPlan = () => hold ? current.promise : old.promise;
    const render = providerHarness(api);
    await render().loadRecipes(); render().selectMeal('demo');
    if (action === 'confirmCooking') { await render().savePlan(); render().startCooking(); }
    const staleHandler = render()[action];
    const pending = staleHandler();
    render().switchProfile(soup.id);
    assert.equal(render().cooking, false);
    assert.equal(render().plan, null);
    assert.equal(render().selectedMeal, null);
    assert.equal(render().editable, true);
    assert.deepEqual(render().kitchenItems, kitchenProducts(soup.currentReceipt.items));
    assert.equal(await staleHandler(), false, 'a handler captured in the previous profile is inert');
    await render().loadRecipes(); render().selectMeal('demo'); hold = true;
    const nextAction = render().savePlan();
    old.resolve({ status: action === 'confirmCooking' ? 'completed' : 'created', saved_recipe_ids: ['old'],
      plan: { user_id: family.userId, status: 'completed' }, progress: { user_id: family.userId, avatar_xp: 20 } });
    assert.equal(await pending, false, 'late success must not navigate to the new profile progress');
    assert.equal(render().busy, true, 'old finally must not unlock new user action');
    assert.equal(render().plan, null); assert.equal(render().progress, null);
    assert.equal(render().notice, null); assert.equal(render().actionError, null);
    current.resolve({ status: 'created', plan: { user_id: soup.userId, status: 'collected', selected_product_ids: [] } });
    assert.equal(await nextAction, true); assert.equal(render().busy, false);
  });
}

test('old action failure does not become the new profile error', async () => {
  const old = deferred();
  const render = providerHarness({ ...baseApi, saveRecipe: () => old.promise });
  await render().loadRecipes(); render().selectMeal('demo');
  const pending = render().saveToBook();
  render().switchProfile(soup.id);
  old.reject(new Error('old connection lost'));
  assert.equal(await pending, false);
  assert.equal(render().actionError, null); assert.equal(render().busy, false);
});
