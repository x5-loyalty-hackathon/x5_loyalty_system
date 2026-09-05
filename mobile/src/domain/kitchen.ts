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
