// Out-of-the-box PoC acceptance: no injected host, console commands or flags.
// Requires a disposable running backend and ordinary web demo.
import assert from 'node:assert/strict';

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
  const response = waitPost('/events/receipts');
  await button('К оформлению').click();
  return (await response).json();
};
try {
  await page.goto(process.env.X5_SMOKE_URL || 'http://localhost:8081', { waitUntil: 'networkidle' });
  await text('Рецепты').click();
  await text('Спагетти болоньезе').click();
  await button('Выбрать товары').click();
  await page.getByText('Демо: оформление и покупка моделируются.', { exact: false }).filter({ visible: true }).waitFor();
  assert.equal(posts.filter((p) => p.path.endsWith('/meal-plans')).length, 0);
  await text('Кухня').click();
  await button('Мой план →').click();
  if (process.env.X5_SMOKE_SCREENSHOT) await page.screenshot({ path: `${process.env.X5_SMOKE_SCREENSHOT}.before-checkout.png` });
  const bought = await checkout();
  assert.equal(bought.meal_plan.status, 'collected'); assert.equal(bought.progress.avatar_xp, 0);
  await page.getByText('Демо-покупка подтверждена.', { exact: false }).filter({ visible: true }).waitFor();
  await page.getByText('Куплено — готовка на Кухне', { exact: false }).filter({ visible: true }).waitFor();
  assert.equal(await button('К оформлению').isDisabled(), true);
  assert.equal(posts.filter((p) => p.path.endsWith('/complete-cook')).length, 0);
  console.log('PASS: demo explained before tap; no host setup; cart preserved; real API confirms synthetic purchase');

  await text('Кухня').click(); await button('Готовить →').click();
  const cookedResponse = page.waitForResponse((r) => r.url().endsWith('/complete-cook'));
  await button('Я приготовил').click();
  const cooked = await (await cookedResponse).json();
  assert.equal(cooked.status, 'completed'); assert.equal(cooked.progress.avatar_xp, 20);
  await text('Рецепты').click(); await text('Спагетти болоньезе').click();
  await button('Купить готовое').click();
  const ready = await checkout();
  assert.equal(ready.meal_plan.selected_route, 'ready');
  assert.equal(ready.meal_plan.status, 'completed');
  assert.equal(ready.progress.avatar_xp, 20, 'same purchase day must not award again');
  await page.getByText('Задание выполнено', { exact: false }).filter({ visible: true }).waitFor();
  assert.equal(await button('К оформлению').isDisabled(), true);
  await text('Кухня').click(); await button('Мой прогресс →').click();
  assert.equal(posts.filter((p) => p.path.endsWith('/complete-cook')).length, 1);
  assert.equal(posts.filter((p) => p.path.endsWith('/events/receipts') && p.body.meal_plan_id).length, 2);
  assert.equal(await page.evaluate(() => globalThis.__X5_COMMERCE_HOST__ === undefined), true);
  assert.deepEqual(errors, []);
  if (process.env.X5_SMOKE_SCREENSHOT) await page.screenshot({ path: process.env.X5_SMOKE_SCREENSHOT });
  console.log('PASS: Kitchen cook completion; ready completes on receipt; no additional XP; no JS errors');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(-4000));
  if (process.env.X5_SMOKE_SCREENSHOT) await page.screenshot({ path: process.env.X5_SMOKE_SCREENSHOT });
  throw error;
} finally { await browser.close(); }
