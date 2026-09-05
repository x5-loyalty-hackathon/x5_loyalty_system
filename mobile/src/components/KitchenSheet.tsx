import { useEffect, useRef } from 'react';
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
  collapsedHeight,
  expandedHeight,
  expanded,
  onChange,
  children,
}: {
  collapsedHeight: number;
  expandedHeight: number;
  expanded: boolean;
  onChange: (expanded: boolean) => void;
  children: React.ReactNode;
}) {
  const height = useRef(new Animated.Value(expanded ? expandedHeight : collapsedHeight)).current;
  const start = useRef(expanded ? expandedHeight : collapsedHeight);

  useEffect(() => {
    Animated.spring(height, {
      toValue: expanded ? expandedHeight : collapsedHeight,
      useNativeDriver: false,
      bounciness: 4,
    }).start();
  }, [collapsedHeight, expanded, expandedHeight, height]);

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_event, gesture) => Math.abs(gesture.dy) > 6,
      onPanResponderGrant: () => {
        height.stopAnimation((value: number) => {
          start.current = value;
        });
      },
      onPanResponderMove: (_event, gesture) => {
        // Тянем вверх — панель растёт, поэтому знак инвертирован.
        const next = start.current - gesture.dy;
        height.setValue(Math.min(expandedHeight, Math.max(collapsedHeight, next)));
      },
      onPanResponderRelease: (_event, gesture) => {
        const next = start.current - gesture.dy;
        const middle = (collapsedHeight + expandedHeight) / 2;
        // Быстрый рывок решает за пользователя, медленный — по середине хода.
        const shouldExpand =
          Math.abs(gesture.vy) > 0.5 ? gesture.vy < 0 : next > middle;
        onChange(shouldExpand);
      },
    }),
  ).current;

  return (
    <Animated.View style={[styles.sheet, { height }]}>
      <View style={styles.handleArea} {...pan.panHandlers}>
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
  handleArea: { paddingTop: 8, paddingBottom: 6, alignItems: 'center' },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: color.iconIdle },
  body: { flex: 1 },
});
