import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { Choice, ActionNotice, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { money, explain } from '../domain/copy';
import { canCompleteCook, purchaseGroups, rewardText, taskTitle } from '../domain/mealFlow';

export default function ProductsScreen() {
  const router = useRouter();
  const {
    selectedMeal: meal, route, fulfillment, chooseFulfillment, markdown, chooseMarkdown,
    choices, chooseProduct, basket, plan, savePlan, confirmPurchase, startCooking,
    busy, editable, loadRecipes,
  } = useDemo();
  if (!meal) return <SafeAreaView style={styles.safe}><AppHeader title="Мой план" />
    <View style={ui.panel}><Text style={ui.text}>Сначала выберите блюдо. Отдельного каталога случайных товаров здесь нет.</Text>
      <Choice label="Что поесть?" onPress={() => router.replace('/recipes')} /></View>
    <BottomNav active="catalog" /></SafeAreaView>;
  const groups = purchaseGroups(meal, route, fulfillment, markdown);
  const stores = route === 'cook' ? meal.cook_variant?.store_selection : null;
  const variant = route === 'cook' ? meal.cook_variant : meal.ready_variant;
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <AppHeader title="Мой план" subtitle={meal.title} />
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
      <Text style={ui.title}>{taskTitle(meal.mode, route)}</Text>
      <View style={[styles.assistant, { marginHorizontal: 0 }]}>
        <Image source={require('../../assets/domovoi/mascot-bag.png')} resizeMode="contain" style={styles.assistantMascot} />
        <Text style={styles.assistantText}>Один магазин, только товары выбранного блюда. Цены за целые упаковки, не за долю в рецепте.</Text>
      </View>
      <View style={ui.choices}>{(['delivery', 'next_visit'] as const).map((option) =>
        <Choice key={option} label={option === 'delivery' ? 'Доставка' : 'Следующий визит'}
          selected={fulfillment === option} disabled={!editable || !variant?.fulfillment_options.includes(option)}
          onPress={() => chooseFulfillment(option)} />)}</View>
      <Choice label={markdown ? '✓ Рассматривать уценку' : 'Рассматривать уценку'} selected={markdown}
        disabled={!editable} onPress={() => chooseMarkdown(!markdown)} />
      <Text style={ui.text}>Без уценки выбирается обычная цена. Если подходящего товара нет, план нельзя сохранить.</Text>
      {stores ? <View style={ui.panel}>
        <Text style={ui.title}>Магазин: {stores.selected_store_id}</Text>
        <Text style={ui.text}>{explain(stores.reason_codes)}</Text>
        {stores.options.map((store) => <View key={store.store_id}>
          <Text style={ui.text}>{store.store_id} · {Math.round(store.distance_km * 1000)} м · есть {store.covered_required_ingredients} из {store.total_required_ingredients}</Text>
          <Choice label={store.store_id === stores.selected_store_id ? 'Выбран' : 'Подобрать в этом магазине'}
            selected={store.store_id === stores.selected_store_id}
            disabled={!editable || !store.complete || store.store_id === stores.selected_store_id}
            onPress={() => { void loadRecipes({ storeId: store.store_id }); router.replace('/recipes'); }} />
        </View>)}
      </View> : null}
      {groups.map((group) => <View key={group.id} style={ui.panel}>
        <Text style={ui.title}>{group.name}</Text>
        {group.options.length === 0 ? <Text style={ui.text}>Нет подходящего товара при этих настройках.</Text> : null}
        {group.options.map((product) => {
          const selected = choices[group.id] ? choices[group.id] === product.sku_id : group.options[0]?.sku_id === product.sku_id;
          return <View key={product.sku_id}>
            <Text style={ui.text}>{product.name} · {product.store_id} · {Math.round(product.distance_km * 1000)} м</Text>
            <View style={styles.priceRow}>
              <Text style={ui.text}>{money(product.price)} / упаковка</Text>
              {product.source === 'markdown' ? <>
                {product.original_price != null && product.original_price > product.price
                  ? <Text style={styles.oldPrice}>{money(product.original_price)}</Text> : null}
                <View style={styles.markdownBadge}><Text style={styles.markdownBadgeText}>↓ уценка</Text></View>
              </> : <Text style={ui.text}>Обычная цена</Text>}
            </View>
            {product.expires_at ? <Text style={ui.text}>Срок в demo-остатках: {product.expires_at}</Text> : null}
            <Choice label={selected ? '✓ Выбрано' : 'Выбрать'} selected={selected} disabled={!editable}
              onPress={() => chooseProduct(group.id, product.sku_id)} />
          </View>;
        })}
      </View>)}
      {!groups.length && !basket.error ? <View style={ui.panel}>
        <Text style={ui.title}>Докупки не нужны</Text><Text style={ui.text}>Проверьте продукты дома. Сохраните план и подтвердите готовку без покупки.</Text>
      </View> : null}
      <Text style={ui.title}>Товары: {money(basket.total)}</Text>
      <Text style={ui.text}>{rewardText(plan)}</Text>
      <Text style={ui.text}>Экономия по выбранным ценам: {money(basket.savings)}. В личную статистику попадёт только после чека.</Text>
      <Text style={ui.text}>В демо — одна упаковка на выбранный ингредиент. Проверка достаточности граммовок ещё не реализована.</Text>
      {fulfillment === 'delivery' ? <Text style={ui.text}>Стоимость и доступность реальной доставки не рассчитаны. Это сохранение намерения, не оформление заказа.</Text> : null}
      <Text style={ui.text}>Уценка и остатки не забронированы. На следующий визит наличие и цены нужно проверять заново. Demo-время: 05.09.2026, 12:00 МСК.</Text>
      {basket.error ? <Text style={[ui.text, { color: color.red }]}>{basket.error}</Text> : null}
      <ActionNotice />
      {!plan ? <Choice label={editable ? 'Выбрать задание и сохранить план' : 'Повторить сохранение того же плана'}
        disabled={busy || Boolean(basket.error)} onPress={() => void savePlan()} /> : <>
        <Text style={ui.text}>План: {({ saved: 'сохранён', collected: 'продукты куплены', completed: 'блюдо завершено', cancelled: 'отменён' })[plan.status]}</Text>
        {plan.selected_product_ids.length > 0 ? <Choice
          label={plan.status === 'saved' ? 'Демо: подтвердить чек выбранных товаров' : 'Демо: повторить тот же чек (без новых XP)'}
          disabled={busy} onPress={() => void confirmPurchase()} /> : null}
        {canCompleteCook(plan) ? <Choice label="Начать готовить" disabled={busy}
          onPress={() => { if (startCooking()) router.push('/'); }} /> : null}
        {plan.status === 'completed' ? <Choice label="Посмотреть прогресс" disabled={busy} onPress={() => router.push('/profile')} /> : null}
      </>}
      <View style={ui.choices}><Choice label="Выбрать другое блюдо" disabled={busy}
        onPress={() => { void loadRecipes(); router.replace('/recipes'); }} /></View>
    </ScrollView>
    <BottomNav active="catalog" />
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
  assistantMascot: { width: 44, height: 44 },
  assistantText: { flex: 1, color: color.muted, fontSize: 12, lineHeight: 17 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, paddingHorizontal: 16 },
  card: { width: '31%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16, padding: 8, paddingBottom: 10 },
  cardPhoto: { height: 104, borderRadius: 12, marginBottom: 9 },
  price: { color: color.ink, fontSize: 17, fontWeight: '700', marginBottom: 5 },
  kopecks: { fontSize: 10, lineHeight: 10 },
  priceLarge: { color: color.ink, fontSize: 22, fontWeight: '700', marginBottom: 5 },
  kopecksLarge: { fontSize: 13, lineHeight: 13 },
  cardUnit: { color: color.muted, fontSize: 10.5, marginBottom: 5 },
  cardName: { color: color.ink, fontSize: 11.5, lineHeight: 14.5, height: 29, marginBottom: 6 },
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
