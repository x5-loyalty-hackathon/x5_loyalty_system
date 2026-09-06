import { useRef } from 'react';
import { Animated, PanResponder, StyleSheet, View } from 'react-native';
import { color } from '../theme/tokens';

/**
 * Шторка над кухней: свёрнутая показывает только заголовок, развёрнутая —
 * полный список. Тянется пальцем снизу вверх и обратно; отпускание
 * доводит её до ближайшего положения.
 *
 * Сделана на встроенных Animated и PanResponder: reanimated в проект не
 * тянем, ради одной панели это лишняя нативная зависимость.
 */
export function KitchenSheet({
  height,
  collapsedHeight,
  expandedHeight,
  expanded,
  onChange,
  children,
}: {
  /** Высотой владеет экран; персонаж остаётся на полу за панелью. */
  height: Animated.Value;
  collapsedHeight: number;
  expandedHeight: number;
  expanded: boolean;
  onChange: (expanded: boolean) => void;
  children: React.ReactNode;
}) {
  const start = useRef(expanded ? expandedHeight : collapsedHeight);
  // PanResponder is retained across renders; layout/callbacks must stay fresh.
  const latest = useRef({ height, collapsedHeight, expandedHeight, expanded, onChange });
  latest.current = { height, collapsedHeight, expandedHeight, expanded, onChange };

  const pan = useRef(
    PanResponder.create({
      // Захватываем и касание тоже: иначе на вебе Pressable и PanResponder на
      // одном элементе отбирают жест друг у друга, и не срабатывает ни тап,
      // ни перетаскивание. Короткое касание ниже трактуем как тап.
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_event, gesture) => Math.abs(gesture.dy) > 6,
      onPanResponderGrant: () => {
        latest.current.height.stopAnimation((value: number) => {
          start.current = value;
        });
      },
      onPanResponderMove: (_event, gesture) => {
        // Тянем вверх — панель растёт, поэтому знак инвертирован.
        const next = start.current - gesture.dy;
        const current = latest.current;
        current.height.setValue(Math.min(current.expandedHeight, Math.max(current.collapsedHeight, next)));
      },
      onPanResponderRelease: (_event, gesture) => {
        const current = latest.current;
        // Палец почти не двигался — это нажатие, переключаем положение.
        if (Math.abs(gesture.dy) < 5 && Math.abs(gesture.dx) < 5) {
          current.onChange(!current.expanded);
          return;
        }
        const next = start.current - gesture.dy;
        const middle = (current.collapsedHeight + current.expandedHeight) / 2;
        // Быстрый рывок решает за пользователя, медленный — по середине хода.
        const shouldExpand =
          Math.abs(gesture.vy) > 0.5 ? gesture.vy < 0 : next > middle;
        current.onChange(shouldExpand);
      },
      onPanResponderTerminate: () => {
        const current = latest.current;
        current.height.setValue(current.expanded ? current.expandedHeight : current.collapsedHeight);
      },
    }),
  ).current;

  return (
    <Animated.View style={[styles.sheet, { height }]}>
      <View style={styles.handleArea} {...pan.panHandlers} accessibilityRole="button"
        accessibilityLabel={expanded ? 'Свернуть панель кухни' : 'Развернуть панель кухни'}
        accessibilityState={{ expanded }}>
        <View style={styles.handle} />
      </View>
      <View style={styles.body}>{children}</View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: color.bg,
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    overflow: 'hidden',
    shadowColor: color.brown,
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -4 },
    elevation: 8,
  },
  /** Зона захвата шире самой полоски, чтобы попадать пальцем. */
  handleArea: { minHeight: 44, justifyContent: 'center', alignItems: 'center' },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: color.iconIdle },
  body: { flex: 1 },
});
