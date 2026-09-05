import { useEffect, useRef, useState } from 'react';
import { Animated, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { KitchenScene } from '../components/KitchenScene';
import { KitchenSheet } from '../components/KitchenSheet';
import { Choice, ActionNotice, flowStyles as ui } from '../components/FlowControls';
import { recipeDetails } from '../fixtures/recipeDetails';
import { matchingSteps } from '../domain/mealFlow';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';

const COLLAPSED_HEIGHT = 220;
export default function KitchenScreen() {
  const router = useRouter();
  const { startEntry, busy, cooking, selectedMeal, confirmCooking, pauseCooking, kitchenItems: products } = useDemo();
  const [stageHeight, setStageHeight] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const sheetHeight = useRef(new Animated.Value(COLLAPSED_HEIGHT)).current;
  const expandedHeight = Math.max(COLLAPSED_HEIGHT + 1, stageHeight - 160);
  const steps = selectedMeal ? matchingSteps(selectedMeal, recipeDetails) : [];
  useEffect(() => { if (cooking) setExpanded(true); }, [cooking]);
  useEffect(() => {
    Animated.spring(sheetHeight, {
      toValue: expanded ? expandedHeight : COLLAPSED_HEIGHT,
      useNativeDriver: false, bounciness: 4,
    }).start();
  }, [expanded, expandedHeight, sheetHeight]);
  const enter = (delivery: boolean) => {
    startEntry(delivery ? 'delivery' : 'next_visit'); router.push('/recipes');
  };
  const finish = async () => {
    if (await confirmCooking()) { setExpanded(false); router.push('/profile'); }
    // A network/business error keeps the cooking screen open with its message.
  };
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <View style={styles.stage} onLayout={(event) => setStageHeight(event.nativeEvent.layout.height)}>
      <KitchenScene products={products} height={stageHeight} pose={cooking ? 'cooking' : 'idle'}
        speech={cooking ? '' : 'Что поедим? Подберём блюдо для готовки или без неё.'} />
      <View style={styles.sheetWrap} pointerEvents="box-none">
        <KitchenSheet height={sheetHeight} collapsedHeight={COLLAPSED_HEIGHT} expandedHeight={expandedHeight}
          expanded={expanded} onChange={setExpanded}>
          <ScrollView contentContainerStyle={styles.content}>
            {cooking && selectedMeal ? <>
              <Text style={ui.title}>Готовим: {selectedMeal.title}</Text>
              <Text style={ui.text}>Ингредиенты подтверждены планом. Готовку отмечаем отдельно от покупки.</Text>
              {steps.length ? steps.map((step, index) => <Text key={step} style={ui.text}>{index + 1}. {step}</Text>)
                : <Text style={ui.text}>Для этого состава инструкция ещё не подключена.</Text>}
              <Text style={ui.text}>Demo-инструкция. Окончание готовки не означает, что вся упаковка продукта закончилась.</Text>
              <ActionNotice />
              <Choice label="Я приготовил" disabled={busy} onPress={() => void finish()} />
              <View style={ui.choices}><Choice label="Вернуться к плану" disabled={busy}
                onPress={() => { pauseCooking(); router.push('/products'); }} /></View>
            </> : <>
              <Text style={ui.title}>Что поесть?</Text>
              <Text style={ui.text}>Начните с блюда перед сборкой заказа.</Text>
              <Choice label="Подобрать для доставки" disabled={busy} onPress={() => enter(true)} />
              <View style={ui.choices}>
                <Choice label="Из недавних покупок →" disabled={busy} onPress={() => enter(false)} />
              </View>
              <Text style={ui.title}>Продукты на кухне</Text>
              <Text style={ui.text}>Начальный demo-чек от 04.09.2026 и покупки этой сессии, принятые сервером.
                Это не точный остаток дома. Рисунки условные: ниже названия купленных товаров.</Text>
              {products.map((item) => <View key={item.id} style={styles.item}>
                <Text style={ui.text}>{item.name}</Text>
              </View>)}
              <Text style={ui.text}>Все позиции остаются в списке, даже если им не хватило места на полке.
                Срок годности из чека неизвестен. Это не заказ доставки и не бронь.</Text>
              <Text style={ui.text}>Сценарий работает без push-уведомлений и без нового чека.</Text>
            </>}
          </ScrollView>
        </KitchenSheet>
      </View>
    </View>
    <BottomNav active="kitchen" />
  </View></SafeAreaView>;
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.cream },
  shell: { flex: 1, backgroundColor: color.bg },
  stage: { flex: 1, overflow: 'hidden' },
  sheetWrap: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  content: { paddingHorizontal: 16, paddingBottom: 24 },
  item: { borderBottomWidth: 1, borderBottomColor: color.line, paddingVertical: 6 },
});
