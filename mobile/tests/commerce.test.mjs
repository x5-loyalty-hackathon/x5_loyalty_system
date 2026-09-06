import assert from 'node:assert/strict';
import test from 'node:test';
import { providerHarness } from './helpers/providerHarness.mjs';
import { makeDemoReceipt } from '../src/domain/mealFlow.ts';
import { DEMO_NOW, DEMO_PROFILES } from '../src/fixtures/recommendationRequest.ts';

const product = (id, fulfillment = ['delivery'], source = 'full_price') => ({
  sku_id: id, name: id, category: 'vegetable', store_id: 'store_17', price: 30,
  original_price: 50, source, fulfillment_options: fulfillment, distance_km: 0.4,
});
const meal = {
  offer_id: 'offered', meal_id: 'meal', title: 'Meal', mode: 'current', default_route: 'cook',
  available_routes: ['cook', 'ready'],
  cook_variant: { recipe_id: 'meal', missing_count: 1, store_selection: { selected_store_id: 'store_17' },
    fulfillment_options: ['delivery'], ingredients: [
      { ingredient_id: 'onion', name: 'Onion', required: true, source: 'markdown',
        product_options: [product('sale', ['delivery'], 'markdown'), product('full')] },
    ] },
  ready_variant: { fulfillment_options: ['next_visit', 'delivery'],
    product_options: [product('pickup-only', ['next_visit']), product('delivered')] },
};
const progress = { avatar_xp: 0 };
async function setup(host, overrides = {}, offered = meal) {
  const plans = [], receipts = [];
  const render = providerHarness({
    getHealth: async () => ({ contract_version: '1.3' }),
    getRecommendations: async () => ({ contract_version: '1.3', recommendations: [offered, { ...offered, meal_id: 'other' }],
      challenge_selection: { available_modes: ['current'], explicit_choice_required: [] } }),
    getRecipeBook: async () => ({ saved_recipe_ids: [] }),
    saveMealPlan: async (request) => {
      plans.push(request); return { status: 'created', plan: { ...request, status: 'saved' }, progress };
    },
    submitReceipt: async (receipt) => {
      receipts.push(receipt); return { status: 'verified', progress,
        meal_plan: { ...plans.at(-1), status: plans.at(-1).selected_route === 'ready' ? 'completed' : 'collected' } };
    },
    ...overrides,
  }, host);
  await render().loadRecipes(); render().selectMeal('meal');
  return { render, plans, receipts };
}
const deferred = () => {
  let resolve; const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test('ready preview and selection use the same delivery SKU, not first unfiltered option', async () => {
  const { render } = await setup();
  assert.equal(render().readyProduct.sku_id, 'delivered');
  assert.equal(render().takeReadyMeal(), true);
  assert.equal(render().basket.error, null);
  assert.equal(render().basket.products[0].sku_id, 'delivered');
  assert.equal(render().fulfillment, 'delivery');
  await render().savePlan();
  assert.equal(render().takeReadyMeal(), false, 'locked task cannot pretend to change route');
});

test('no delivery SKU means no ready selection or silent switch to pickup', async () => {
  const { render } = await setup(undefined, {}, { ...meal, ready_variant: {
    fulfillment_options: ['next_visit'], product_options: [product('pickup', ['next_visit'])],
  } });
  assert.equal(render().readyProduct, null);
  assert.equal(render().takeReadyMeal(), false);
  render().chooseRoute('ready');
  assert.equal(render().route, 'cook');
  assert.equal(render().fulfillment, 'delivery');
});

test('draft survives browsing and selecting the same meal; a different meal replaces it', async () => {
  const { render, plans } = await setup();
  render().chooseProduct('onion', 'full');
  await render().loadRecipes(); render().selectMeal('meal');
  assert.equal(render().basket.products[0].sku_id, 'full');
  assert.equal(plans.length, 0, 'editing/browsing is not server task activation');
  render().selectMeal('other');
  assert.equal(render().basket.products[0].sku_id, 'sale');
});

test('A → B → A restores delivery/markdown defaults and ignores old ready handler', async () => {
  const { render } = await setup();
  const old = render().takeReadyMeal;
  render().chooseMarkdown(false); render().chooseFulfillment('next_visit');
  render().switchProfile(DEMO_PROFILES[1].id); render().switchProfile(DEMO_PROFILES[0].id);
  assert.equal(old(), false);
  assert.equal(render().markdown, true); assert.equal(render().fulfillment, 'delivery');
  await render().loadRecipes(); render().selectMeal('meal');
  assert.equal(render().basket.products[0].sku_id, 'sale');
});

test('missing commerce host does not activate a plan or fabricate a receipt', async () => {
  const { render, plans, receipts } = await setup();
  assert.equal(await render().checkout(), false);
  assert.match(render().actionError, /автономном демо/);
  assert.equal(plans.length, 0); assert.equal(receipts.length, 0);
  assert.equal(render().editable, true);
});

test('cancelled external checkout preserves editable draft without a purchase or XP', async () => {
  const { render, receipts } = await setup({ openCheckout: async () => ({ status: 'cancelled' }) });
  render().chooseProduct('onion', 'full');
  assert.equal(await render().checkout(), true);
  assert.equal(receipts.length, 0); assert.equal(render().progress.avatar_xp, 0);
  assert.equal(render().plan, null); assert.equal(render().editable, true);
  assert.equal(render().basket.products[0].sku_id, 'full');
  render().chooseProduct('onion', 'sale');
  assert.equal(render().basket.products[0].sku_id, 'sale');
});

for (const route of ['cook', 'ready']) {
  test(`external ${route} receipt updates task once; basket never starts cooking`, async () => {
    let opened = 0;
    const { render, receipts } = await setup({ openCheckout: async ({ plan, products }) => {
      opened++; return { status: 'purchased', receipt: makeDemoReceipt(plan, products, DEMO_NOW) };
    } });
    if (route === 'ready') render().takeReadyMeal();
    assert.equal(await render().checkout(), true, render().actionError);
    assert.equal(render().plan.status, route === 'cook' ? 'collected' : 'completed');
    assert.equal(render().cooking, false); assert.equal(render().canConfirmPurchase, false);
    assert.equal(await render().checkout(), false);
    assert.equal(opened, 1); assert.equal(receipts.length, 1);
    assert.equal(render().startCooking(), route === 'cook');
  });
}

test('lost host response resumes same checkout; lost receipt response never opens checkout again', async () => {
  const opens = [], requests = []; let submissions = 0;
  const { render } = await setup({ openCheckout: async (request) => {
    opens.push(request);
    if (opens.length === 1) throw new Error('lost checkout response');
    return { status: 'purchased', receipt: makeDemoReceipt(request.plan, request.products, DEMO_NOW) };
  } }, { submitReceipt: async (receipt) => {
    requests.push(receipt); submissions++;
    if (submissions === 1) throw new Error('lost receipt response');
    return { status: 'duplicate', progress, meal_plan: { ...opens[0].plan, status: 'collected' } };
  } });
  assert.equal(await render().checkout(), false);
  assert.equal(render().editable, false);
  assert.equal(await render().checkout(), false);
  assert.equal(await render().checkout(), true, render().actionError);
  assert.equal(opens.length, 2); assert.deepEqual(opens[0], opens[1]);
  assert.equal(submissions, 2); assert.deepEqual(requests[0], requests[1]);
});

test('late checkout result after profile A → B → A cannot submit a receipt or change kitchen', async () => {
  const held = deferred(), opened = deferred(); let request;
  const { render, receipts } = await setup({ openCheckout: (value) => {
    request = value; opened.resolve(); return held.promise;
  } });
  const old = render().checkout;
  const pending = old(); await opened.promise;
  assert.equal(await render().checkout(), false, 'overlap suppressed');
  render().switchProfile(DEMO_PROFILES[1].id); render().switchProfile(DEMO_PROFILES[0].id);
  held.resolve({ status: 'purchased', receipt: makeDemoReceipt(request.plan, request.products, DEMO_NOW) });
  assert.equal(await pending, false); assert.equal(await old(), false);
  assert.equal(receipts.length, 0); assert.equal(render().plan, null);
});

test('host cannot attach another user or another task receipt', async () => {
  for (const field of ['user_id', 'meal_plan_id']) {
    const { render, receipts } = await setup({ openCheckout: async ({ plan, products }) => ({
      status: 'purchased', receipt: { ...makeDemoReceipt(plan, products, DEMO_NOW), [field]: 'other' },
    }) });
    assert.equal(await render().checkout(), false);
    assert.equal(receipts.length, 0); assert.match(render().actionError, /другому/);
  }
});

test('definitive plan rejection allows refresh of same recipe offer, preserving cart choice', async () => {
  let attempt = 0, opened = 0;
  const { render } = await setup({ openCheckout: async () => { opened++; return { status: 'cancelled' }; } }, {
    saveMealPlan: async (request) => ++attempt === 1 ? { status: 'rejected', plan: null }
      : { status: 'created', plan: { ...request, status: 'saved' } },
  });
  render().chooseProduct('onion', 'full');
  assert.equal(await render().checkout(), false);
  assert.equal(opened, 0); assert.equal(render().editable, true);
  await render().loadRecipes(); render().selectMeal('meal');
  assert.equal(render().basket.products[0].sku_id, 'full');
  assert.equal(await render().checkout(), true);
  assert.equal(opened, 1);
});

test('partial receipt does not populate the whole cart on Kitchen', async () => {
  const another = product('carrot');
  const twoItems = { ...meal, cook_variant: { ...meal.cook_variant, missing_count: 2,
    ingredients: [...meal.cook_variant.ingredients, {
      ingredient_id: 'carrot', name: 'Carrot', required: true, source: 'full_price', product_options: [another],
    }] } };
  const { render } = await setup({ openCheckout: async ({ plan, products }) => {
    const receipt = makeDemoReceipt(plan, products, DEMO_NOW);
    receipt.receipt.items = receipt.receipt.items.slice(0, 1);
    return { status: 'purchased', receipt };
  } }, {}, twoItems);
  const before = render().kitchenItems.length;
  assert.equal(await render().checkout(), true);
  assert.equal(render().kitchenItems.length, before + 1);
  assert.equal(render().kitchenItems.some((item) => item.name === 'carrot'), false);
});
