/**
 * Раскладка продуктов пользователя по слотам кухни.
 *
 * Правило задано артом, а не догадками: спрайт нарисован под конкретный размер
 * слота, поэтому продукт встаёт только туда, где габариты совпадают клетка в
 * клетку. Растягивать спрайт нельзя — это пиксель-арт.
 *
 * Раскладка детерминирована: один и тот же список продуктов всегда даёт одну
 * и ту же картинку.
 */
import type { KitchenProduct } from '../domain/kitchen';
import { spriteForIngredient, type ProductSprite } from './productSprites';
import { visibleSlots, type KitchenSlot } from './kitchenSlots';

export interface PlacedProduct {
  product: KitchenProduct;
  sprite: ProductSprite;
  slot: KitchenSlot;
}

export type SkipReason = 'нет спрайта' | 'нет свободного места нужного размера';

export interface SkippedProduct {
  product: KitchenProduct;
  reason: SkipReason;
}

function fits(slot: KitchenSlot, sprite: ProductSprite): boolean {
  const [, , w, h] = slot.rect;
  return w === sprite.size[0] && h === sprite.size[1];
}

/**
 * Раскладывает продукты по свободным слотам.
 * Не поместившиеся возвращаются отдельно с причиной — интерфейс должен
 * показать их списком, а не потерять молча.
 */
export function placeProducts(products: readonly KitchenProduct[]): {
  placed: PlacedProduct[];
  skipped: SkippedProduct[];
} {
  const free = visibleSlots();
  const taken = new Set<string>();
  const placed: PlacedProduct[] = [];
  const skipped: SkippedProduct[] = [];

  for (const product of products) {
    const sprite = spriteForIngredient(product.id);
    if (!sprite) {
      skipped.push({ product, reason: 'нет спрайта' });
      continue;
    }
    const slot = free.find((candidate) => !taken.has(candidate.id) && fits(candidate, sprite));
    if (!slot) {
      skipped.push({ product, reason: 'нет свободного места нужного размера' });
      continue;
    }
    taken.add(slot.id);
    placed.push({ product, sprite, slot });
  }

  return { placed, skipped };
}
