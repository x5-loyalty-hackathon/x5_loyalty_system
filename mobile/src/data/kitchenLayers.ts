import type { ImageSourcePropType } from 'react-native';
import { BAND_OFFSET_X, CELL } from './kitchenSlots';

/**
 * Базовая кухня разложена на независимые спрайты на общей сетке 117x156.
 *
 * `rect` — положение обрезанного PNG в клетках исходной сцены. Каждый файл
 * хранит только свой фрагмент и прозрачность вокруг него, поэтому варианты
 * оформления можно менять по одному, не экспортируя комнату целиком.
 * Порядок массива одновременно является порядком отрисовки слоёв.
 */
export interface KitchenLayer {
  id:
    | 'wall'
    | 'floor'
    | 'window'
    | 'stove'
    | 'cabinets'
    | 'shelves'
    | 'shelf-decor'
    | 'window-decor'
    | 'counter-decor'
    | 'textile-decor';
  rect: readonly [number, number, number, number];
  source: ImageSourcePropType;
}

export const KITCHEN_BASE_LAYERS: readonly KitchenLayer[] = [
  { id: 'wall', rect: [0, 0, 117, 62], source: require('../../assets/kitchen/base/wall.png') },
  { id: 'floor', rect: [0, 113, 117, 43], source: require('../../assets/kitchen/base/floor.png') },
  { id: 'window', rect: [71, 14, 40, 35], source: require('../../assets/kitchen/base/window.png') },
  { id: 'stove', rect: [0, 3, 34, 110], source: require('../../assets/kitchen/base/stove.png') },
  { id: 'cabinets', rect: [34, 62, 83, 51], source: require('../../assets/kitchen/base/cabinets.png') },
  { id: 'shelves', rect: [33, 18, 37, 28], source: require('../../assets/kitchen/base/shelves.png') },
  { id: 'shelf-decor', rect: [37, 9, 9, 9], source: require('../../assets/kitchen/base/shelf-decor.png') },
  { id: 'window-decor', rect: [99, 31, 9, 12], source: require('../../assets/kitchen/base/window-decor.png') },
  { id: 'counter-decor', rect: [61, 58, 26, 4], source: require('../../assets/kitchen/base/counter-decor.png') },
  { id: 'textile-decor', rect: [103, 68, 8, 13], source: require('../../assets/kitchen/base/textile-decor.png') },
] as const;

/** Переводит обрезанный слой из клеток исходного арта в координаты сцены. */
export function kitchenLayerRect(layer: KitchenLayer) {
  const [x, y, width, height] = layer.rect;
  return {
    left: x * CELL + BAND_OFFSET_X,
    top: y * CELL,
    width: width * CELL,
    height: height * CELL,
  };
}
