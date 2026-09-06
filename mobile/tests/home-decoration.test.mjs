import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { providerHarness } from './helpers/providerHarness.mjs';
import { DEMO_PROFILES } from '../src/fixtures/recommendationRequest.ts';
import * as visuals from '../src/domain/homeDecoration.ts';

const [family, vegetable] = DEMO_PROFILES;
const items = [
  { item_id: 'wallpaper_default', title: 'Тёплый дом', description: 'Базовое оформление', unlock_level: 1, required_xp: 0, unlocked: true },
  { item_id: 'wallpaper_mint', title: 'Мятное утро', description: 'Мятные обои', unlock_level: 2, required_xp: 50, unlocked: false },
];
const snapshot = (patch = {}) => ({ user_id: family.userId, avatar_xp: 0, avatar_level: 1,
  applied_item_id: 'wallpaper_default', goal_item_id: null, items, ...patch });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test('decoration default/empty responses stay server owned; late GET cannot undo apply or goal', async () => {
  const old = deferred();
  const render = providerHarness({
    getHomeDecoration: () => old.promise,
    applyHomeDecoration: async () => snapshot({ applied_item_id: 'wallpaper_mint' }),
    setHomeDecorationGoal: async () => snapshot({ applied_item_id: 'wallpaper_mint', goal_item_id: 'wallpaper_mint' }),
  });
  assert.equal(render().decoration, null);
  const get = render().loadHomeDecoration();
  assert.equal(await render().applyDecoration('wallpaper_mint'), true);
  assert.equal(await render().chooseDecorationGoal('wallpaper_mint'), true);
  old.resolve(snapshot()); await get;
  assert.equal(render().decoration.applied_item_id, 'wallpaper_mint');
  assert.equal(render().decoration.goal_item_id, 'wallpaper_mint');
});

test('refresh during mutation is deferred, then reads after commit without suppressing its response', async () => {
  const mutation = deferred(), refresh = deferred();
  let calls = 0;
  const render = providerHarness({ getHomeDecoration: () => { calls++; return refresh.promise; },
    applyHomeDecoration: () => mutation.promise });
  const applying = render().applyDecoration('wallpaper_mint');
  await render().loadHomeDecoration();
  assert.equal(calls, 0);
  assert.equal(await render().chooseDecorationGoal('wallpaper_default'), false, 'mutations are serialized');
  mutation.resolve(snapshot({ applied_item_id: 'wallpaper_mint' }));
  assert.equal(await applying, true);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_mint');
  assert.equal(calls, 1);
  refresh.resolve(snapshot({ applied_item_id: 'wallpaper_mint', avatar_xp: 60 }));
  await new Promise(setImmediate);
  assert.equal(render().decoration.avatar_xp, 60);
});

for (const committed of [false, true]) {
  test(`automatic refresh after failed apply preserves retry unless server confirms commit (${committed})`, async () => {
    const mutation = deferred();
    const render = providerHarness({
      getHomeDecoration: async () => snapshot({ applied_item_id: committed ? 'wallpaper_mint' : 'wallpaper_default' }),
      applyHomeDecoration: () => mutation.promise,
    });
    const applying = render().applyDecoration('wallpaper_mint');
    await render().loadHomeDecoration();
    mutation.reject(new Error('connection lost'));
    assert.equal(await applying, false);
    await new Promise(setImmediate);
    assert.equal(render().decorationStatus, committed ? 'ready' : 'error');
    assert.equal(render().decorationError, committed ? null : 'connection lost');
    assert.equal(render().decorationFailedAction?.itemId ?? null, committed ? null : 'wallpaper_mint');
    assert.equal(render().decoration.applied_item_id, committed ? 'wallpaper_mint' : 'wallpaper_default');
  });
}

for (const operation of ['loadHomeDecoration', 'applyDecoration', 'chooseDecorationGoal']) {
  test(`profile generations reject stale ${operation} after A → B → A`, async () => {
    const old = deferred();
    let first = true;
    const get = async (userId) => {
      if (operation === 'loadHomeDecoration' && first) { first = false; return old.promise; }
      return snapshot({ user_id: userId, goal_item_id: 'wallpaper_default' });
    };
    const render = providerHarness({ getHomeDecoration: get,
      applyHomeDecoration: () => old.promise, setHomeDecorationGoal: () => old.promise });
    const staleHandler = render()[operation];
    const pending = staleHandler('wallpaper_mint');
    render().switchProfile(vegetable.id);
    assert.equal(render().decoration, null);
    assert.equal(render().decorationBusy, false);
    await render().loadHomeDecoration();
    assert.equal(render().decoration.user_id, vegetable.userId);
    render().switchProfile(family.id); await render().loadHomeDecoration();
    old.resolve(snapshot({ applied_item_id: 'wallpaper_mint', goal_item_id: 'wallpaper_mint' }));
    await pending;
    assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
    assert.equal(render().decoration.goal_item_id, 'wallpaper_default');
    assert.equal(render().decorationError, null);
    if (operation !== 'loadHomeDecoration') assert.equal(await staleHandler('wallpaper_mint'), false);
  });
}

test('old mutation failure/finally cannot change or unlock a new profile operation', async () => {
  const old = deferred(), current = deferred();
  let first = true;
  const render = providerHarness({ applyHomeDecoration: () => { if (first) { first = false; return old.promise; } return current.promise; } });
  const previous = render().applyDecoration('wallpaper_mint');
  render().switchProfile(vegetable.id);
  const next = render().applyDecoration('wallpaper_default');
  old.reject(new Error('old failure')); assert.equal(await previous, false);
  assert.equal(render().decorationBusy, true); assert.equal(render().decorationError, null);
  current.resolve(snapshot({ user_id: vegetable.userId }));
  assert.equal(await next, true); assert.equal(render().decorationBusy, false);
});

test('load/apply failures preserve saved wall and goal; retry repeats exact action and no client XP', async () => {
  let failLoad = false, failApply = true;
  const attempts = [];
  const saved = snapshot({ goal_item_id: 'wallpaper_mint' });
  const render = providerHarness({
    getHomeDecoration: async () => { if (failLoad) throw new Error('offline GET'); return saved; },
    applyHomeDecoration: async (...args) => {
      attempts.push(args);
      if (failApply) throw new Error('response lost');
      return snapshot({ goal_item_id: 'wallpaper_mint', applied_item_id: 'wallpaper_mint' });
    },
  });
  await render().loadHomeDecoration(); failLoad = true;
  await render().loadHomeDecoration();
  assert.equal(render().decoration, saved); assert.equal(render().decorationStatus, 'error');
  failLoad = false; await render().retryHomeDecoration();
  assert.equal(render().decorationStatus, 'ready');
  assert.equal(await render().applyDecoration('wallpaper_mint'), false);
  assert.equal(render().decoration, saved);
  failApply = false;
  assert.equal(await render().retryHomeDecoration(), true);
  assert.deepEqual(attempts, [['wallpaper_mint', family.userId], ['wallpaper_mint', family.userId]]);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_mint');
  assert.equal(render().decorationError, null); assert.equal(render().decorationFailedAction, null);
});

test('409 keeps the authoritative wall; wrong-user snapshot is never accepted', async () => {
  const render = providerHarness({
    getHomeDecoration: async () => snapshot(),
    applyHomeDecoration: async () => { throw Object.assign(new Error('409'), { status: 409 }); },
    setHomeDecorationGoal: async () => snapshot({ user_id: vegetable.userId }),
  });
  await render().loadHomeDecoration(); const saved = render().decoration;
  assert.equal(await render().applyDecoration('wallpaper_mint'), false);
  assert.match(render().decorationError, /ещё закрыты/); assert.equal(render().decoration, saved);
  assert.equal(await render().chooseDecorationGoal('wallpaper_mint'), false);
  assert.match(render().decorationError, /другого покупателя/); assert.equal(render().decoration, saved);
});

test('reward completion refreshes decoration from API without synthesizing unlocks', async () => {
  const meal = { offer_id: 'o', meal_id: 'm', default_route: 'cook', available_routes: ['cook'],
    cook_variant: { recipe_id: 'r', fulfillment_options: ['next_visit'], ingredients: [] } };
  let gets = 0;
  const render = providerHarness({
    getHealth: async () => ({ contract_version: '1.3' }), getRecipeBook: async () => ({ saved_recipe_ids: [] }),
    getRecommendations: async () => ({ contract_version: '1.3', recommendations: [meal],
      challenge_selection: { available_modes: ['current'], explicit_choice_required: [] } }),
    saveMealPlan: async (request) => ({ status: 'created', plan: { ...request, status: 'collected' } }),
    completeCook: async () => ({ status: 'completed', plan: { status: 'completed', selected_product_ids: [] }, progress: { avatar_xp: 60 } }),
    getHomeDecoration: async () => { gets++; return snapshot({ avatar_xp: 60, avatar_level: 2,
      items: items.map((item) => ({ ...item, unlocked: true })) }); },
  });
  await render().loadRecipes(); render().selectMeal('m'); await render().savePlan();
  assert.equal(await render().confirmCooking(), true);
  assert.equal(gets, 1);
  assert.equal(render().decoration.items[1].unlocked, true);
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
});

// Render actual sheet handlers with deterministic hooks. Native layout and art
// appearance are checked separately in the browser, not asserted by these hooks.
function sheetHarness(value) {
  const slots = [], cleanups = []; let cursor = 0;
  const react = {
    useEffect: (fn) => { const cleanup = fn(); if (typeof cleanup === 'function') cleanups.push(cleanup); },
    useRef: (value) => { const i = cursor++; return slots[i] ?? (slots[i] = { current: value }); },
    useState: (initial) => { const i = cursor++; if (!(i in slots)) slots[i] = initial;
      return [slots[i], (next) => { slots[i] = next; }]; },
  };
  const jsx = (type, props) => ({ type, props });
  const modules = { react, 'react/jsx-runtime': { jsx, jsxs: jsx },
    'react-native': { ActivityIndicator: 'Spinner', Modal: 'Modal', Pressable: 'Pressable', ScrollView: 'Scroll', Text: 'Text', View: 'View', StyleSheet: { create: (styles) => styles } },
    '../state/DemoContext': { useDemo: () => value }, '../domain/homeDecoration': visuals, '../theme/tokens': { color: {} } };
  const source = readFileSync(new URL('../src/components/HomeDecorationSheet.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: (id) => { assert.ok(id in modules, id); return modules[id]; } });
  const render = (props) => { cursor = 0; return exports.HomeDecorationSheet(props); };
  render.unmount = () => { for (const cleanup of cleanups) cleanup(); };
  return render;
}
function nodes(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(nodes);
  return [node, ...nodes(node.props?.children)];
}
const byId = (tree, id) => nodes(tree).find((node) => node.props?.testID === id);
test('closed wallpaper previews honestly, sets only a goal, and cannot be applied by the UI', async () => {
  const goals = [], applications = [], previews = [];
  // Even a contradictory XP field cannot override server unlocked=false.
  const render = sheetHarness({ decoration: snapshot({ avatar_xp: 60 }), decorationStatus: 'ready',
    decorationBusy: false, chooseDecorationGoal: (id) => goals.push(id), applyDecoration: (id) => applications.push(id) });
  const props = { onClose: () => {}, onPreview: (id) => previews.push(id) };
  byId(render(props), 'decoration-item-wallpaper_mint').props.onPress();
  const preview = render(props);
  assert.equal(previews.at(-1), 'wallpaper_mint');
  assert.equal(byId(preview, 'decoration-apply').props.disabled, true);
  assert.match(JSON.stringify(byId(preview, 'decoration-preview-label')), /ещё не применено/);
  byId(preview, 'decoration-set-goal').props.onPress();
  assert.deepEqual(goals, ['wallpaper_mint']); assert.deepEqual(applications, []);
});
test('sheet is safe with no snapshot or an empty catalog', () => {
  for (const decoration of [null, snapshot({ items: [] })]) {
    const render = sheetHarness({ decoration, decorationStatus: 'ready' });
    const tree = render({ onClose: () => {}, onPreview: () => {} });
    assert.ok(byId(tree, 'home-decoration-sheet'));
    assert.equal(byId(tree, 'decoration-apply'), undefined);
  }
});

test('late apply from a closed sheet cannot close a subsequently reopened sheet', async () => {
  const applying = deferred(); let closeCalls = 0;
  const render = sheetHarness({ decoration: snapshot({ items: items.map((item) => ({ ...item, unlocked: true })) }),
    decorationStatus: 'ready', applyDecoration: () => applying.promise });
  const props = { onClose: () => { closeCalls++; }, onPreview: () => {} };
  byId(render(props), 'decoration-item-wallpaper_mint').props.onPress();
  byId(render(props), 'decoration-apply').props.onPress();
  render.unmount();
  applying.resolve(true); await new Promise(setImmediate);
  assert.equal(closeCalls, 0, 'only the currently mounted sheet may close itself');
});

test('a reward response arriving after failed apply preserves its error and retry during auto refresh', async () => {
  const completion = deferred();
  const meal = { offer_id: 'o', meal_id: 'm', default_route: 'cook', available_routes: ['cook'],
    cook_variant: { recipe_id: 'r', fulfillment_options: ['next_visit'], ingredients: [] } };
  const render = providerHarness({
    getHealth: async () => ({ contract_version: '1.3' }), getRecipeBook: async () => ({ saved_recipe_ids: [] }),
    getRecommendations: async () => ({ contract_version: '1.3', recommendations: [meal],
      challenge_selection: { available_modes: ['current'], explicit_choice_required: [] } }),
    saveMealPlan: async (request) => ({ status: 'created', plan: { ...request, status: 'collected' } }),
    completeCook: () => completion.promise,
    getHomeDecoration: async () => snapshot({ avatar_xp: 60 }),
    applyHomeDecoration: async () => { throw new Error('apply not committed'); },
  });
  await render().loadRecipes(); render().selectMeal('m'); await render().savePlan();
  const cooking = render().confirmCooking();
  assert.equal(await render().applyDecoration('wallpaper_mint'), false);
  completion.resolve({ status: 'completed', plan: { status: 'completed', selected_product_ids: [] }, progress: { avatar_xp: 60 } });
  assert.equal(await cooking, true); await new Promise(setImmediate);
  assert.equal(render().decorationError, 'apply not committed');
  assert.equal(render().decorationFailedAction.itemId, 'wallpaper_mint');
  assert.equal(render().decoration.applied_item_id, 'wallpaper_default');
});

test('wall geometry covers the room wall without any fixed object or furniture pixels', () => {
  assert.deepEqual(visuals.KITCHEN_ART, { left: -39, top: 0, width: 468, height: 624 });
  for (const wall of visuals.WALL_REGIONS) {
    assert.ok(wall.x >= 18 && wall.x + wall.width <= 117 && wall.y >= 0 && wall.y + wall.height <= 62);
    assert.ok(visuals.WALL_OBJECTS.every((object) => !visuals.intersectRect(wall, object)));
  }
  assert.ok(visuals.WALL_REGIONS.reduce((sum, wall) => sum + wall.width * wall.height, 0) > 3500,
    'wallpaper changes a meaningful continuous portion of the room');
  assert.deepEqual(visuals.wallpaperStyle('unknown_future_item'), visuals.wallpaperStyles.wallpaper_default);
});
