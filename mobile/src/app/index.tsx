import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { KitchenScene } from '../components/KitchenScene';
import { PhotoStub } from '../components/PhotoStub';
import { kitchenProducts, type KitchenProduct } from '../data/demo';
import { color } from '../theme/tokens';

type Filter = 'all' | 'soon';

const TONE: Record<KitchenProduct['tone'], string> = {
  good: color.green,
  soon: color.orange,
  today: color.red,
};

export default function KitchenScreen() {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>('all');

  const soonCount = kitchenProducts.filter((item) => item.tone !== 'good').length;
  const products =
    filter === 'soon' ? kitchenProducts.filter((item) => item.tone !== 'good') : kitchenProducts;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <KitchenScene
            products={kitchenProducts}
            speech="Молоко надо выпить сегодня. Сварим что-нибудь?"
          />

          <View style={styles.sheet}>
            <View style={styles.sectionTitleRow}>
              <Text style={styles.title}>Что есть на кухне</Text>
              <Text style={styles.count}>по чекам · {kitchenProducts.length}</Text>
            </View>

            <View style={styles.filters}>
              <FilterChip
                label="Все"
                selected={filter === 'all'}
                onPress={() => setFilter('all')}
              />
              <FilterChip
                label={`Скоро испортится · ${soonCount}`}
                selected={filter === 'soon'}
                onPress={() => setFilter('soon')}
              />
            </View>

            <View style={styles.grid}>
              {products.map((product) => (
                <KitchenCard key={product.id} product={product} />
              ))}
            </View>

            <View style={styles.hint}>
              <View style={styles.hintMark}>
                <Text style={styles.hintMarkText}>×2</Text>
              </View>
              <Text style={styles.hintText}>
                Из этих продуктов Домовой собрал 2 рецепта без докупок
              </Text>
            </View>
          </View>
        </ScrollView>

        <View style={styles.ctaWrap}>
          <Pressable style={styles.cta} onPress={() => router.push('/recipes')}>
            <Text style={styles.ctaText}>Что приготовить</Text>
            <Text style={styles.ctaArrow}>›</Text>
          </Pressable>
        </View>
        <BottomNav active="kitchen" />
      </View>
    </SafeAreaView>
  );
}

function FilterChip({
  label, selected, onPress,
}: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.filter, selected && styles.filterSelected]} onPress={onPress}>
      <Text style={[styles.filterText, selected && styles.filterTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function KitchenCard({ product }: { product: KitchenProduct }) {
  return (
    <View style={styles.card}>
      <PhotoStub style={styles.cardPhoto} />
      <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
      <Text style={styles.cardQty}>{product.quantity}</Text>
      <View style={styles.pill}>
        <View style={[styles.pillDot, { backgroundColor: TONE[product.tone] }]} />
        <Text style={styles.pillText}>{product.expires}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.cream },
  shell: { flex: 1, backgroundColor: color.bg },
  scroll: { paddingBottom: 168 },

  sheet: {
    marginTop: -18, paddingHorizontal: 16, paddingTop: 18, backgroundColor: color.bg,
    borderTopLeftRadius: 22, borderTopRightRadius: 22, minHeight: 420,
  },
  sectionTitleRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12,
  },
  title: { color: color.ink, fontSize: 22, fontWeight: '700' },
  count: { color: color.muted, fontSize: 13, fontWeight: '600' },

  filters: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  filter: {
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 18, backgroundColor: color.white,
    minHeight: 36, justifyContent: 'center',
  },
  filterSelected: { backgroundColor: color.ink },
  filterText: { color: color.ink, fontSize: 13, fontWeight: '600' },
  filterTextSelected: { color: color.white },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: {
    width: '31%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16,
    padding: 8, paddingBottom: 12,
  },
  cardPhoto: { height: 78, borderRadius: 12, marginBottom: 8 },
  cardName: { color: color.ink, fontSize: 12, lineHeight: 15, fontWeight: '600', marginBottom: 3 },
  cardQty: { color: color.muted, fontSize: 11, marginBottom: 7 },
  pill: {
    alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 7, paddingVertical: 4, borderRadius: 9, backgroundColor: color.bg,
  },
  pillDot: { width: 6, height: 6, borderRadius: 3 },
  pillText: { color: color.body, fontSize: 10.5, fontWeight: '600' },

  hint: {
    marginTop: 16, padding: 14, backgroundColor: color.white, borderRadius: 18,
    flexDirection: 'row', alignItems: 'center', gap: 12,
  },
  hintMark: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: color.greenSoft,
    alignItems: 'center', justifyContent: 'center',
  },
  hintMarkText: { color: color.green, fontSize: 15, fontWeight: '700' },
  hintText: { flex: 1, color: color.body, fontSize: 12.5, lineHeight: 17.5 },

  ctaWrap: { position: 'absolute', left: 0, right: 0, bottom: 74, paddingHorizontal: 16, paddingBottom: 12 },
  cta: {
    height: 54, borderRadius: 16, backgroundColor: color.red, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.7 },
});
