import assert from 'node:assert/strict';
import test from 'node:test';
import { acceptMeals, assertVersion, canCompleteCook, createRequestGate, levelShare,
  makeBasket, makeDemoReceipt, makePlan, matchingSteps, purchaseGroups, receiptNotice } from '../src/domain/mealFlow.ts';
import { recipeDetails } from '../src/fixtures/recipeDetails.ts';
import { buildRecommendationRequest } from '../src/fixtures/recommendationRequest.ts';

const product = (sku_id = 'onion', extra = {}) => ({
  sku_id, name: 'Лук, 500 г', category: 'vegetable', store_id: 'store_17',
  distance_km: 0.4, price: 49.9, original_price: 49.9, brand: null,
  source: 'full_price', expires_at: null, fulfillment_options: ['delivery', 'next_visit'], ...extra,
});
const meal = (allHome = false) => ({
  offer_id: 'offered-bolognese',
  meal_id: 'bolognese', title: 'Болоньезе', mode: 'current', model_score: 1,
  default_route: 'cook', available_routes: ['cook'], reason_codes: [], route_reason_codes: [],
  ready_variant: null, warnings: [], safety_status: 'approved',
  cook_variant: {
    recipe_id: 'bolognese', preparation_minutes: 30, missing_count: allHome ? 0 : 1,
    ingredients: [
      { ingredient_id: 'pasta', name: 'Паста', category: 'pantry', required: true, source: 'receipt', product_options: [] },
      { ingredient_id: 'onion', name: 'Лук', category: 'vegetable', required: true,
        source: allHome ? 'home' : 'markdown', product_options: allHome ? [] : [
          product('sale', { price: 29.9, source: 'markdown' }), product(),
        ] },
      { ingredient_id: 'basil', name: 'Базилик', category: 'herbs', required: false, source: 'unavailable', product_options: [] },
    ],
    store_selection: allHome ? null : { selected_store_id: 'store_17' },
    fulfillment_options: ['delivery', 'next_visit'], warnings: [],
  },
});
const response = (recommendations = []) => ({
  contract_version: '1.3', recommendations,
  challenge_selection: { default_mode: recommendations[0]?.mode ?? null,
    available_modes: recommendations.length ? ['current'] : [], explicit_choice_required: [], mode_reason_codes: {} },
});

test('empty response remains empty; server order is preserved without filler', () => {
  assert.deepEqual(acceptMeals(response()).recommendations, []);
  const original = response([meal(), { ...meal(), meal_id: 'other' }]);
  assert.equal(acceptMeals(original), original);
});
test('reject incompatible version, duplicate meals and illegal auto opt-in', () => {
  assert.throws(() => assertVersion({ contract_version: '1.0' }), /API 1.3/);
  assert.throws(() => acceptMeals(response([meal(), meal()])), /повторяющиеся/);
  const invalid = response([meal()]);
  invalid.challenge_selection.explicit_choice_required = ['current'];
  assert.throws(() => acceptMeals(invalid), /основной/);
});
test('reject advertised ready route without a verified ready variant', () => {
  assert.throws(() => acceptMeals(response([{ ...meal(), available_routes: ['cook', 'ready'] }])), /несогласованные/);
  assert.match(makeBasket(meal(), 'ready', 'delivery', false).error, /недоступен/);
});
test('regular pack price by default; markdown is opt-in with rounded savings', () => {
  assert.equal(makeBasket(meal(), 'cook', 'delivery', false).total, 49.9);
  const sale = makeBasket(meal(), 'cook', 'delivery', true);
  assert.equal(sale.total, 29.9); assert.equal(sale.savings, 20);
  assert.deepEqual(sale.products.map((p) => p.sku_id), ['sale']);
});
test('optional unavailable ingredients do not force a purchase', () => {
  const basket = makeBasket(meal(true), 'cook', 'next_visit', false);
  assert.equal(basket.error, null); assert.deepEqual(basket.products, []);
  assert.equal(purchaseGroups(meal(true), 'cook', 'next_visit', false).length, 0);
});
test('stale, unapproved and wrong-store SKU cannot silently replace the selection', () => {
  assert.match(makeBasket(meal(), 'cook', 'delivery', false, { onion: 'sale' }).error, /Нет подходящего/);
  const invalid = meal();
  invalid.cook_variant.ingredients[1].product_options = [product('elsewhere', { store_id: 'store_21' })];
  assert.match(makeBasket(invalid, 'cook', 'delivery', false).error, /Нет подходящего/);
  assert.match(makeBasket(meal(), 'cook', 'delivery', false, { onion: 'invented' }).error, /Нет подходящего/);
});
test('incompatible fulfillment and no regular alternative block plan creation', () => {
  const onlySale = meal();
  onlySale.cook_variant.ingredients[1].product_options = [product('sale', { source: 'markdown' })];
  const invalid = makeBasket(onlySale, 'cook', 'next_visit', false);
  assert.ok(invalid.error);
  assert.throws(() => makePlan(onlySale, 'cook', 'next_visit', invalid, 'u', 'p', 'now'));
  const onlyVisit = meal(); onlyVisit.cook_variant.fulfillment_options = ['next_visit'];
  assert.match(makeBasket(onlyVisit, 'cook', 'delivery', false).error, /способ/);
});
test('ready selects exactly one matching option, not an ingredient basket', () => {
  const ready = { ...meal(), default_route: 'ready', available_routes: ['cook', 'ready'],
    ready_variant: { meal_intent_id: 'bolognese', product_options: [product('prepared')], fulfillment_options: ['delivery'], warnings: [] } };
  const basket = makeBasket(ready, 'ready', 'delivery', false);
  assert.deepEqual(basket.products.map((p) => p.sku_id), ['prepared']);
  const plan = makePlan(ready, 'ready', 'delivery', basket, 'u', 'p', '2026-09-05T12:00:00+03:00');
  assert.equal(plan.selected_recipe_id, null);
  assert.equal(makeDemoReceipt(plan, basket.products, plan.created_at).receipt.items[0].is_prepared_food, true);
});
test('receipt matches selected SKU and price; retry keeps the same ID and body', () => {
  const basket = makeBasket(meal(), 'cook', 'next_visit', true);
  const plan = makePlan(meal(), 'cook', 'next_visit', basket, 'u', 'p', '2026-09-05T12:00:00+03:00');
  const receipt = makeDemoReceipt(plan, basket.products, plan.created_at);
  assert.deepEqual(receipt, makeDemoReceipt(plan, basket.products, plan.created_at));
  assert.equal(receipt.receipt.items[0].sku_id, 'sale');
  assert.equal(receipt.receipt.items[0].unit_price, 29.9);
  assert.equal(receipt.recipe_completed, undefined);
  assert.throws(() => makeDemoReceipt(plan, [product('unrelated')], plan.created_at), /не совпадают/);
  assert.throws(() => makeDemoReceipt(plan, [], plan.created_at), /чек не нужен/);
});
test('cook confirmation requires collected products unless no purchase is needed', () => {
  assert.equal(canCompleteCook(null), false);
  assert.equal(canCompleteCook({ selected_route: 'cook', status: 'saved', selected_product_ids: [] }), true);
  assert.equal(canCompleteCook({ selected_route: 'cook', status: 'saved', selected_product_ids: ['p'] }), false);
  assert.equal(canCompleteCook({ selected_route: 'cook', status: 'collected', selected_product_ids: ['p'] }), true);
  assert.equal(canCompleteCook({ selected_route: 'ready', status: 'collected', selected_product_ids: ['p'] }), false);
});
test('stale network responses lose their right to update state', () => {
  const gate = createRequestGate(); const home = gate.next(); const work = gate.next();
  assert.equal(gate.isCurrent(home), false); assert.equal(gate.isCurrent(work), true);
});
test('anchor switch changes distances and preference, not just a label', () => {
  const home = buildRecommendationRequest(null, 'home');
  const work = buildRecommendationRequest('explore', 'work', 'store_21');
  assert.notEqual(home.inventory_snapshot[0].distance_km, work.inventory_snapshot[0].distance_km);
  assert.deepEqual(work.shopping_context.preferred_store_ids, ['store_21']);
  assert.equal(work.shopping_context.selected_store_id, 'store_21');
  assert.equal(work.requested_mode, 'explore');
  assert.equal(work.current_receipt.purchased_at, '2026-09-04T10:00:00+03:00');
  assert.equal(new Set(work.inventory_snapshot.map((p) => p.sku_id)).size, work.inventory_snapshot.length);
});
test('level progress resets at the level boundary', () => {
  assert.equal(levelShare({ avatar_xp: 50, xp_to_next_level: 50 }), 0);
  assert.equal(levelShare({ avatar_xp: 70, xp_to_next_level: 30 }), 0.4);
});

test('HTTP 200 business rejection/review is not a success; partial collection is explicit', () => {
  assert.throws(() => receiptNotice({ status: 'pending_review' }), /пока не подтверждена/);
  assert.throws(() => receiptNotice({ status: 'rejected' }), /отклонён/);
  assert.throws(() => receiptNotice({ status: 'invented' }), /Неизвестный/);
  assert.match(receiptNotice({ status: 'verified', meal_plan: { status: 'saved' } }), /не собран/);
  assert.match(receiptNotice({ status: 'duplicate' }), /повторных наград нет/);
});

test('demo instructions match the catalog; altered/new recipes have no fabricated steps', () => {
  const request = buildRecommendationRequest();
  for (const recipe of request.recipe_catalog) {
    const selected = { cook_variant: { recipe_id: recipe.recipe_id, ingredients: recipe.ingredients } };
    assert.ok(matchingSteps(selected, recipeDetails).length > 0);
    selected.cook_variant.ingredients = recipe.ingredients.slice(1);
    assert.deepEqual(matchingSteps(selected, recipeDetails), []);
  }
  assert.deepEqual(matchingSteps({ cook_variant: { recipe_id: 'new_ml_recipe', ingredients: [] } }, recipeDetails), []);
});
