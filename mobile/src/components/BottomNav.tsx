import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { color } from '../theme/tokens';

type NavKey = 'kitchen' | 'recipes' | 'profile';
// «Мой план» отдельной вкладкой нет: экран принадлежит выбранному блюду и
// пустует, пока блюдо не выбрано. Вход в план — с кухни и из карточки рецепта.
const items: Array<{ key: NavKey; label: string; glyph: string; route?: '/' | '/recipes' | '/products' | '/profile' }> = [
  { key: 'kitchen', label: 'Кухня', glyph: '■', route: '/' },
  { key: 'recipes', label: 'Рецепты', glyph: '▤', route: '/recipes' },
  { key: 'profile', label: 'Профиль', glyph: '●', route: '/profile' },
];

export function BottomNav({ active }: { active: NavKey }) {
  const router = useRouter();
  return (
    <View style={styles.root}>
      {items.map((item) => {
        const selected = item.key === active;
        return (
          <Pressable key={item.key} onPress={() => item.route && router.replace(item.route)} style={styles.item}>
            <Text style={[styles.glyph, selected && styles.selected]}>{item.glyph}</Text>
            <Text style={[styles.label, selected && styles.selected]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { height: 74, flexDirection: 'row', backgroundColor: color.white, borderTopWidth: 1, borderTopColor: color.line, paddingBottom: 8 },
  item: { flex: 1, minHeight: 48, alignItems: 'center', justifyContent: 'center', gap: 4 },
  glyph: { color: color.iconIdle, fontSize: 18, fontWeight: '700' },
  label: { color: color.muted, fontSize: 11, fontWeight: '600' },
  selected: { color: color.ink },
});
