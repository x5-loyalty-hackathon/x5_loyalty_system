// Audit the exported UI with a real, isolated FastAPI TestClient bridge.
// No live server or payment is used. Set X5_AUDIT_PLAYWRIGHT_MODULE if needed.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { resolve, extname } from 'node:path';

const { chromium } = await import(process.env.X5_AUDIT_PLAYWRIGHT_MODULE ?? 'playwright');
const out = resolve(process.argv[2] ?? 'artifacts/safety-audit-2026-09-07');
const web = resolve(out, 'web');
const source = `
import json, sys
from fastapi.testclient import TestClient
from app.main import app, state_repository
with TestClient(app) as client:
    for line in sys.stdin:
        req = json.loads(line)
        if req['path'] == '__audit_reset__':
            state_repository.reset()
            result = {'status': 200, 'body': {}}
        else:
            r = client.request(req['method'], req['path'], json=req.get('body'))
            result = {'status': r.status_code, 'body': r.json()}
        print(json.dumps(result), flush=True)
`;
const child = spawn(resolve('.venv/bin/python'), ['-u', '-c', source], {
  env: { ...process.env, RECOMMENDATION_ENGINE: 'model' }, stdio: ['pipe', 'pipe', 'inherit'],
});
const lines = createInterface({ input: child.stdout });
const iterator = lines[Symbol.asyncIterator]();
let chain = Promise.resolve();
const api = (method, path, body) => {
  const result = chain.then(async () => {
    child.stdin.write(JSON.stringify({ method, path, body }) + '\n');
    const next = await iterator.next();
    assert.equal(next.done, false, 'isolated API bridge must stay alive');
    return JSON.parse(next.value);
  });
  chain = result.catch(() => {});
  return result;
};
const browser = await chromium.launch();
const checks = [], errors = [], traffic = [];
await mkdir(out, { recursive: true });
try {
  const health = (await api('GET', '/health')).body;
  assert.equal(health.recommendation_engine, 'model'); assert.equal(health.model_fallback, false);
  for (const mode of ['external', 'demo']) {
    await api('POST', '__audit_reset__');
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    // Only the explicitly intercepted audit origin may respond; no real host.
    await context.route('**/*', (route) => route.abort());
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('http://poc-audit.test/**', async (route) => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
        const request = req.postData() ? req.postDataJSON() : undefined;
        const result = await api(req.method(), url.pathname + url.search, request);
        traffic.push({ mode, method: req.method(), path: url.pathname, request, ...result });
        return route.fulfill({ status: result.status, contentType: 'application/json', body: JSON.stringify(result.body) });
      }
      const file = resolve(web, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
      assert.ok(file.startsWith(web + '/'));
      try {
        const body = await readFile(file);
        const types = { '.html': 'text/html', '.js': 'application/javascript', '.png': 'image/png', '.ttf': 'font/ttf', '.ico': 'image/x-icon' };
        return route.fulfill({ contentType: types[extname(file)] ?? 'application/octet-stream', body });
      } catch { return route.fulfill({ status: 404, body: '' }); }
    });
    if (mode === 'external') await page.addInitScript(() => {
      globalThis.auditHostMode = 'cancelled'; globalThis.auditHostCalls = [];
      globalThis.__X5_COMMERCE_HOST__ = { mode: 'external', async openCheckout(request) {
        globalThis.auditHostCalls.push(request);
        if (globalThis.auditHostMode === 'error') throw new Error('Аудит: товар закончился в X5');
        if (globalThis.auditHostMode === 'cancelled') return { status: 'cancelled' };
        const { plan, products } = request;
        return { status: 'purchased', receipt: {
          user_id: plan.user_id, meal_plan_id: plan.plan_id, now: plan.created_at,
          rank_cohort: 'cooking_households', receipt: {
            receipt_id: `audit-host-${plan.plan_id}`, purchased_at: plan.created_at,
            store_id: products[0].store_id, items: products.map(p => ({
              sku_id: p.sku_id, name: p.name, category: p.category, quantity: 1,
              unit_price: p.price + 10, is_markdown: false,
              is_prepared_food: plan.selected_route === 'ready',
            })),
          },
        } };
      } };
    });
    const text = (s) => page.getByText(s, { exact: true }).filter({ visible: true });
    const button = (s) => page.getByRole('button', { name: s, exact: true }).filter({ visible: true });
    const visible = (s) => page.getByText(s, { exact: false }).filter({ visible: true }).first().waitFor();
    const progress = async () => (await api('GET', '/api/v1/progress/user_mobile_12')).body;
    try {
      await page.goto('http://poc-audit.test/');
      await text('Рецепты').click(); await text('Спагетти болоньезе').waitFor();
      await text('Спагетти болоньезе').click();
      await button('Купить готовое').click();
      await button('К оформлению').waitFor();
      assert.equal((await progress()).avatar_xp, 0);
      const before = (await progress()).verified_receipts;
      if (mode === 'external') {
        assert.equal(await page.getByText('Демо: оформление и покупка моделируются.', { exact: false }).count(), 0);
        await button('К оформлению').click(); await visible('Оформление отменено');
        assert.equal((await progress()).verified_receipts, before);
        assert.equal((await progress()).avatar_xp, 0);
        checks.push('external cancellation: no purchase or XP');
        await page.evaluate(() => { globalThis.auditHostMode = 'error'; });
        await button('К оформлению').click(); await visible('Аудит: товар закончился в X5');
        assert.equal((await progress()).verified_receipts, before);
        assert.equal((await progress()).avatar_xp, 0);
        checks.push('external stock/error: no simulated fallback success');
        await page.screenshot({ path: resolve(out, 'browser-host-error.png') });
        await page.evaluate(() => { globalThis.auditHostMode = 'purchased'; });
        await button('К оформлению').click(); await visible('Покупка готового блюда подтверждена');
        const calls = await page.evaluate(() => globalThis.auditHostCalls);
        assert.equal(calls.length, 3);
        assert.deepEqual(calls[1], calls[2], 'error retry uses same checkout and selection');
        const receipt = traffic.filter(t => t.mode === mode && t.path === '/api/v1/events/receipts').at(-1);
        assert.equal(receipt.request.receipt.items[0].unit_price, calls[2].products[0].price + 10);
        checks.push('external purchased callback: stable retry, changed receipt price accepted');
      } else {
        await visible('Демо: оформление и покупка моделируются.');
        await button('К оформлению').click(); await visible('Демо-покупка подтверждена');
        checks.push('standalone simulated checkout explicitly labelled');
      }
      assert.equal((await progress()).verified_receipts, before + 1);
      assert.equal((await progress()).avatar_xp, 20);
      assert.equal(await button('К оформлению').isDisabled(), true);
      await page.screenshot({ path: resolve(out, `browser-${mode}-completed.png`) });
      checks.push(`${mode} ready: exactly one purchase, 20 XP, completed button disabled`);
      await text('Профиль').click(); await visible('20 XP');
      await button('Овощные ужины').click(); await visible('0 XP');
      await text('Рецепты').click(); await text('Паста с томатами').waitFor();
      const offer = traffic.filter(t => t.mode === mode && t.path === '/api/v1/meal-recommendations').at(-1);
      assert.equal(offer.request.user.user_id, 'user_mobile_vegetable');
      assert.ok(offer.body.recommendations.every(m => m.meal_id !== 'spaghetti_bolognese'));
      await text('Профиль').click(); await button('Семья · паста').click(); await visible('20 XP');
      checks.push(`${mode} profile isolation: vegetable excludes meat; family XP restored`);
    } catch (error) {
      await writeFile(resolve(out, 'browser-failure.txt'), await page.locator('body').innerText());
      await page.screenshot({ path: resolve(out, 'browser-failure.png') });
      throw error;
    } finally { await context.close(); }
  }
  assert.deepEqual(errors, []);
  const report = { browser: await browser.version(), transport: 'Chromium exported UI + route interception + isolated FastAPI TestClient; no socket/CORS verification', health, checks, errors, traffic };
  await writeFile(resolve(out, 'browser.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ browser: report.browser, health, checks, errors }, null, 2));
} finally {
  await browser.close(); child.stdin.end(); child.kill(); lines.close();
}
