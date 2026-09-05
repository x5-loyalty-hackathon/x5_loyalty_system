/**
 * Спрайты продуктов для кухни.
 *
 * Источник — дизайн-файл «Продукты для кухни»: спрайты нарисованы попиксельно
 * в палитре сцены и **по размерам конкретных слотов**. Габариты PNG равны
 * размеру слота в клетках, умноженному на 10 (сетка спрайта вдвое плотнее
 * сцены, экспорт ×5). Поэтому спрайт нельзя поставить в слот другого размера:
 * размер — это и есть его место.
 */
import type { ImageSourcePropType } from 'react-native';

export interface ProductSprite {
  id: string;
  /** Человекочитаемое название из дизайн-файла. */
  title: string;
  /** Размер в клетках сцены: должен совпадать со слотом. */
  size: readonly [number, number];
  source: ImageSourcePropType;
}

export const PRODUCT_SPRITES: Record<string, ProductSprite> = {
  'jar-jam': { id: 'jar-jam', title: 'Банка варенья', size: [9, 6], source: require('../../assets/products/jar-jam.png') },
  'tea-tin': { id: 'tea-tin', title: 'Жестянка чая', size: [9, 6], source: require('../../assets/products/tea-tin.png') },
  'honey-jar': { id: 'honey-jar', title: 'Банка мёда', size: [9, 6], source: require('../../assets/products/honey-jar.png') },
  'grain-box': { id: 'grain-box', title: 'Коробка крупы', size: [8, 6], source: require('../../assets/products/grain-box.png') },

  garlic: { id: 'garlic', title: 'Связка чеснока', size: [6, 8], source: require('../../assets/products/garlic.png') },
  herbs: { id: 'herbs', title: 'Пучок зелени', size: [6, 8], source: require('../../assets/products/herbs.png') },
  sausage: { id: 'sausage', title: 'Колбаса', size: [6, 8], source: require('../../assets/products/sausage.png') },

  bread: { id: 'bread', title: 'Хлеб', size: [8, 7], source: require('../../assets/products/bread.png') },
  'milk-bottle': { id: 'milk-bottle', title: 'Бутылка молока', size: [8, 7], source: require('../../assets/products/milk-bottle.png') },
  cheese: { id: 'cheese', title: 'Круг сыра', size: [8, 7], source: require('../../assets/products/cheese.png') },

  'veg-basket': { id: 'veg-basket', title: 'Корзина овощей', size: [10, 10], source: require('../../assets/products/veg-basket.png') },
  'apple-crate': { id: 'apple-crate', title: 'Ящик яблок', size: [12, 10], source: require('../../assets/products/apple-crate.png') },

  'flour-sack': { id: 'flour-sack', title: 'Мешок муки', size: [14, 12], source: require('../../assets/products/flour-sack.png') },
  'potato-crate': { id: 'potato-crate', title: 'Ящик картошки', size: [14, 12], source: require('../../assets/products/potato-crate.png') },
};

/**
 * Каким спрайтом показывать продукт пользователя.
 * Ключ — `ingredient_id` из чеков и рецептов.
 */
export const SPRITE_FOR_INGREDIENT: Record<string, string> = {
  pasta: 'grain-box',
  spaghetti: 'grain-box',
  flour: 'flour-sack',
  grain: 'grain-box',
  tea: 'tea-tin',
  jam: 'jar-jam',
  honey: 'honey-jar',

  garlic: 'garlic',
  basil: 'herbs',
  herbs: 'herbs',
  onion: 'garlic',
  mince: 'sausage',
  meat: 'sausage',
  chicken: 'sausage',
  sausage: 'sausage',

  bread: 'bread',
  milk: 'milk-bottle',
  cheese: 'cheese',
  cottage_cheese: 'cheese',

  tomato: 'veg-basket',
  vegetable: 'veg-basket',
  zucchini: 'veg-basket',
  apple: 'apple-crate',
  fruit: 'apple-crate',
  potato: 'potato-crate',
};

export function spriteForIngredient(ingredientId: string): ProductSprite | null {
  const slug = SPRITE_FOR_INGREDIENT[ingredientId];
  return slug ? PRODUCT_SPRITES[slug] ?? null : null;
}

/**
 * Спрайт под слот заданного размера. Нужен, когда родного места для продукта
 * уже нет: полку лучше занять подходящим по габаритам предметом, чем оставить
 * пустой. Выбор детерминирован — зависит только от `seed`, поэтому картинка
 * не скачет между перерисовками.
 */
export function spriteForSlotSize(width: number, height: number, seed: string): ProductSprite | null {
  const candidates = Object.values(PRODUCT_SPRITES).filter(
    (sprite) => sprite.size[0] === width && sprite.size[1] === height,
  );
  if (candidates.length === 0) return null;
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) % 100000;
  }
  return candidates[hash % candidates.length];
}
