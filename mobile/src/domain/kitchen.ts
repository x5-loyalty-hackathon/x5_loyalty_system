import type { MealRecommendation, MealRoute, ProductOption } from '../api/types.ts';

/** Display evidence only, never an inferred pantry or receipt ingestion API. */
export interface KitchenProduct { id: string; name: string }

export function kitchenProducts(items: Array<{ name: string; ingredient_ids: string[] }>): KitchenProduct[] {
  const byIngredient = new Map<string, KitchenProduct>();
  for (const item of items) {
    for (const id of item.ingredient_ids) {
      if (!byIngredient.has(id)) byIngredient.set(id, { id, name: item.name });
    }
  }
  return [...byIngredient.values()];
}

/** Map selected, server-approved SKU to display items, not to inferred stock.
 * Ready food remains one purchased dish; its composition is never raw pantry.
 */
export function purchasedKitchenProducts(
  meal: MealRecommendation, route: MealRoute, products: ProductOption[],
): KitchenProduct[] {
  return products.map((product) => {
    const ingredient = route === 'cook' ? meal.cook_variant?.ingredients.find((item) =>
      item.product_options.some((option) => option.sku_id === product.sku_id)) : null;
    return {
      id: route === 'ready' ? `ready:${product.sku_id}` : ingredient?.ingredient_id ?? `sku:${product.sku_id}`,
      name: product.name,
    };
  });
}

export function mergeKitchenProducts(
  current: readonly KitchenProduct[], purchased: readonly KitchenProduct[],
): KitchenProduct[] {
  const items = new Map(current.map((item) => [item.id, item]));
  for (const item of purchased) items.set(item.id, item);
  return [...items.values()];
}
