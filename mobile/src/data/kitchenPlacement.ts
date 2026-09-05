/**
 * Раскладка продуктов пользователя по слотам кухни.
 *
 * Спрайт нарисован под конкретный размер слота, растягивать пиксель-арт нельзя.
 * Поэтому сначала пробуем родной спрайт продукта, а если места его размера уже
 * нет — занимаем любое свободное и берём спрайт под него. Кухня должна
 * наполняться по мере роста запасов; точное соответствие категории вторично.
 *
 * Раскладка детерминирована: один и тот же список продуктов всегда даёт одну
 * и ту же картинку.
 */
import type { KitchenProduct } from '../domain/kitchen';
import { spriteForIngredient, spriteForSlotSize, type ProductSprite } from './productSprites';
import { visibleSlots, type KitchenSlot } from './kitchenSlots';

export interface PlacedProduct {
  product: KitchenProduct;
  sprite: ProductSprite;
  slot: KitchenSlot;
}

export type SkipReason = 'нет свободного места';

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
    const own = spriteForIngredient(product.id);
    let slot = own
      ? free.find((candidate) => !taken.has(candidate.id) && fits(candidate, own))
      : undefined;
    let sprite = own && slot ? own : null;

    if (!sprite) {
      // Родного места нет — занимаем любое свободное подходящим по размеру
      // спрайтом, чтобы полки заполнялись, а не пустовали.
      slot = free.find((candidate) => !taken.has(candidate.id));
      sprite = slot ? spriteForSlotSize(slot.rect[2], slot.rect[3], product.id) : null;
    }

    if (!slot || !sprite) {
      skipped.push({ product, reason: 'нет свободного места' });
      continue;
    }
    taken.add(slot.id);
    placed.push({ product, sprite, slot });
  }

  return { placed, skipped };
}
