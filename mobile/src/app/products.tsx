import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, ActionNotice, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { money } from '../domain/copy';
import { canCompleteCook, purchaseGroups, rewardText, taskTitle } from '../domain/mealFlow';

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
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <AppHeader title="Мой план" subtitle={meal.title} />
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
      <Text style={ui.title}>{taskTitle(meal.mode, route)}</Text>
      {stores ? <View style={ui.panel}>
        <Text style={ui.title}>Магазин: {stores.selected_store_id}</Text>
        {stores.options.map((store) => <View key={store.store_id}>
          <Text style={ui.text}>{store.store_id} · {Math.round(store.distance_km * 1000)} м · есть {store.covered_required_ingredients} из {store.total_required_ingredients}</Text>
          <Choice label={store.store_id === stores.selected_store_id ? 'Выбран' : 'Подобрать в этом магазине'}
            selected={store.store_id === stores.selected_store_id}
            disabled={!editable || !store.complete || store.store_id === stores.selected_store_id}
            onPress={() => { void loadRecipes({ storeId: store.store_id }); router.replace('/recipes'); }} />
        </View>)}
      </View> : null}
      {route === 'cook' && meal.ready_variant?.product_options.length ? <View style={styles.group}>
        <View style={styles.groupHead}>
          <Text style={styles.groupName}>Можно не готовить</Text>
        </View>
        <Text style={styles.groupNote}>Готовое блюдо вместо продуктов для рецепта. Чек завершает сценарий сразу.</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.groupRow}>
          {meal.ready_variant.product_options.map((product) => <View key={product.sku_id} style={styles.card}>
            <PhotoStub label="фото" style={styles.cardPhoto} />
            <View style={styles.priceRow}><Text style={styles.price}>{money(product.price)}</Text></View>
            <Text style={styles.cardMeta}>{Math.round(product.distance_km * 1000)} м · {product.store_id}</Text>
            <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
          </View>)}
        </ScrollView>
        <Choice label="Взять готовое вместо продуктов" disabled={!editable}
          onPress={() => chooseRoute('ready')} />
      </View> : null}
      {route === 'ready' && meal.available_routes.includes('cook') ? <View style={styles.group}>
        <Choice label="Вернуться к продуктам для рецепта" disabled={!editable}
          onPress={() => chooseRoute('cook')} />
      </View> : null}
      {groups.map((group) => <View key={group.id} style={styles.group}>
        <View style={styles.groupHead}>
          <Text style={styles.groupName}>
            {group.id === 'ready' ? 'Можно не готовить' : group.name}
          </Text>
          <Text style={styles.groupMeta}>{group.options.length
            ? `${group.options.length} ${group.options.length === 1 ? 'вариант' : 'варианта'}` : ''}</Text>
        </View>
        {group.id === 'ready'
          ? <Text style={styles.groupNote}>Готовое блюдо вместо продуктов для рецепта. Чек завершает сценарий сразу.</Text>
          : null}
        {group.options.length === 0
          ? <Text style={ui.text}>Нет подходящего товара при этих настройках.</Text> : null}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.groupRow}>
          {group.options.map((product) => {
            const selected = choices[group.id] ? choices[group.id] === product.sku_id : group.options[0]?.sku_id === product.sku_id;
            const cheaper = product.original_price != null && product.original_price > product.price;
            return <Pressable key={product.sku_id} disabled={!editable}
              onPress={() => chooseProduct(group.id, product.sku_id)}
              style={[styles.card, selected && styles.cardSelected]}>
              <View>
                <PhotoStub label="фото" style={styles.cardPhoto} />
                {product.source === 'markdown' ? <View style={styles.markdownBadge}>
                  <Text style={styles.markdownBadgeText}>↓ уценка</Text></View> : null}
                {selected ? <View style={styles.tick}><Text style={styles.tickText}>✓</Text></View> : null}
              </View>
              <View style={styles.priceRow}>
                <Text style={styles.price}>{money(product.price)}</Text>
                {cheaper ? <Text style={styles.oldPrice}>{money(product.original_price!)}</Text> : null}
              </View>
              <Text style={styles.cardMeta}>{Math.round(product.distance_km * 1000)} м · {product.store_id}</Text>
              <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
              {product.expires_at ? <Text style={styles.cardMeta}>срок: {product.expires_at}</Text> : null}
            </Pressable>;
          })}
        </ScrollView>
      </View>)}
      {!groups.length && !basket.error ? <View style={ui.panel}>
        <Text style={ui.title}>Докупки не нужны</Text><Text style={ui.text}>Проверьте продукты дома. Сохраните план и подтвердите готовку без покупки.</Text>
      </View> : null}
      <View style={styles.totalCard}>
        <View style={styles.totalRow}>
          <Text style={styles.totalLabel}>Товары</Text>
          <Text style={styles.totalValue}>{money(basket.total)}</Text>
        </View>
        <View style={styles.totalRow}>
          <Text style={styles.totalLabel}>Экономия по выбранным ценам</Text>
          <Text style={[styles.totalValue, styles.totalSaving]}>{money(basket.savings)}</Text>
        </View>
        <Text style={styles.totalHint}>{rewardText(plan)} В личную статистику экономия попадёт только после чека.</Text>
      </View>
      {basket.error ? <Text style={[ui.text, { color: color.red }]}>{basket.error}</Text> : null}
      <ActionNotice />
      {!plan ? <Choice label={editable ? 'Выбрать задание и сохранить план' : 'Повторить сохранение того же плана'}
        disabled={busy || Boolean(basket.error)} onPress={() => void savePlan()} /> : <>
        <Text style={ui.text}>План: {({ saved: 'сохранён', collected: 'продукты куплены', completed: 'блюдо завершено', cancelled: 'отменён' })[plan.status]}</Text>
        {canConfirmPurchase ? <Choice
          label={plan.status === 'saved' ? 'Демо: подтвердить чек выбранных товаров' : 'Демо: повторить тот же чек (без новых XP)'}
          disabled={busy} onPress={() => void confirmPurchase()} /> : null}
        {canCompleteCook(plan) ? <Choice label="Начать готовить" disabled={busy}
          onPress={() => { if (startCooking()) router.push('/'); }} /> : null}
        {plan.status === 'completed' ? <Choice label="Посмотреть прогресс" disabled={busy} onPress={() => router.push('/profile')} /> : null}
      </>}
      <View style={ui.choices}><Choice label="Выбрать другое блюдо" disabled={busy}
        onPress={() => { void loadRecipes(); router.replace('/recipes'); }} /></View>
    </ScrollView>
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
