import { memo } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  KITCHEN_ART, WALL_GRID, WALL_REGIONS, hasWallpaperVisual, intersectRect, wallpaperMotifs, wallpaperStyle,
} from '../domain/homeDecoration';
import type { WallRect } from '../domain/homeDecoration';

const position = ({ x, y, width, height }: WallRect) => ({
  left: x * WALL_GRID, top: y * WALL_GRID, width: width * WALL_GRID, height: height * WALL_GRID,
});

/** Code-native paper above the raster, strictly clipped around all fixed art. */
export const KitchenWallpaper = memo(function KitchenWallpaper({ itemId }: { itemId?: string | null }) {
  if (!itemId || itemId === 'wallpaper_default' || !hasWallpaperVisual(itemId)) return null;
  const paper = wallpaperStyle(itemId);
  const pattern = wallpaperMotifs(itemId).flatMap((mark) =>
    WALL_REGIONS.flatMap((wall) => { const part = intersectRect(mark, wall); return part ? [part] : []; }));
  return <View pointerEvents="none" testID={`kitchen-wallpaper-${itemId}`} style={styles.art}>
    {WALL_REGIONS.map((wall, index) => <View key={`wall-${index}`}
      style={[styles.pixel, position(wall), { backgroundColor: paper.base }]} />)}
    {pattern.map((mark, index) => <View key={`pattern-${index}`}
      style={[styles.pixel, position(mark), { backgroundColor: paper.ink, opacity: 0.5 }]} />)}
  </View>;
});

const styles = StyleSheet.create({
  art: { position: 'absolute', ...KITCHEN_ART },
  pixel: { position: 'absolute' },
});
