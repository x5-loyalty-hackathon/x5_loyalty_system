import { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { KitchenScene } from '../components/KitchenScene';
import { KitchenSheet } from '../components/KitchenSheet';
import { PhotoStub } from '../components/PhotoStub';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import type { KitchenProduct } from '../data/demo';

type Filter = 'all' | 'soon';

const TONE: Record<KitchenProduct['tone'], string> = {
  good: color.green,
  soon: color.orange,
  today: color.red,
};

const SHEET_COLLAPSED = 200;
/** Раскрытая шторка оставляет сверху ровно столько комнаты, сколько в макете. */
const SCENE_VISIBLE_WHEN_EXPANDED = 268;

export default function KitchenScreen() {
  const router = useRouter();
  const { pantry, cookingRecipe, finishCooking, cookingStatus, cookingError } = useDemo();
  const [filter, setFilter] = useState<Filter>('all');
  const [expanded, setExpanded] = useState(false);
  // Сцена занимает весь контейнер, шторка лежит поверх её нижней части.
  const [stageHeight, setStageHeight] = useState(0);
  // Высотой шторки владеет экран: к ней привязан и лист, и Домовой, поэтому
  // он едет вместе со шторкой и всегда стоит на её краю.
  const sheetHeight = useRef(new Animated.Value(SHEET_COLLAPSED)).current;
  const expandedHeight = Math.max(
    SHEET_COLLAPSED + 1,
    stageHeight - SCENE_VISIBLE_WHEN_EXPANDED,
  );

  // Начали готовить — шаги нужны сразу, поэтому шторка раскрывается сама.
  useEffect(() => {
    if (cookingRecipe) setExpanded(true);
  }, [cookingRecipe]);

  useEffect(() => {
    Animated.spring(sheetHeight, {
      toValue: expanded ? expandedHeight : SHEET_COLLAPSED,
      useNativeDriver: false,
      bounciness: 4,
    }).start();
  }, [expanded, expandedHeight, sheetHeight]);

  const soonCount = pantry.filter((item) => item.tone !== 'good').length;
  const products = filter === 'soon' ? pantry.filter((item) => item.tone !== 'good') : pantry;

  const onFinish = async () => {
    await finishCooking();
    setExpanded(false);
    router.push('/profile');
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <View
          style={styles.stage}
          onLayout={(event) => setStageHeight(event.nativeEvent.layout.height)}
        >
        <KitchenScene
          height={stageHeight}
          mascotBottom={sheetHeight}
          products={pantry}
          pose={cookingRecipe ? 'cooking' : 'idle'}
          speech={
            cookingRecipe
              ? `Готовим «${cookingRecipe.title}». Скажи, когда закончишь.`
              : 'Молоко надо выпить сегодня. Сварим что-нибудь?'
          }
        />

        <View style={styles.sheetWrap} pointerEvents="box-none">
          <KitchenSheet
            height={sheetHeight}
            collapsedHeight={SHEET_COLLAPSED}
            expandedHeight={expandedHeight}
            expanded={expanded}
            onChange={setExpanded}
          >
            {cookingRecipe ? (
              <>
                <View style={styles.head}>
                  <Text style={styles.title} numberOfLines={1}>{cookingRecipe.title}</Text>
                  <Text style={styles.count}>{cookingRecipe.time} мин</Text>
                </View>
                <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                  {cookingRecipe.steps.map((step, index) => (
                    <View key={step.title} style={styles.step}>
                      <View style={styles.stepNum}>
                        <Text style={styles.stepNumText}>{index + 1}</Text>
                      </View>
                      <Text style={styles.stepTitle}>{step.title}</Text>
                      <Text style={styles.stepTime}>{step.minutes} мин</Text>
                    </View>
                  ))}
                  {cookingError ? <Text style={styles.error}>{cookingError}</Text> : null}
                </ScrollView>
                <View style={styles.ctaWrap}>
                  <Pressable
                    style={[styles.cta, styles.ctaDone]}
                    disabled={cookingStatus === 'loading'}
                    onPress={onFinish}
                  >
                    <Text style={styles.ctaText}>
                      {cookingStatus === 'loading' ? 'Записываю…' : 'Я закончил'}
                    </Text>
                  </Pressable>
                </View>
              </>
            ) : (
              <>
                <View style={styles.head}>
                  <Text style={styles.title}>Что есть на кухне</Text>
                  <Text style={styles.count}>по чекам · {pantry.length}</Text>
                </View>
                <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                  <View style={styles.filters}>
                    <FilterChip label="Все" selected={filter === 'all'} onPress={() => setFilter('all')} />
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
                </ScrollView>
                <View style={styles.ctaWrap}>
                  <Pressable style={styles.cta} onPress={() => router.push('/recipes')}>
                    <Text style={styles.ctaText}>Что приготовить</Text>
                    <Text style={styles.ctaArrow}>›</Text>
                  </Pressable>
                </View>
              </>
            )}
          </KitchenSheet>
        </View>
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
  shell: { flex: 1, backgroundColor: color.cream },

  /** Сцена и шторка живут в одном слое: шторка прижата к его низу. */
  stage: { flex: 1 },
  sheetWrap: {
    position: 'absolute', left: 0, right: 0, bottom: 0, top: 0,
    justifyContent: 'flex-end',
  },

  head: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingBottom: 10,
  },
  title: { flex: 1, color: color.ink, fontSize: 20, fontWeight: '700' },
  count: { color: color.muted, fontSize: 13, fontWeight: '600', marginLeft: 12 },

  scroll: { paddingHorizontal: 16, paddingBottom: 12 },

  filters: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  filter: {
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 18,
    backgroundColor: color.white, minHeight: 36, justifyContent: 'center',
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

  step: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: color.line,
  },
  stepNum: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: color.white,
    alignItems: 'center', justifyContent: 'center',
  },
  stepNumText: { color: color.ink, fontSize: 12.5, fontWeight: '700' },
  stepTitle: { flex: 1, color: color.ink, fontSize: 14, fontWeight: '500' },
  stepTime: { color: color.red, fontSize: 12.5, fontWeight: '700' },
  error: { color: color.red, fontSize: 13, marginTop: 12 },

  ctaWrap: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12 },
  cta: {
    height: 54, borderRadius: 16, backgroundColor: color.red, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  ctaDone: { backgroundColor: color.green },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.7 },
});
