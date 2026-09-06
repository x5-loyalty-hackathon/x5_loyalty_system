import type {
  FulfillmentOption, MealPlan, MealRecommendation, MealResponse, MealRoute,
  PlanRequest, ProductOption, ProgressSnapshot, ReceiptProgressResponse,
  RecommendationMode,
} from '../api/types.ts';

export interface ProductGroup { id: string; name: string; options: ProductOption[] }
export interface Basket { products: ProductOption[]; error: string | null; total: number; savings: number }

export function assertVersion(value: { contract_version: string }): void {
  if (value.contract_version !== '1.3') throw new Error('Нужен backend с контрактом API 1.3.');
}

export function acceptMeals(response: MealResponse): MealResponse {
  assertVersion(response);
  const ids = response.recommendations.map((meal) => meal.meal_id);
  if (new Set(ids).size !== ids.length) throw new Error('Сервер вернул повторяющиеся блюда.');
  const selection = response.challenge_selection;
  if (selection.default_mode && (
    response.recommendations[0]?.mode !== selection.default_mode ||
    selection.explicit_choice_required.includes(selection.default_mode)
  )) throw new Error('Некорректный основной вариант в ответе сервера.');
  for (const meal of response.recommendations) {
    if (!meal.offer_id) throw new Error('Сервер не выдал основание игрового задания. Обновите рекомендации.');
    if (!meal.available_routes.includes(meal.default_route) ||
      (meal.available_routes.includes('cook') !== Boolean(meal.cook_variant)) ||
      (meal.available_routes.includes('ready') !== Boolean(meal.ready_variant))) {
      throw new Error('Сервер вернул несогласованные способы получения блюда.');
    }
  }
  // No filler, client-side sorting or automatic opt-in.
  return response;
}

export function purchaseGroups(
  meal: MealRecommendation, route: MealRoute, fulfillment: FulfillmentOption, markdown: boolean,
): ProductGroup[] {
  if (!meal.available_routes.includes(route)) return [];
  const filter = (options: ProductOption[]) => options.filter((p) =>
    p.fulfillment_options.includes(fulfillment) && (markdown || p.source !== 'markdown'));
  if (route === 'ready') return [{
    id: 'ready', name: 'Готовое блюдо', options: filter(meal.ready_variant?.product_options ?? []),
  }];
  return (meal.cook_variant?.ingredients ?? [])
    .filter((item) => item.required && !['receipt', 'home'].includes(item.source))
    .map((item) => ({
      id: item.ingredient_id, name: item.name,
      options: filter(item.product_options).filter((p) =>
        p.store_id === meal.cook_variant?.store_selection?.selected_store_id),
    }));
}

export function makeBasket(
  meal: MealRecommendation, route: MealRoute, fulfillment: FulfillmentOption,
  markdown: boolean, choices: Record<string, string> = {},
): Basket {
  const failure = (error: string): Basket => ({ products: [], error, total: 0, savings: 0 });
  if (!meal.available_routes.includes(route)) return failure('Этот способ сейчас недоступен.');
  const variant = route === 'cook' ? meal.cook_variant : meal.ready_variant;
  if (!variant?.fulfillment_options.includes(fulfillment)) return failure('Выберите доступный способ получения.');
  const groups = purchaseGroups(meal, route, fulfillment, markdown);
  const products: ProductOption[] = [];
  for (const group of groups) {
    const product = choices[group.id]
      ? group.options.find((p) => p.sku_id === choices[group.id]) : group.options[0];
    if (!product) return failure(`Нет подходящего товара: ${group.name}. Измените выбор или отмените план.`);
    products.push(product);
  }
  if (new Set(products.map((p) => p.store_id)).size > 1) return failure('План должен собираться в одном магазине.');
  // A demo pack cannot silently cover two required ingredients / quantities.
  if (new Set(products.map((p) => p.sku_id)).size !== products.length) {
    return failure('Один товар покрывает несколько ингредиентов: количество требует уточнения.');
  }
  const round = (n: number) => Math.round(n * 100) / 100;
  return {
    products, error: null, total: round(products.reduce((sum, p) => sum + p.price, 0)),
    savings: round(products.reduce((sum, p) => sum + (p.source === 'markdown'
      ? Math.max(0, (p.original_price ?? p.price) - p.price) : 0), 0)),
  };
}

export function makePlan(
  meal: MealRecommendation, route: MealRoute, fulfillment: FulfillmentOption,
  basket: Basket, userId: string, planId: string, now: string,
): PlanRequest {
  if (basket.error) throw new Error(basket.error);
  if (!meal.offer_id) throw new Error('Обновите рекомендации перед выбором задания.');
  if (!meal.available_routes.includes(route) || (route === 'ready' && basket.products.length !== 1)) {
    throw new Error('Нельзя сохранить недоступный способ получения.');
  }
  return {
    offer_id: meal.offer_id,
    plan_id: planId, user_id: userId, meal_id: meal.meal_id,
    selected_route: route, selected_recipe_id: route === 'cook' ? meal.cook_variant!.recipe_id : null,
    selected_product_ids: basket.products.map((p) => p.sku_id), fulfillment, created_at: now,
  };
}

export function makeDemoReceipt(plan: PlanRequest, products: ProductOption[], now: string) {
  if (!products.length) throw new Error('Для блюда без докупок чек не нужен.');
  if (products.length !== plan.selected_product_ids.length ||
    products.some((p) => !plan.selected_product_ids.includes(p.sku_id)) ||
    new Set(products.map((p) => p.store_id)).size !== 1) throw new Error('Товары не совпадают с сохранённым планом.');
  return {
    user_id: plan.user_id, rank_cohort: 'cooking_households' as const,
    meal_plan_id: plan.plan_id, now,
    receipt: {
      // Stable across retries: a timeout must not mint a second receipt.
      receipt_id: `receipt-${plan.plan_id}`, purchased_at: now, store_id: products[0].store_id,
      items: products.map((p) => ({
        sku_id: p.sku_id, name: p.name, category: p.category,
        quantity: 1, unit_price: p.price, is_markdown: p.source === 'markdown',
        original_unit_price: p.original_price, is_prepared_food: plan.selected_route === 'ready',
      })),
    },
  };
}
export type DemoReceiptEvent = ReturnType<typeof makeDemoReceipt>;

export function receiptNotice(result: ReceiptProgressResponse): string {
  if (result.status === 'pending_review') throw new Error('Чек отправлен на проверку. Покупка пока не подтверждена.');
  if (result.status === 'rejected') throw new Error('Чек отклонён. Прогресс за него не начислен.');
  if (result.status === 'duplicate') return 'Этот чек уже учтён; повторных наград нет.';
  if (result.status !== 'verified') throw new Error('Неизвестный результат проверки чека.');
  if (result.meal_plan?.status === 'completed') return 'Покупка готового блюда подтверждена.';
  if (result.meal_plan?.status === 'collected') return 'Продукты из плана куплены. После готовки нажмите «Я приготовил».';
  return 'Чек учтён, но план ещё не собран полностью. Проверьте выбранные товары.';
}

export function canCompleteCook(plan: MealPlan | null): boolean {
  return Boolean(plan && plan.selected_route === 'cook' && (
    plan.status === 'collected' || (plan.status === 'saved' && !plan.selected_product_ids.length)
  ));
}

export function rewardText(plan: MealPlan | null): string {
  if (!plan) return '20 XP за выбранное выполненное задание с подтверждённой покупкой. Не более одного бонуса на покупочный день.';
  switch (plan.reward?.status) {
    case 'awarded': return `За это задание начислено ${plan.reward.xp} XP.`;
    case 'available': return 'Покупка подтверждена. После выполнения задания — 20 XP.';
    case 'purchase_day_reward_used': return 'За этот покупочный день бонус уже получен. Можно готовить дальше без дополнительных XP.';
    case 'no_purchase_evidence': return 'Можно готовить и сохранить результат. Без подходящей подтверждённой покупки XP не начисляются.';
    default: return 'Ожидаем покупку продуктов задания. Бонус — 20 XP, не более одного на покупочный день.';
  }
}

export function taskTitle(mode: RecommendationMode, route: MealRoute): string {
  if (route === 'ready') return 'Ужин без готовки';
  return { current: 'Ужин из моих покупок', repeat: 'Наш любимый ужин', explore: 'Новое для нашей кухни' }[mode];
}

export function levelShare(progress: ProgressSnapshot): number {
  const earned = progress.avatar_xp % 50;
  return earned / Math.max(1, earned + progress.xp_to_next_level);
}

export function matchingSteps(
  meal: MealRecommendation,
  catalog: Record<string, { ingredientIds: string[]; steps: string[] }>,
): string[] {
  const cook = meal.cook_variant;
  if (!cook) return [];
  const detail = catalog[cook.recipe_id];
  if (!detail) return [];
  const actual = cook.ingredients.map((ingredient) => ingredient.ingredient_id).sort();
  const expected = [...detail.ingredientIds].sort();
  // A new ML recipe or changed composition must not inherit unrelated steps.
  return JSON.stringify(actual) === JSON.stringify(expected) ? detail.steps : [];
}

/** Latest-request gate shared by UI and unit tests. */
export function createRequestGate() {
  let revision = 0;
  return { next: () => ++revision, isCurrent: (token: number) => revision === token };
}
