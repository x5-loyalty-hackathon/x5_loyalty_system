/**
 * Слоты кухни — места, куда встают продукты пользователя.
 *
 * Координаты взяты из дизайн-бандла (`Kitchen Scene.dc.html`, массив `SLOTS`)
 * и заданы в клетках пиксель-арта на сетке 117×156. Менять их следует вместе
 * с артом: слот привязан к нарисованной полке, крючку или столешнице.
 *
 * В приложении показан только верхний срез сетки (62 строки из 156), поэтому
 * часть слотов в кадр не попадает — см. `visibleSlots()`.
 */

/** Ширина сетки пиксель-арта. */
export const GRID_W = 117;
/** Полная высота комнаты. */
export const GRID_H = 156;
/**
 * До какой строки сетки слот остаётся на виду. Ниже начинается свёрнутая
 * шторка со списком продуктов, и предмет за ней уже не разглядеть.
 */
export const VISIBLE_ROWS = 116;

/** Масштаб: сколько точек экрана приходится на одну клетку сетки. */
export const CELL = 4;
/** Сдвиг арта влево, как в макете (`left: -39`). */
export const BAND_OFFSET_X = -39;
/** Ширина экрана, под которую свёрстан макет. */
export const SCREEN_W = 390;

export type SlotKind = 'shelf' | 'hook' | 'sill' | 'counter' | 'floor';

export interface KitchenSlot {
  id: string;
  kind: SlotKind;
  /** Прямоугольник в клетках сетки: x, y, ширина, высота. */
  rect: readonly [number, number, number, number];
}

export const KITCHEN_SLOTS: readonly KitchenSlot[] = [
  { id: 'shelf-top-1', kind: 'shelf', rect: [48, 12, 9, 6] },
  { id: 'shelf-top-2', kind: 'shelf', rect: [60, 12, 8, 6] },
  { id: 'shelf-low-1', kind: 'shelf', rect: [36, 32, 9, 6] },
  { id: 'shelf-low-2', kind: 'shelf', rect: [48, 32, 9, 6] },
  { id: 'shelf-low-3', kind: 'shelf', rect: [60, 32, 8, 6] },
  { id: 'hook-1', kind: 'hook', rect: [40, 29, 6, 8] },
  { id: 'hook-2', kind: 'hook', rect: [47, 29, 6, 8] },
  { id: 'sill-1', kind: 'sill', rect: [76, 36, 8, 7] },
  { id: 'sill-2', kind: 'sill', rect: [88, 36, 8, 7] },
  { id: 'counter-1', kind: 'counter', rect: [88, 52, 10, 10] },
  { id: 'counter-2', kind: 'counter', rect: [102, 52, 12, 10] },
  { id: 'floor-1', kind: 'floor', rect: [4, 118, 14, 12] },
] as const;

export interface SlotRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Переводит слот в координаты внутри полосы кухни. */
export function slotRect(slot: KitchenSlot): SlotRect {
  const [x, y, w, h] = slot.rect;
  return { left: x * CELL + BAND_OFFSET_X, top: y * CELL, width: w * CELL, height: h * CELL };
}

/** Слот целиком попадает в показанную полосу и не выходит за края экрана. */
export function isSlotVisible(slot: KitchenSlot): boolean {
  const [x, y, w, h] = slot.rect;
  if (y + h > VISIBLE_ROWS) return false;
  const { left, width } = slotRect(slot);
  return left >= 0 && left + width <= SCREEN_W;
}

/** Слоты, которые реально видно на экране кухни. */
export function visibleSlots(): KitchenSlot[] {
  return KITCHEN_SLOTS.filter(isSlotVisible);
}
