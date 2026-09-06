// Real TS request/basket/receipt builders against FastAPI TestClient, no socket.
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { buildRecommendationRequest, DEMO_NOW, DEMO_USER_ID } from '../../src/fixtures/recommendationRequest.ts';
import { acceptMeals, makeBasket, makePlan, makeDemoReceipt } from '../../src/domain/mealFlow.ts';
import { reasonText } from '../../src/domain/copy.ts';
import { providerHarness } from '../helpers/providerHarness.mjs';

const root = fileURLToPath(new URL('../../../', import.meta.url));
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
