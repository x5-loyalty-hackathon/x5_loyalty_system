// Explicit synthetic HOST driver. It does not add checkout UI to the game.
// Requires a disposable running backend and web demo; see docs/commerce-host.md.
import assert from 'node:assert/strict';
import { makeDemoReceipt } from '../src/domain/mealFlow.ts';
import { DEMO_NOW } from '../src/fixtures/recommendationRequest.ts';

const { chromium } = await import(process.env.X5_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const errors = [], posts = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('request', (request) => {
  if (request.method() === 'POST') posts.push({ path: new URL(request.url()).pathname, body: request.postDataJSON() });
});
const text = (value) => page.getByText(value, { exact: true }).filter({ visible: true });
const button = (value) => page.getByRole('button', { name: value, exact: true }).filter({ visible: true });
const waitPost = (suffix) => page.waitForResponse((r) => r.url().endsWith(suffix) && r.request().method() === 'POST');
const checkout = async () => {
  await button('К оформлению').click();
  await page.waitForFunction(() => Boolean(globalThis.__X5_SMOKE_CHECKOUT__));
  return page.evaluate(() => globalThis.__X5_SMOKE_CHECKOUT__.request);
};
const finishCheckout = (result) => page.evaluate((value) => {
  globalThis.__X5_SMOKE_CHECKOUT__.resolve(value);
  globalThis.__X5_SMOKE_CHECKOUT__ = undefined;
}, result);
try {
  await page.goto(process.env.X5_SMOKE_URL || 'http://localhost:8081', { waitUntil: 'networkidle' });
  await text('Рецепты').click();
  await text('Спагетти болоньезе').click();
  await button('Выбрать товары').click();
  await button('К оформлению').click();
  await page.getByText('В автономном демо оно не подключено.', { exact: false }).filter({ visible: true }).waitFor();
  assert.equal(posts.filter((p) => p.path.endsWith('/meal-plans')).length, 0);
  console.log('PASS: no host = no invented order, receipt or task');

  // The external test host resolves cancellation/purchase separately from taps.
  await page.evaluate(() => {
    globalThis.__X5_COMMERCE_HOST__ = { openCheckout: (request) => new Promise((resolve) => {
      globalThis.__X5_SMOKE_CHECKOUT__ = { request, resolve };
    }) };
  });
  const cart = await checkout();
  const receiptCount = posts.filter((p) => p.path.endsWith('/events/receipts')).length;
  await finishCheckout({ status: 'cancelled' });
  await text('Оформление отменено. Выбранные товары остались в корзине.').waitFor();
  assert.equal(posts.filter((p) => p.path.endsWith('/events/receipts')).length, receiptCount);
  await text('Кухня').click();
  await button('Мой план →').click();
  const retry = await checkout();
  assert.deepEqual(retry.products, cart.products);
  const received = waitPost('/events/receipts');
  await finishCheckout({ status: 'purchased', receipt: makeDemoReceipt(retry.plan, retry.products, DEMO_NOW) });
  const bought = await (await received).json();
  assert.equal(bought.meal_plan.status, 'collected'); assert.equal(bought.progress.avatar_xp, 0);
  await text('Куплено — готовка на Кухне').waitFor();
  assert.equal(await button('К оформлению').isDisabled(), true);
  assert.equal(posts.filter((p) => p.path.endsWith('/complete-cook')).length, 0);
  console.log('PASS: cancel preserves cart; purchased cook cart does not cook or replay receipts');

  await text('Кухня').click(); await button('Готовить →').click();
  const cookedResponse = page.waitForResponse((r) => r.url().endsWith('/complete-cook'));
  await button('Я приготовил').click();
  const cooked = await (await cookedResponse).json();
  assert.equal(cooked.status, 'completed'); assert.equal(cooked.progress.avatar_xp, 20);
  await text('Рецепты').click(); await text('Спагетти болоньезе').click();
  await button('Купить готовое').click();
  const readyRequest = await checkout();
  assert.equal(readyRequest.plan.selected_route, 'ready');
  const readyResponse = waitPost('/events/receipts');
  await finishCheckout({ status: 'purchased', receipt: makeDemoReceipt(readyRequest.plan, readyRequest.products, DEMO_NOW) });
  const ready = await (await readyResponse).json();
  assert.equal(ready.meal_plan.status, 'completed');
  assert.equal(ready.progress.avatar_xp, 20, 'same purchase day must not award again');
  await text('Задание выполнено').waitFor();
  assert.equal(await button('К оформлению').isDisabled(), true);
  await text('Кухня').click(); await button('Мой прогресс →').click();
  assert.equal(posts.filter((p) => p.path.endsWith('/complete-cook')).length, 1);
  assert.deepEqual(errors, []);
  if (process.env.X5_SMOKE_SCREENSHOT) await page.screenshot({ path: process.env.X5_SMOKE_SCREENSHOT });
  console.log('PASS: Kitchen cook completion; ready completes on receipt; no additional XP; no JS errors');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(-4000));
  if (process.env.X5_SMOKE_SCREENSHOT) await page.screenshot({ path: process.env.X5_SMOKE_SCREENSHOT });
  throw error;
} finally { await browser.close(); }
