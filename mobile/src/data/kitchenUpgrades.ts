/**
 * Косметика кухни: варианты оформления отдельных слоёв.
 *
 * Каждый предмет — это альтернативный спрайт для одного слоя базовой комнаты.
 * Габариты и положение совпадают с базовым слоем, поэтому вариант просто
 * подменяет картинку, ничего не двигая.
 *
 * Открывается по уровню и навсегда: XP остаётся историей достижений, тратить
 * его нельзя. Открытый предмет можно поставить или снять — это выбор
 * оформления, а не расход награды.
 *
 * Порядок лестницы — от мелкого к крупному: сначала то, что стоит на полке,
 * в конце печь. Уровни идут через один, как договорились.
 */
import type { ImageSourcePropType } from 'react-native';
import type { KitchenLayer } from './kitchenLayers';

export interface KitchenUpgrade {
  id: string;
  /** Какой слой базовой комнаты подменяется. */
  layer: KitchenLayer['id'];
  title: string;
  /** Короткое пояснение для карточки в списке. */
  hint: string;
  /** Уровень Домового, на котором предмет открывается. */
  level: number;
  source: ImageSourcePropType;
}

const SAGE = 'sage-tier';

export const KITCHEN_UPGRADES: readonly KitchenUpgrade[] = [
  {
    id: `${SAGE}/shelf-decor`, layer: 'shelf-decor', level: 2,
    title: 'Банка на полке', hint: 'Мелочь, с которой полка выглядит обжитой',
    source: require('../../assets/kitchen/upgrades/sage-tier/shelf-decor.png'),
  },
  {
    id: `${SAGE}/window-decor`, layer: 'window-decor', level: 4,
    title: 'Горшок на окне', hint: 'Зелень на подоконнике',
    source: require('../../assets/kitchen/upgrades/sage-tier/window-decor.png'),
  },
  {
    id: `${SAGE}/textile-decor`, layer: 'textile-decor', level: 6,
    title: 'Полотенце', hint: 'Ткань у столешницы',
    source: require('../../assets/kitchen/upgrades/sage-tier/textile-decor.png'),
  },
  {
    id: `${SAGE}/counter-decor`, layer: 'counter-decor', level: 8,
    title: 'Доска и утварь', hint: 'Рабочая поверхность',
    source: require('../../assets/kitchen/upgrades/sage-tier/counter-decor.png'),
  },
  {
    id: `${SAGE}/shelves`, layer: 'shelves', level: 10,
    title: 'Полки', hint: 'Новое дерево и рейка с крючками',
    source: require('../../assets/kitchen/upgrades/sage-tier/shelves.png'),
  },
  {
    id: `${SAGE}/window`, layer: 'window', level: 12,
    title: 'Окно', hint: 'Рама и подоконник',
    source: require('../../assets/kitchen/upgrades/sage-tier/window.png'),
  },
  {
    id: `${SAGE}/cabinets`, layer: 'cabinets', level: 14,
    title: 'Гарнитур', hint: 'Столешница и шкафы',
    source: require('../../assets/kitchen/upgrades/sage-tier/cabinets.png'),
  },
  {
    id: `${SAGE}/floor`, layer: 'floor', level: 16,
    title: 'Пол', hint: 'Доски другого тона',
    source: require('../../assets/kitchen/upgrades/sage-tier/floor.png'),
  },
  {
    id: `${SAGE}/wall`, layer: 'wall', level: 18,
    title: 'Стены', hint: 'Другая штукатурка',
    source: require('../../assets/kitchen/upgrades/sage-tier/wall.png'),
  },
  {
    id: `${SAGE}/stove`, layer: 'stove', level: 20,
    title: 'Печь', hint: 'Сердце кухни — открывается последней',
    source: require('../../assets/kitchen/upgrades/sage-tier/stove.png'),
  },
] as const;

export function isUnlocked(upgrade: KitchenUpgrade, level: number): boolean {
  return level >= upgrade.level;
}

/** Сколько уровней осталось до ближайшего закрытого предмета. */
export function nextUpgrade(level: number): KitchenUpgrade | null {
  return KITCHEN_UPGRADES.find((upgrade) => !isUnlocked(upgrade, level)) ?? null;
}
