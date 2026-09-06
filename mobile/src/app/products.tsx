import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, ActionNotice, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { money } from '../domain/copy';
import { canCompleteCook, purchaseGroups, rewardText } from '../domain/mealFlow';

export default function ProductsScreen() {
  const router = useRouter();
  const {
    selectedMeal: meal, route, fulfillment, markdown,
    choices, chooseProduct, chooseRoute, basket, plan, savePlan, canConfirmPurchase, confirmPurchase, startCooking,
    busy, editable, loadRecipes,
  } = useDemo();
  if (!meal) return <SafeAreaView style={styles.safe}><AppHeader title="Мой план" />
    <View style={ui.panel}><Text style={ui.text}>Сначала выберите блюдо. Отдельного каталога случайных товаров здесь нет.</Text>
      <Choice label="Что поесть?" onPress={() => router.replace('/recipes')} /></View>
    <BottomNav active="kitchen" /></SafeAreaView>;
  const groups = purchaseGroups(meal, route, fulfillment, markdown);
  const stores = route === 'cook' ? meal.cook_variant?.store_selection : null;
  const variant = route === 'cook' ? meal.cook_variant : meal.ready_variant;
  const ready = route === 'cook' ? meal.ready_variant?.product_options[0] : null;
  const hasPlan = Boolean(plan);
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <AppHeader title="Мой план" subtitle={meal.title} />
    <ScrollView contentContainerStyle={styles.scroll}>
      {ready ? <>
        <Text style={styles.sectionTitle}>Можно не готовить</Text>
        <View style={styles.readyCard}>
          <PhotoStub label="фото" style={styles.readyPhoto} />
          <View style={styles.readyCopy}>
            <View style={styles.readyBadge}><Text style={styles.readyBadgeText}>Готовое блюдо</Text></View>
            <Text style={styles.priceLarge}>{money(ready.price)}</Text>
            <Text style={styles.readyUnit}>{Math.round(ready.distance_km * 1000)} м · {ready.store_id}</Text>
            <Text style={styles.readyName} numberOfLines={2}>{ready.name}</Text>
          </View>
          <Pressable style={styles.readyAdd} disabled={!editable} onPress={() => chooseRoute('ready')}>
            <Text style={styles.readyAddText}>Взять</Text>
          </Pressable>
        </View>
      </> : null}

      {route === 'ready' && meal.available_routes.includes('cook') ? <>
        <Text style={styles.sectionTitle}>Готовое блюдо выбрано</Text>
        <View style={styles.assistant}>
          <Image source={require('../../assets/domovoi/mascot-think.png')} resizeMode="contain" style={styles.assistantMascot} />
          <Text style={styles.assistantText}>Чек завершит сценарий сразу, без готовки.</Text>
        </View>
        <View style={{ paddingHorizontal: 16, marginBottom: 18 }}>
          <Pressable style={styles.cardAdd} disabled={!editable} onPress={() => chooseRoute('cook')}>
            <Text style={styles.cardAddText}>Вернуться к продуктам для рецепта</Text>
          </Pressable>
        </View>
      </> : null}

      {groups.map((group) => <View key={group.id} style={{ marginBottom: 18 }}>
        <View style={[styles.sectionRow, { marginHorizontal: 16 }]}>
          <Text style={[styles.sectionTitle, { marginHorizontal: 0 }]}>{group.name}</Text>
          <Text style={styles.sectionMeta}>{group.options.length ? `${group.options.length} товара` : ''}</Text>
        </View>
        {group.options.length === 0
          ? <Text style={styles.note}>Нет подходящего товара при этих настройках.</Text> : null}
        <View style={styles.grid}>
          {group.options.map((product) => {
            const selected = choices[group.id] ? choices[group.id] === product.sku_id : group.options[0]?.sku_id === product.sku_id;
            const cheaper = product.original_price != null && product.original_price > product.price;
            return <View key={product.sku_id} style={styles.card}>
              <View>
                <PhotoStub label="фото" style={styles.cardPhoto} />
                {product.source === 'markdown' ? <View style={[styles.markdownBadge, { position: 'absolute', left: 5, top: 5 }]}>
                  <Text style={styles.markdownBadgeText}>↓ уценка</Text></View> : null}
              </View>
              <View style={styles.priceRow}>
                <Text style={styles.price}>{money(product.price)}</Text>
                {cheaper ? <Text style={styles.oldPrice}>{money(product.original_price!)}</Text> : null}
              </View>
              <Text style={styles.cardUnit}>{Math.round(product.distance_km * 1000)} м</Text>
              <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
              <Pressable style={[styles.cardAdd, selected && styles.cardAddDone]} disabled={!editable}
                onPress={() => chooseProduct(group.id, product.sku_id)}>
                <Text style={[styles.cardAddText, selected && { color: color.white }]}>
                  {selected ? 'В корзине' : 'В корзину'}</Text>
              </Pressable>
            </View>;
          })}
        </View>
      </View>)}

      {!groups.length && !basket.error
        ? <Text style={styles.note}>Докупать нечего. Сохраните план и подтвердите готовку.</Text> : null}
      {basket.error ? <Text style={styles.error}>{basket.error}</Text> : null}
      <View style={{ paddingHorizontal: 16, marginTop: 8 }}><ActionNotice /></View>
      {hasPlan ? <Text style={styles.note}>{rewardText(plan)}</Text> : null}
    </ScrollView>

    <View style={styles.basketBar}>
      <Text style={styles.basketHint}>
        {!hasPlan ? 'Сохраните план' : canConfirmPurchase ? 'Подтвердите покупку' : canCompleteCook(plan) ? 'Можно готовить' : 'План сохранён'}
      </Text>
      <Pressable style={[styles.basket, busy && styles.basketOff]} disabled={busy}
        onPress={() => {
          if (!hasPlan) { void savePlan(); return; }
          if (canConfirmPurchase) { void confirmPurchase(); return; }
          if (canCompleteCook(plan)) { if (startCooking()) router.push('/'); return; }
          router.push('/profile');
        }}>
        <View style={styles.basketIcon} />
        <Text style={styles.basketText}>{money(basket.total)}</Text>
      </Pressable>
    </View>
    <BottomNav active="kitchen" />
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.bg },
  priceRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  oldPrice: { color: color.muted, fontSize: 13, textDecorationLine: 'line-through' },
  markdownBadge: { borderRadius: 8, paddingHorizontal: 7, paddingVertical: 4, backgroundColor: color.orange },
  markdownBadgeText: { color: color.white, fontSize: 11, fontWeight: '700' },
  scroll: { paddingTop: 16, paddingBottom: 190 },

  sectionTitle: { color: color.ink, fontSize: 17, fontWeight: '700', marginHorizontal: 16, marginBottom: 10 },
  sectionRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionMeta: { color: color.muted, fontSize: 12, fontWeight: '600', marginRight: 16 },

  readyCard: {
    marginHorizontal: 16, marginBottom: 22, padding: 10, backgroundColor: color.white,
    borderRadius: 20, flexDirection: 'row', gap: 12, alignItems: 'center',
  },
  readyPhoto: { width: 96, height: 96, borderRadius: 16 },
  readyCopy: { flex: 1 },
  readyBadge: {
    alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 5, borderRadius: 9,
    backgroundColor: color.greenSoft, marginBottom: 7,
  },
  readyBadgeText: { color: color.green, fontSize: 10.5, fontWeight: '700' },
  readyUnit: { color: color.muted, fontSize: 11.5, marginBottom: 4 },
  readyName: { color: color.ink, fontSize: 12.5, fontWeight: '600' },
  readyAdd: {
    alignSelf: 'flex-end', paddingHorizontal: 16, paddingVertical: 11,
    borderRadius: 14, backgroundColor: color.red, minHeight: 44, justifyContent: 'center',
  },
  readyAddText: { color: color.white, fontSize: 13, fontWeight: '700' },

  assistant: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 16, marginBottom: 12 },
  group: { marginBottom: 18 },
  groupHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 },
  groupName: { color: color.ink, fontSize: 17, fontWeight: '700' },
  groupMeta: { color: color.muted, fontSize: 12, fontWeight: '600' },
  groupRow: { gap: 10, paddingBottom: 2 },
  groupNote: { color: color.muted, fontSize: 12.5, lineHeight: 17, marginBottom: 10 },
  card: {
    width: 148, padding: 8, paddingBottom: 12, borderRadius: 16,
    backgroundColor: color.white, borderWidth: 2, borderColor: 'transparent',
  },
  cardSelected: { borderColor: color.green },
  cardPhoto: { height: 96, borderRadius: 12, marginBottom: 9 },
  tick: {
    position: 'absolute', right: 6, top: 6, width: 22, height: 22, borderRadius: 11,
    backgroundColor: color.green, alignItems: 'center', justifyContent: 'center',
  },
  tickText: { color: color.white, fontSize: 12, fontWeight: '700' },
  price: { color: color.ink, fontSize: 17, fontWeight: '700' },
  cardMeta: { color: color.muted, fontSize: 11, marginTop: 3 },
  cardName: { color: color.ink, fontSize: 12.5, lineHeight: 16, marginTop: 5, minHeight: 32 },

  totalCard: { backgroundColor: color.white, borderRadius: 18, padding: 14, marginTop: 4, marginBottom: 12 },
  totalRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 },
  totalLabel: { flex: 1, color: color.body, fontSize: 13.5 },
  totalValue: { color: color.ink, fontSize: 17, fontWeight: '700' },
  totalSaving: { color: color.green },
  totalHint: { color: color.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },

  assistantMascot: { width: 44, height: 44 },
  assistantText: { flex: 1, color: color.muted, fontSize: 12, lineHeight: 17 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, paddingHorizontal: 16 },
  kopecks: { fontSize: 10, lineHeight: 10 },
  priceLarge: { color: color.ink, fontSize: 22, fontWeight: '700', marginBottom: 5 },
  kopecksLarge: { fontSize: 13, lineHeight: 13 },
  cardUnit: { color: color.muted, fontSize: 10.5, marginBottom: 5 },
  rating: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 8 },
  ratingDot: { width: 9, height: 9, borderRadius: 2, backgroundColor: color.star },
  ratingText: { color: color.body, fontSize: 11, fontWeight: '600' },
  cardAdd: { paddingVertical: 10, borderRadius: 12, backgroundColor: color.bg, alignItems: 'center', minHeight: 40, justifyContent: 'center' },
  cardAddDone: { backgroundColor: color.green },
  cardAddText: { color: color.ink, fontSize: 12, fontWeight: '600' },

  note: { marginHorizontal: 16, marginTop: 18, color: color.body, fontSize: 13, lineHeight: 18 },
  error: { marginHorizontal: 16, marginTop: 12, color: color.red, fontSize: 13 },

  basketBar: {
    position: 'absolute', left: 0, right: 0, bottom: 74, paddingHorizontal: 16,
    paddingTop: 10, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12,
  },
  basketHint: { flex: 1, color: color.muted, fontSize: 13.5 },
  basket: {
    flexDirection: 'row', alignItems: 'center', gap: 10, height: 52, paddingHorizontal: 20,
    borderRadius: 26, backgroundColor: color.red,
  },
  basketOff: { backgroundColor: color.iconIdle },
  basketIcon: {
    width: 18, height: 16, borderWidth: 2, borderTopWidth: 0, borderColor: color.white,
    borderBottomLeftRadius: 6, borderBottomRightRadius: 6,
  },
  basketText: { color: color.white, fontSize: 15, fontWeight: '700' },
});
