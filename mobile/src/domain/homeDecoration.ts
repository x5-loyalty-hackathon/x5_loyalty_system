/** Visuals only. Access, prices (none), and goals come from the API catalog. */
export const wallpaperStyles = {
  wallpaper_default: { base: '#EEDDB9', ink: '#D8C399', motif: 'grain' },
  wallpaper_mint: { base: '#9FCDB8', ink: '#5E9980', motif: 'leaf' },
  wallpaper_sunset: { base: '#EDBA99', ink: '#CD8165', motif: 'diamond' },
  wallpaper_sky: { base: '#AACDE0', ink: '#6E9CB8', motif: 'cloud' },
  wallpaper_night: { base: '#394C70', ink: '#D9CA92', motif: 'star' },
  wallpaper_berry: { base: '#CEA2B7', ink: '#985E7D', motif: 'berry' },
} as const;
export type WallpaperId = keyof typeof wallpaperStyles;
export function wallpaperStyle(itemId: string | null | undefined) {
  return wallpaperStyles[itemId as WallpaperId] ?? wallpaperStyles.wallpaper_default;
}
export function hasWallpaperVisual(itemId: string): itemId is WallpaperId {
  return Object.hasOwn(wallpaperStyles, itemId);
}

export interface WallRect { x: number; y: number; width: number; height: number }
const rect = (x: number, y: number, width: number, height: number): WallRect => ({ x, y, width, height });
/** Original 1170×1560 art uses a 10px grid. One grid cell is 4 layout points. */
export const KITCHEN_ART = { left: -39, top: 0, width: 468, height: 624 };
export const WALL_GRID = 4;
// Tight silhouettes, including their pixel shadows: chimney/stove, pot, shelves,
// hooks, vase, window/sill and board. These pixels must remain original art.
export const WALL_OBJECTS: readonly WallRect[] = [
  rect(0, 0, 18, 55), rect(0, 55, 36, 5), rect(0, 60, 34, 2),
  rect(19, 46, 13, 1), rect(23, 43, 3, 2), rect(27, 45, 3, 2),
  rect(18, 47, 13, 10), rect(31, 50, 3, 1), rect(31, 51, 2, 2),
  rect(37, 9, 9, 2), rect(38, 11, 7, 7),
  rect(34, 18, 36, 5), rect(36, 24, 3, 2), rect(67, 24, 2, 2),
  rect(36, 26, 32, 2),
  rect(42, 28, 1, 4), rect(43, 30, 2, 1),
  rect(49, 28, 1, 4), rect(50, 30, 1, 1),
  rect(56, 28, 1, 4), rect(57, 30, 2, 1),
  rect(63, 28, 1, 4), rect(64, 30, 2, 1),
  rect(34, 38, 36, 5), rect(36, 44, 3, 2), rect(66, 44, 3, 2),
  rect(74, 14, 34, 30), rect(71, 44, 40, 5),
  rect(61, 58, 21, 1), rect(61, 59, 26, 2), rect(62, 61, 26, 1), rect(47, 61, 1, 1),
];
export function intersectRect(a: WallRect, b: WallRect): WallRect | null {
  const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  return right > x && bottom > y ? rect(x, y, right - x, bottom - y) : null;
}
// Merge consecutive wall pixels into horizontal strips. Every strip and motif
// shares the original art origin, so paper is seamless between cutouts.
export const WALL_REGIONS: readonly WallRect[] = Array.from({ length: 62 }, (_, y) => {
  const strips: WallRect[] = [];
  for (let x = 18; x < 117; x++) {
    if (WALL_OBJECTS.some((object) => intersectRect(rect(x, y, 1, 1), object))) continue;
    const previous = strips.at(-1);
    if (previous && previous.x + previous.width === x) previous.width += 1;
    else strips.push(rect(x, y, 1, 1));
  }
  return strips;
}).flat();

export function wallpaperMotifs(itemId: string): WallRect[] {
  const motif = wallpaperStyle(itemId).motif;
  const marks: WallRect[] = [];
  for (let y = 5; y < 62; y += 11) {
    for (let x = 21 + (Math.floor(y / 11) % 2) * 5; x < 117; x += 12) {
      if (motif === 'leaf') marks.push(rect(x, y, 1, 2), rect(x + 1, y - 1, 1, 1), rect(x - 1, y, 1, 1));
      else if (motif === 'diamond') marks.push(rect(x, y - 1, 1, 3), rect(x - 1, y, 3, 1));
      else if (motif === 'cloud') marks.push(rect(x, y, 3, 1), rect(x + 1, y - 1, 1, 1));
      else if (motif === 'star') marks.push(rect(x, y - 1, 0.5, 2.5), rect(x - 1, y, 2.5, 0.5));
      else if (motif === 'berry') marks.push(rect(x, y, 1, 1), rect(x + 1.5, y + 1, 1, 1), rect(x + 1, y - 1, 0.5, 1));
      else marks.push(rect(x, y, 0.5, 0.5));
    }
  }
  return marks;
}
