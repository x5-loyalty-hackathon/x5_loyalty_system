/**
 * Раскладка продуктов пользователя по слотам кухни.
 *
 * Правило простое и объяснимое: у каждой категории есть предпочтительный вид
 * места — банки и бакалея на полки, зелень на крючки, мелкие овощи на
 * подоконник, крупное на столешницу. Если подходящих мест не осталось,
 * продукт занимает любой свободный видимый слот. Раскладка детерминирована:
 * один и тот же список продуктов всегда даёт одну и ту же картинку.
 */
import type { KitchenProduct } from './demo';
import { visibleSlots, type KitchenSlot, type SlotKind } from './kitchenSlots';

/** Куда по смыслу просится продукт. Первый подходящий вид места выигрывает. */
const PREFERRED: Record<string, SlotKind[]> = {
  pasta: ['shelf'],
  spaghetti: ['shelf'],
  flour: ['shelf'],
  cheese: ['shelf'],
  milk: ['shelf', 'counter'],
  cottage_cheese: ['shelf', 'counter'],
  egg: ['shelf', 'counter'],
  bread: ['counter', 'shelf'],
  mince: ['counter'],
  chicken: ['counter'],
  meat: ['counter'],
  tomato: ['sill', 'counter'],
  zucchini: ['sill', 'counter'],
  vegetable: ['sill', 'counter'],
  basil: ['hook'],
  herbs: ['hook'],
  onion: ['hook', 'sill'],
};

/** Запасной порядок, если у продукта нет своей записи. */
const FALLBACK_ORDER: SlotKind[] = ['shelf', 'counter', 'sill', 'hook', 'floor'];

export interface PlacedProduct {
  product: KitchenProduct;
  slot: KitchenSlot;
}

/**
 * Раскладывает продукты по свободным слотам.
 * Продукты, которым места не хватило, возвращаются отдельно — интерфейс
 * должен показать их списком, а не молча потерять.
 */
export function placeProducts(products: readonly KitchenProduct[]): {
  placed: PlacedProduct[];
  overflow: KitchenProduct[];
} {
  const free = visibleSlots();
  const taken = new Set<string>();
  const placed: PlacedProduct[] = [];
  const overflow: KitchenProduct[] = [];

  const take = (kinds: SlotKind[]): KitchenSlot | null => {
    for (const kind of kinds) {
      const slot = free.find((candidate) => candidate.kind === kind && !taken.has(candidate.id));
      if (slot) {
        taken.add(slot.id);
        return slot;
      }
    }
    return null;
  };

  for (const product of products) {
    const slot =
      take(PREFERRED[product.id] ?? []) ?? take(FALLBACK_ORDER);
    if (slot) placed.push({ product, slot });
    else overflow.push(product);
  }

  return { placed, overflow };
}

/** Сколько продуктов кухня способна показать одновременно. */
export function kitchenCapacity(): number {
  return visibleSlots().length;
}
