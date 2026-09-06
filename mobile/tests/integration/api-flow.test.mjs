// Real TS request/basket/receipt builders against FastAPI TestClient, no socket.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { buildRecommendationRequest, DEMO_NOW, DEMO_USER_ID, DEMO_PROFILES } from '../../src/fixtures/recommendationRequest.ts';
import { acceptMeals, makeBasket, makePlan, makeDemoReceipt } from '../../src/domain/mealFlow.ts';
import { reasonText } from '../../src/domain/copy.ts';
import { providerHarness } from '../helpers/providerHarness.mjs';
import { endpointHarness } from '../helpers/endpointHarness.mjs';
import { kitchenProducts } from '../../src/domain/kitchen.ts';

const root = fileURLToPath(new URL('../../../', import.meta.url));

for (const route of ['cook', 'ready']) {
  test(`default standalone demo → real API: ${route} works without host setup and recovers lost receipt response`, { timeout: 15000 }, async (t) => {
    const call = await api(t);
    const body = async (method, path, payload) => {
      const result = await call(method, path, payload);
      assert.equal(result.status, 200, JSON.stringify(result.body)); return result.body;
    };
    const receipts = []; let loseFirst = true;
    const render = providerHarness({
      getHealth: () => body('GET', '/health'),
      getRecipeBook: (id) => body('GET', `/api/v1/saved-recipes/${id}`),
      getRecommendations: () => body('POST', '/api/v1/meal-recommendations', buildRecommendationRequest()),
      saveMealPlan: (request) => body('POST', '/api/v1/meal-plans', request),
      getHomeDecoration: (id) => body('GET', `/api/v1/home-decoration/${id}`),
      completeCook: (id, userId) => body('POST', `/api/v1/meal-plans/${id}/complete-cook`, { user_id: userId, now: DEMO_NOW }),
      submitReceipt: async (receipt) => {
        receipts.push(receipt);
        const result = await body('POST', '/api/v1/events/receipts', receipt);
        if (loseFirst) { loseFirst = false; throw new Error('response lost after commit'); }
        return result;
      },
    });
    assert.equal(render().isDemoCheckout, true);
    await render().loadRecipes(); render().selectMeal('spaghetti_bolognese');
    if (route === 'ready') assert.equal(render().takeReadyMeal(), true);
    const beforeKitchen = render().kitchenItems.length;
    assert.equal(receipts.length, 0);
    assert.equal(await render().checkout(), false);
    assert.equal(render().kitchenItems.length, beforeKitchen);
    assert.equal(await render().checkout(), true, render().actionError);
    assert.deepEqual(receipts[0], receipts[1]);
    assert.equal(render().progress.verified_receipts, 1);
    assert.ok(render().kitchenItems.length > beforeKitchen);
    assert.match(render().notice, /Демо-покупка подтверждена/);
    assert.equal(render().cooking, false);
    if (route === 'cook') {
      assert.equal(render().progress.avatar_xp, 0);
      assert.equal(render().startCooking(), true);
      assert.equal(await render().confirmCooking(), true, render().actionError);
      assert.equal(await render().confirmCooking(), true);
    } else assert.equal(render().startCooking(), false);
    assert.equal(render().progress.avatar_xp, 20);
    assert.equal(await render().checkout(), false);
    assert.equal(receipts.length, 2);
  });
}

for (const route of ['cook', 'ready']) {
  test(`host checkout → real API: ${route}, cancellation and lost response do not duplicate purchases/XP`, { timeout: 15000 }, async (t) => {
    const call = await api(t);
    const body = async (method, path, payload) => {
      const result = await call(method, path, payload);
      assert.equal(result.status, 200, JSON.stringify(result.body)); return result.body;
    };
    let cancel = true, opened = 0, loseReceipt = true;
    const render = providerHarness({
      getHealth: () => body('GET', '/health'),
      getRecipeBook: (id) => body('GET', `/api/v1/saved-recipes/${id}`),
      getRecommendations: () => body('POST', '/api/v1/meal-recommendations', buildRecommendationRequest()),
      saveMealPlan: (request) => body('POST', '/api/v1/meal-plans', request),
      getHomeDecoration: (id) => body('GET', `/api/v1/home-decoration/${id}`),
      completeCook: (id, userId) => body('POST', `/api/v1/meal-plans/${id}/complete-cook`, { user_id: userId, now: DEMO_NOW }),
      submitReceipt: async (receipt) => {
        const result = await body('POST', '/api/v1/events/receipts', receipt);
        if (loseReceipt) { loseReceipt = false; throw new Error('response lost'); }
        return result;
      },
    }, { openCheckout: async ({ plan, products }) => {
      opened++;
      return cancel ? { status: 'cancelled' } : { status: 'purchased', receipt: makeDemoReceipt(plan, products, DEMO_NOW) };
    } });
    await render().loadRecipes(); render().selectMeal('spaghetti_bolognese');
    if (route === 'ready') assert.equal(render().takeReadyMeal(), true);
    const beforeKitchen = render().kitchenItems.length;
    assert.equal(await render().checkout(), true, render().actionError);
    assert.equal(render().editable, true);
    const before = await body('GET', `/api/v1/progress/${DEMO_USER_ID}`);
    assert.equal(before.verified_receipts, 0); assert.equal(before.avatar_xp, 0);
    cancel = false;
    assert.equal(await render().checkout(), false);
    assert.equal(await render().checkout(), true, render().actionError);
    assert.equal(opened, 2, 'retrying accepted receipt never reopens commerce checkout');
    assert.equal(render().progress.verified_receipts, 1);
    assert.ok(render().kitchenItems.length > beforeKitchen, 'lost response retry restores kitchen too');
    assert.equal(render().cooking, false);
    if (route === 'cook') {
      assert.equal(render().progress.avatar_xp, 0);
      assert.equal(render().startCooking(), true);
      assert.equal(await render().confirmCooking(), true, render().actionError);
      assert.equal(await render().confirmCooking(), true);
    } else assert.equal(render().startCooking(), false);
    assert.equal(render().progress.avatar_xp, 20);
    assert.equal(await render().checkout(), false);
    assert.equal(opened, 2);
  });
}
const python = process.env.X5_TEST_PYTHON ?? (existsSync(`${root}.venv/bin/python`) ? `${root}.venv/bin/python` : 'python3');
const engine = process.env.X5_TEST_ENGINE ?? 'mock';
assert.ok(['mock', 'model'].includes(engine), 'X5_TEST_ENGINE must be mock or model');
const bridgeSource = `
import json, sys
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    print('ready', flush=True)
    for line in sys.stdin:
        req = json.loads(line)
        response = client.request(req['method'], req['path'], json=req.get('body'), headers=req.get('headers'))
        try:
            body = response.json()
        except ValueError:
            body = response.text
        print(json.dumps({'status': response.status_code, 'body': body}), flush=True)
`;
async function api(t) {
  const child = spawn(python, ['-u', '-c', bridgeSource], {
    cwd: root, env: { ...process.env, RECOMMENDATION_ENGINE: engine }, stdio: ['pipe', 'pipe', 'inherit'],
  });
  const lines = createInterface({ input: child.stdout });
  const iterator = lines[Symbol.asyncIterator]();
  t.after(() => { child.stdin.end(); child.kill(); lines.close(); });
  child.on('error', (error) => lines.close());
  assert.equal((await iterator.next()).value, 'ready', 'Python test backend must start');
  const call = async (method, path, body, headers) => {
    child.stdin.write(`${JSON.stringify({ method, path, body, headers })}\n`);
    const line = await iterator.next();
    assert.equal(line.done, false, 'Python backend unexpectedly stopped');
    return JSON.parse(line.value);
  };
  const health = await call('GET', '/health');
  assert.equal(health.status, 200);
  assert.equal(health.body.contract_version, '1.3');
  assert.equal(health.body.recommendation_engine, engine);
  assert.equal(health.body.model_fallback, false, 'model tests must not silently use mock');
  return call;
}
async function recommend(call, mode = null, anchor = 'home', storeId = null) {
  const response = await call('POST', '/api/v1/meal-recommendations', buildRecommendationRequest(mode, anchor, storeId));
  assert.equal(response.status, 200, JSON.stringify(response.body));
  return acceptMeals(response.body);
}

test('TS → API: save book → repeat, no XP for saving', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  assert.deepEqual((await recommend(call, 'repeat')).recommendations, []);
  const meal = (await recommend(call)).recommendations[0];
  const body = { user_id: DEMO_USER_ID, recipe_id: meal.cook_variant.recipe_id };
  assert.equal((await call('POST', '/api/v1/saved-recipes', body)).body.status, 'created');
  assert.equal((await call('POST', '/api/v1/saved-recipes', body)).body.status, 'duplicate');
  const repeated = await recommend(call, 'repeat');
  assert.equal(repeated.recommendations[0].meal_id, meal.meal_id);
  assert.equal((await call('GET', `/api/v1/progress/${DEMO_USER_ID}`)).body.avatar_xp, 0);
});

test('TS → API: selected markdown pack → collected → cooked; retries award once', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const meal = (await recommend(call)).recommendations.find((m) => m.meal_id === 'spaghetti_bolognese');
  const basket = makeBasket(meal, 'cook', 'next_visit', true);
  assert.deepEqual(basket.products.map((p) => p.sku_id), ['onion_sale']);
  const plan = makePlan(meal, 'cook', 'next_visit', basket, DEMO_USER_ID, 'mobile-integration-cook', DEMO_NOW);
  assert.equal((await call('POST', '/api/v1/meal-plans', plan)).body.status, 'created');
  assert.equal((await call('POST', '/api/v1/meal-plans', plan)).body.status, 'duplicate');
  const completePath = `/api/v1/meal-plans/${plan.plan_id}/complete-cook`;
  const confirmation = { user_id: DEMO_USER_ID, now: DEMO_NOW };
  assert.equal((await call('POST', completePath, confirmation)).body.status, 'not_ready');
  const receipt = makeDemoReceipt(plan, basket.products, DEMO_NOW);
  const bought = (await call('POST', '/api/v1/events/receipts', receipt)).body;
  assert.equal(bought.status, 'verified'); assert.equal(bought.meal_plan.status, 'collected');
  assert.equal(bought.progress.recipes_completed, 0); assert.equal(bought.progress.avatar_xp, 0);
  assert.equal(bought.progress.markdown_savings, 20);
  const duplicate = (await call('POST', '/api/v1/events/receipts', receipt)).body;
  assert.equal(duplicate.status, 'duplicate'); assert.deepEqual(duplicate.progress, bought.progress);
  const cooked = (await call('POST', completePath, confirmation)).body;
  assert.equal(cooked.status, 'completed'); assert.equal(cooked.progress.avatar_xp, 20);
  const repeated = (await call('POST', completePath, confirmation)).body;
  assert.equal(repeated.status, 'duplicate'); assert.deepEqual(repeated.progress, cooked.progress);
});

test('TS → API: verified ready meal completes with receipt, never a fixed milk receipt', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const meal = (await recommend(call)).recommendations.find((m) => m.meal_id === 'spaghetti_bolognese');
  const basket = makeBasket(meal, 'ready', 'delivery', false);
  const plan = makePlan(meal, 'ready', 'delivery', basket, DEMO_USER_ID, 'mobile-integration-ready', DEMO_NOW);
  assert.equal((await call('POST', '/api/v1/meal-plans', plan)).status, 200);
  const result = (await call('POST', '/api/v1/events/receipts', makeDemoReceipt(plan, basket.products, DEMO_NOW))).body;
  assert.equal(result.status, 'verified'); assert.equal(result.meal_plan.status, 'completed');
  assert.equal(result.progress.ready_meals_completed, 1); assert.equal(result.progress.recipes_completed, 0);
  assert.equal(result.progress.avatar_xp, 20);
});

test('TS → API: all-home meal completes without a receipt or new purchase day', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const meal = (await recommend(call)).recommendations.find((m) => m.meal_id === 'pasta_tomatoes');
  const basket = makeBasket(meal, 'cook', 'next_visit', false);
  assert.equal(basket.products.length, 0);
  const plan = makePlan(meal, 'cook', 'next_visit', basket, DEMO_USER_ID, 'mobile-integration-home', DEMO_NOW);
  await call('POST', '/api/v1/meal-plans', plan);
  const result = (await call('POST', `/api/v1/meal-plans/${plan.plan_id}/complete-cook`, { user_id: DEMO_USER_ID, now: DEMO_NOW })).body;
  assert.equal(result.status, 'completed'); assert.equal(result.progress.avatar_xp, 0);
  assert.equal(result.progress.purchase_days, 0); assert.equal(result.progress.verified_receipts, 0);
});

test('real provider → API: direct cooking creates a bound plan but no purchase or XP', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const body = async (method, path, payload) => {
    const result = await call(method, path, payload);
    assert.equal(result.status, 200, JSON.stringify(result.body));
    return result.body;
  };
  let saves = 0;
  const render = providerHarness({
    getHealth: () => body('GET', '/health'),
    getRecipeBook: (id) => body('GET', `/api/v1/saved-recipes/${id}`),
    getRecommendations: (mode, anchor, storeId, profile) => body('POST',
      '/api/v1/meal-recommendations', buildRecommendationRequest(mode, anchor, storeId, profile)),
    saveMealPlan: (plan) => { saves++; return body('POST', '/api/v1/meal-plans', plan); },
    completeCook: (id, userId) => body('POST', `/api/v1/meal-plans/${id}/complete-cook`,
      { user_id: userId, now: DEMO_NOW }),
    submitReceipt: () => assert.fail('Direct cooking must never simulate purchase evidence'),
  });
  await render().loadRecipes(); render().selectMeal('pasta_tomatoes');
  assert.equal(render().selectedMeal.cook_variant.missing_count, 0);
  assert.equal(await render().savePlanAndCook(), true, render().actionError);
  assert.equal(saves, 1); assert.equal(render().cooking, true);
  assert.equal(render().plan.status, 'collected');
  assert.equal(render().plan.reward.status, 'no_purchase_evidence');
  assert.equal(await render().confirmCooking(), true, render().actionError);
  assert.equal(render().progress.avatar_xp, 0);
  assert.equal(render().progress.purchase_days, 0);
  assert.equal(render().progress.verified_receipts, 0);
  assert.equal(await render().confirmCooking(), true);
  assert.equal(render().progress.avatar_xp, 0);
});

test('TS → API: work anchor, explicit store and full-basket explore', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const response = await recommend(call, 'explore', 'work', 'store_21');
  const soup = response.recommendations.find((m) => m.meal_id === 'chicken_soup');
  assert.ok(soup, 'explicit explore must expose the new full basket');
  assert.equal(soup.cook_variant.missing_count, 3);
  assert.equal(soup.cook_variant.store_selection.selected_store_id, 'store_21');
  const basket = makeBasket(soup, 'cook', 'next_visit', false);
  assert.equal(basket.products.length, 3);
  assert.ok(basket.products.every((p) => p.store_id === 'store_21' && p.distance_km === 0.25));
  const defaultResponse = await recommend(call);
  assert.ok(defaultResponse.recommendations.every((m) => m.meal_id !== 'chicken_soup'));
});

test('public explanations match the authoritative backend registry', () => {
  const source = execFileSync(python, ['-c',
    'import json; from app.explanations import CHALLENGE_REASON_TEXT, RECIPE_REASON_TEXT, ROUTE_REASON_TEXT, STORE_REASON_TEXT; print(json.dumps(CHALLENGE_REASON_TEXT | RECIPE_REASON_TEXT | ROUTE_REASON_TEXT | STORE_REASON_TEXT))'], { cwd: root, encoding: 'utf8' });
  assert.deepEqual(reasonText, JSON.parse(source));
});

test('real provider → API: lost receipt response recovers plan and cooking on duplicate', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const body = async (method, path, payload) => {
    const response = await call(method, path, payload);
    assert.equal(response.status, 200, JSON.stringify(response.body));
    return response.body;
  };
  let loseFirstResponse = true;
  const render = providerHarness({
    getHealth: () => body('GET', '/health'),
    getRecipeBook: () => body('GET', `/api/v1/saved-recipes/${DEMO_USER_ID}`),
    getRecommendations: (mode, anchor, storeId) => body('POST', '/api/v1/meal-recommendations', buildRecommendationRequest(mode, anchor, storeId)),
    saveMealPlan: (plan) => body('POST', '/api/v1/meal-plans', plan),
    completeCook: (id) => body('POST', `/api/v1/meal-plans/${id}/complete-cook`, { user_id: DEMO_USER_ID, now: DEMO_NOW }),
    submitReceipt: async (receipt) => {
      const result = await body('POST', '/api/v1/events/receipts', receipt);
      if (loseFirstResponse) { loseFirstResponse = false; throw new Error('Response lost after server commit'); }
      assert.equal(result.status, 'duplicate');
      assert.equal(result.meal_plan.status, 'collected');
      return result;
    },
  });
  await render().loadRecipes();
  assert.equal(render().recipesStatus, 'ready', render().recipesError);
  render().selectMeal('spaghetti_bolognese');
  render().chooseRoute('cook');
  render().chooseMarkdown(true);
  assert.equal(await render().savePlan(), true, render().actionError);
  assert.equal(await render().confirmPurchase(), false);
  assert.equal(render().plan.status, 'saved');
  assert.equal(await render().confirmPurchase(), true, render().actionError);
  assert.equal(render().plan.status, 'collected');
  assert.equal(render().progress.avatar_xp, 0);
  assert.equal(render().startCooking(), true);
  assert.equal(await render().confirmCooking(), true, render().actionError);
  assert.equal(render().progress.avatar_xp, 20);
  assert.equal(render().plan.reward.status, 'awarded');
  assert.equal(await render().confirmCooking(), true);
  assert.equal(render().progress.avatar_xp, 20);
});

test('post-checkout: verified current receipt enables one task, never passive XP', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const request = buildRecommendationRequest();
  const proof = await call('POST', '/api/v1/events/receipts', { user_id: DEMO_USER_ID, receipt: request.current_receipt, now: DEMO_NOW });
  assert.equal(proof.body.progress.avatar_xp, 0);
  const meal = (await recommend(call)).recommendations.find((m) => m.meal_id === 'pasta_tomatoes');
  const basket = makeBasket(meal, 'cook', 'next_visit', false);
  for (let index = 0; index < 2; index++) {
    const plan = makePlan(meal, 'cook', 'next_visit', basket, DEMO_USER_ID, `post-checkout-${index}`, DEMO_NOW);
    const saved = (await call('POST', '/api/v1/meal-plans', plan)).body;
    assert.equal(saved.plan.reward.status, index ? 'purchase_day_reward_used' : 'available');
    const result = (await call('POST', `/api/v1/meal-plans/${plan.plan_id}/complete-cook`, { user_id: DEMO_USER_ID, now: DEMO_NOW })).body;
    assert.equal(result.progress.avatar_xp, 20);
    assert.equal(result.progress.purchase_days, 1);
  }
});

test('real provider → API: ready completed on save cannot fabricate a retry purchase', { timeout: 15000 }, async (t) => {
  const call = await api(t);
  const body = async (method, path, payload) => {
    const response = await call(method, path, payload);
    assert.equal(response.status, 200, JSON.stringify(response.body));
    return response.body;
  };
  let receiptCalls = 0;
  const render = providerHarness({
    getHealth: () => body('GET', '/health'),
    getRecipeBook: () => body('GET', `/api/v1/saved-recipes/${DEMO_USER_ID}`),
    getRecommendations: async () => {
      // Complete stock now makes other cook recipes eligible too. Explicit
      // explore exposes all three, so this tests post-checkout ready completion
      // without depending on which full-basket recipe the selector represents.
      const request = buildRecommendationRequest('explore');
      const ready = request.inventory_snapshot.find((p) => p.sku_id === 'ready_bolognese');
      assert.ok(ready);
      request.current_receipt.items = [{
        sku_id: ready.sku_id, name: ready.name, category: ready.category,
        ingredient_ids: [], unit_price: ready.price, is_prepared_food: true,
      }];
      request.current_receipt.store_id = ready.store_id;
      const proof = await body('POST', '/api/v1/events/receipts', {
        user_id: DEMO_USER_ID, receipt: request.current_receipt, now: DEMO_NOW,
      });
      assert.equal(proof.progress.avatar_xp, 0);
      return body('POST', '/api/v1/meal-recommendations', request);
    },
    saveMealPlan: (plan) => body('POST', '/api/v1/meal-plans', plan),
    submitReceipt: async (receipt) => {
      receiptCalls++;
      return body('POST', '/api/v1/events/receipts', receipt);
    },
  });
  await render().loadRecipes();
  assert.equal(render().recipesStatus, 'ready', render().recipesError);
  render().selectMeal('spaghetti_bolognese');
  render().chooseRoute('ready');
  assert.equal(await render().savePlan(), true, render().actionError);
  assert.equal(render().plan.status, 'completed');
  assert.equal(render().plan.completion_evidence, 'verified_receipt:mobile-history-2026-09-04');
  const before = render().progress;
  assert.equal(before.avatar_xp, 20);
  assert.equal(before.purchase_days, 1);
  assert.equal(before.verified_receipts, 1);
  assert.equal(render().canConfirmPurchase, false, 'UI must not offer a fabricated retry');
  assert.equal(await render().confirmPurchase(), false, 'handler also rejects a direct call');
  assert.equal(receiptCalls, 0);
  assert.equal(await render().savePlan(), true, 'save retry must preserve the result');
  assert.deepEqual(await body('GET', `/api/v1/progress/${DEMO_USER_ID}`), before);
});

function realEndpoints(call, afterResponse = async () => {}) {
  return endpointHarness(async (path, options = {}) => {
    const method = options.method ?? 'GET';
    const payload = options.body ? JSON.parse(options.body) : undefined;
    const result = await call(method, path, payload);
    assert.equal(result.status, 200, JSON.stringify(result.body));
    await afterResponse({ method, path, payload, result: result.body });
    return result.body;
  });
}

test('real profiles → API: cooking examples have different recommendations and history reaches the model', { timeout: 20000 }, async (t) => {
  const call = await api(t);
  const endpoints = realEndpoints(call);
  const results = [];
  for (const profile of DEMO_PROFILES) {
    const result = await endpoints.getRecommendations(null, 'home', null, profile);
    assert.equal(result.user_id, profile.userId);
    assert.equal(result.receipt_id, profile.currentReceipt.receipt_id);
    assert.ok(result.recommendations.length > 0);
    const progress = await endpoints.getProgress(profile.userId);
    assert.equal(progress.avatar_xp, 0);
    assert.equal(progress.verified_receipts, 1, 'history is context; only the explicit current event is verified');
    assert.equal(progress.private_rank.cohort, 'cooking_households');
    results.push(result);
    t.diagnostic(`${engine} ${profile.id}: ${JSON.stringify(result.recommendations.map((meal) => ({
      id: meal.meal_id, mode: meal.mode, missing: meal.cook_variant?.missing_count, score: meal.model_score,
    })))}`);
  }
  assert.ok(results[0].recommendations.some((meal) => meal.meal_id === 'spaghetti_bolognese'));
  assert.deepEqual(results[1].recommendations.map((meal) => meal.meal_id), ['pasta_tomatoes']);
  assert.equal(results[2].recommendations[0].meal_id, 'chicken_soup');
  if (engine === 'model') {
    // Controlled sensitivity check: keep the same user/current receipt/catalog
    // and change only purchase_history. Not an expert quality score or uplift.
    const request = buildRecommendationRequest();
    request.purchase_history = buildRecommendationRequest(null, 'home', null, DEMO_PROFILES[2]).purchase_history;
    const swapped = (await call('POST', '/api/v1/meal-recommendations', request)).body;
    const originalScores = new Map(results[0].recommendations.map((meal) => [meal.meal_id, meal.model_score]));
    assert.ok(swapped.recommendations.some((meal) => originalScores.has(meal.meal_id)
      && originalScores.get(meal.meal_id) !== meal.model_score), 'history must affect actual model scores');
    t.diagnostic(`model family with soup history only: ${JSON.stringify(swapped.recommendations.map((meal) => ({
      id: meal.meal_id, score: meal.model_score,
    })))}`);
  }
});

test('real provider + endpoints → API: profiles isolate book, plan, receipts, cooking, kitchen and XP', { timeout: 20000 }, async (t) => {
  const call = await api(t);
  const events = [];
  const render = providerHarness(realEndpoints(call, async (event) => { events.push(event); }));
  const recipes = ['spaghetti_bolognese', 'pasta_tomatoes', 'chicken_soup'];
  const planIds = new Set(), receiptIds = new Set();
  for (const [i, profile] of DEMO_PROFILES.entries()) {
    render().switchProfile(profile.id);
    assert.equal(render().selectedMeal, null); assert.equal(render().plan, null);
    assert.equal(render().cooking, false); assert.equal(render().progress, null);
    assert.equal(render().busy, false); assert.equal(render().editable, true);
    assert.equal(render().canConfirmPurchase, false);
    assert.deepEqual(Array.from(render().book), []);
    assert.deepEqual(render().kitchenItems, kitchenProducts(profile.currentReceipt.items));
    await render().loadRecipes();
    assert.equal(render().recipesStatus, 'ready', render().recipesError);
    assert.equal(render().response.user_id, profile.userId);
    await render().loadProgress();
    assert.equal(render().progress.user_id, profile.userId);
    assert.equal(render().progress.avatar_xp, 0);
    render().selectMeal(recipes[i]);
    assert.ok(render().selectedMeal);
    render().chooseRoute('cook');
    assert.equal(await render().saveToBook(), true, render().actionError);
    assert.equal(await render().savePlan(), true, render().actionError);
    assert.equal(render().plan.user_id, profile.userId);
    assert.equal(planIds.has(render().plan.plan_id), false); planIds.add(render().plan.plan_id);
    if (render().canConfirmPurchase) {
      assert.equal(await render().confirmPurchase(), true, render().actionError);
      assert.ok(render().kitchenItems.some((item) => item.id === 'onion'));
    }
    assert.equal(render().startCooking(), true);
    assert.equal(await render().confirmCooking(), true, render().actionError);
    assert.equal(render().progress.user_id, profile.userId);
    assert.equal(render().progress.avatar_xp, 20);
    assert.equal(render().progress.rewarded_meals, 1);
  }
  for (const event of events.filter((item) => item.path === '/api/v1/events/receipts')) {
    assert.equal(receiptIds.has(event.payload.receipt.receipt_id), false);
    receiptIds.add(event.payload.receipt.receipt_id);
    assert.equal(event.result.progress.user_id, event.payload.user_id);
    if (event.payload.meal_plan_id) assert.ok(planIds.has(event.payload.meal_plan_id));
  }
  // Switching back restores server-owned data, while local cooking/plan/kitchen reset.
  render().switchProfile(DEMO_PROFILES[0].id);
  await render().loadRecipes(); await render().loadProgress();
  assert.deepEqual(Array.from(render().book), [recipes[0]]);
  assert.equal(render().progress.avatar_xp, 20);
  assert.equal(render().plan, null); assert.equal(render().cooking, false);
  assert.deepEqual(render().kitchenItems, kitchenProducts(DEMO_PROFILES[0].currentReceipt.items));
  for (const [i, profile] of DEMO_PROFILES.entries()) {
    const book = (await call('GET', `/api/v1/saved-recipes/${profile.userId}`)).body;
    assert.deepEqual(book.saved_recipe_ids, [recipes[i]]);
    const progress = (await call('GET', `/api/v1/progress/${profile.userId}`)).body;
    assert.equal(progress.avatar_xp, 20);
    assert.equal(progress.recipes_completed, 1);
  }
});

test('real provider + endpoints → API: late receipt response cannot enter a new profile or survive switching back', { timeout: 20000 }, async (t) => {
  const call = await api(t);
  let release, committed;
  const held = new Promise((resolve) => { release = resolve; });
  const hasCommitted = new Promise((resolve) => { committed = resolve; });
  const render = providerHarness(realEndpoints(call, async ({ path, payload }) => {
    if (path === '/api/v1/events/receipts' && payload.meal_plan_id) { committed(); await held; }
  }));
  await render().loadRecipes(); render().selectMeal('spaghetti_bolognese');
  assert.equal(await render().savePlan(), true, render().actionError);
  const oldPlan = render().plan;
  const oldReceipt = render().confirmPurchase(); await hasCommitted;
  assert.equal(render().busy, true);
  render().switchProfile(DEMO_PROFILES[2].id);
  await render().loadRecipes(); await render().loadProgress();
  const snapshot = { response: render().response, kitchen: render().kitchenItems, progress: render().progress };
  release();
  assert.equal(await oldReceipt, false);
  assert.equal(render().plan, null); assert.equal(render().canConfirmPurchase, false);
  assert.equal(render().notice, null); assert.equal(render().actionError, null);
  assert.equal(render().response, snapshot.response);
  assert.equal(render().kitchenItems, snapshot.kitchen);
  assert.equal(render().progress, snapshot.progress);
  // B needs its own purchase too: a retained pendingReceipt from A must never
  // be reused when B saves a different basket.
  render().selectMeal('pasta_tomatoes');
  assert.equal(await render().savePlan(), true, render().actionError);
  assert.notEqual(render().plan.plan_id, oldPlan.plan_id);
  assert.equal(render().plan.user_id, DEMO_PROFILES[2].userId);
  assert.equal(render().canConfirmPurchase, true);
  assert.equal(await render().confirmPurchase(), true, render().actionError);
  assert.equal(render().plan.user_id, DEMO_PROFILES[2].userId);
  assert.equal(render().progress.user_id, DEMO_PROFILES[2].userId);
  assert.equal(render().startCooking(), true);
  assert.equal(await render().confirmCooking(), true, render().actionError);
  render().switchProfile(DEMO_PROFILES[0].id);
  assert.equal(render().plan, null); assert.equal(render().canConfirmPurchase, false);
  await render().loadRecipes(); await render().loadProgress();
  assert.equal(render().progress.avatar_xp, 0, 'old receipt was accepted for A but did not confirm cooking');
  assert.equal(render().progress.verified_receipts, 2);
  assert.deepEqual(render().kitchenItems, kitchenProducts(DEMO_PROFILES[0].currentReceipt.items));
});

test('real decoration endpoints + provider: purchase-backed unlock, free apply, lost response retry and profile restore', { timeout: 25000 }, async (t) => {
  const call = await api(t);
  let loseApply = false;
  const endpoints = endpointHarness(async (path, options = {}) => {
    const result = await call(options.method ?? 'GET', path, options.body ? JSON.parse(options.body) : undefined);
    if (result.status !== 200) throw Object.assign(new Error(`HTTP ${result.status}`), { status: result.status });
    if (loseApply && path.endsWith('/apply')) { loseApply = false; throw new Error('Response lost after decoration commit'); }
    return result.body;
  });
  const render = providerHarness(endpoints);
  await render().loadHomeDecoration();
  assert.equal(render().decoration.avatar_xp, 0);
  assert.equal(render().decoration.items.length, 6);
  assert.equal(await render().chooseDecorationGoal('wallpaper_mint'), true);
  assert.equal(await render().applyDecoration('wallpaper_mint'), false);
  assert.match(render().decorationError, /ещё закрыты/);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
  const family = DEMO_PROFILES[0];
  // Two different verified purchase days, using actual endpoint adapters and TS
  // meal/plan builders. Neither history nor direct XP seeding opens the paper.
  for (const [index, profile] of [
    { ...family, currentReceipt: { ...family.currentReceipt, receipt_id: 'decor-earlier-current', purchased_at: '2026-09-03T10:00:00+03:00' } },
    family,
  ].entries()) {
    const response = await endpoints.getRecommendations(null, 'home', null, profile);
    const meal = response.recommendations.find((item) => item.meal_id === 'pasta_tomatoes');
    const basket = makeBasket(meal, 'cook', 'next_visit', false);
    assert.equal(basket.products.length, 0);
    const plan = makePlan(meal, 'cook', 'next_visit', basket, family.userId, `decor-verified-day-${index}`, DEMO_NOW);
    await endpoints.saveMealPlan(plan);
    const result = await endpoints.completeCook(plan.plan_id, family.userId);
    assert.equal(result.progress.avatar_xp, (index + 1) * 20);
  }
  await render().loadRecipes(); render().selectMeal('spaghetti_bolognese');
  assert.equal(await render().savePlan(), true, render().actionError);
  assert.equal(await render().confirmPurchase(), true, render().actionError);
  assert.equal(await render().confirmCooking(), true, render().actionError);
  // The reward triggers a GET in the provider; settle its real transport.
  for (let attempt = 0; attempt < 100 && render().decorationStatus === 'loading'; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.equal(render().decoration.avatar_xp, 60, render().decorationError);
  assert.deepEqual(render().decoration.items.filter((item) => item.unlocked).map((item) => item.item_id),
    ['wallpaper_default', 'wallpaper_mint', 'wallpaper_sunset', 'wallpaper_sky']);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
  const progressBefore = await endpoints.getProgress(family.userId);
  loseApply = true;
  assert.equal(await render().applyDecoration('wallpaper_mint'), false);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default', 'lost response is not optimistic apply');
  assert.equal(await render().retryHomeDecoration(), true);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_mint');
  assert.equal(render().decoration.goal_item_id, 'wallpaper_mint');
  assert.equal(await render().applyDecoration('wallpaper_sunset'), true);
  assert.equal(await render().applyDecoration('wallpaper_mint'), true);
  assert.deepEqual(await endpoints.getProgress(family.userId), progressBefore, 'free changes never spend or award XP');
  render().switchProfile(DEMO_PROFILES[1].id);
  assert.equal(render().decoration, null); await render().loadHomeDecoration();
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
  assert.equal(render().decoration.goal_item_id, null); assert.equal(render().decoration.avatar_xp, 0);
  render().switchProfile(family.id); await render().loadHomeDecoration();
  assert.equal(render().decoration.applied_item_id, 'wallpaper_mint');
  assert.equal(render().decoration.goal_item_id, 'wallpaper_mint');
  const restarted = providerHarness(endpoints); await restarted().loadHomeDecoration();
  assert.equal(restarted().decoration.applied_item_id, 'wallpaper_mint', 'new client restores server selection');
  assert.equal(await restarted().chooseDecorationGoal(null), true);
  assert.equal(restarted().decoration.goal_item_id, null);
});
