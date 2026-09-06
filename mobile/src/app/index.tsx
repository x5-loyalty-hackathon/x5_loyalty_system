import { useEffect, useRef, useState } from 'react';
import { Animated, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { KitchenScene } from '../components/KitchenScene';
import { KitchenSheet } from '../components/KitchenSheet';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, ActionNotice, PrimaryAction, flowStyles as ui } from '../components/FlowControls';
import { recipeDetails } from '../fixtures/recipeDetails';
import { matchingSteps } from '../domain/mealFlow';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';

const COLLAPSED_HEIGHT = 220;
export default function KitchenScreen() {
  const router = useRouter();
  const { startEntry, busy, cooking, selectedMeal, confirmCooking, pauseCooking, kitchenItems: products, equipped, plan } = useDemo();
  const [stageHeight, setStageHeight] = useState(0);
  const { height: windowHeight } = useWindowDimensions();
  // onLayout на вебе иногда отдаёт нулевую высоту при первом монтировании и
  // больше не срабатывает: размер контейнера с тех пор не меняется. Тогда
  // панель раскрывалась на один пиксель. Считаем запасное значение от окна.
  const sceneHeight = stageHeight || Math.max(320, windowHeight - 150);
  const [expanded, setExpanded] = useState(false);
  const sheetHeight = useRef(new Animated.Value(COLLAPSED_HEIGHT)).current;
  const expandedHeight = Math.max(COLLAPSED_HEIGHT + 1, sceneHeight - 160);
  const steps = selectedMeal ? matchingSteps(selectedMeal, recipeDetails) : [];
  useEffect(() => { if (cooking) setExpanded(true); }, [cooking]);
  useEffect(() => {
    Animated.spring(sheetHeight, {
      toValue: expanded ? expandedHeight : COLLAPSED_HEIGHT,
      useNativeDriver: false, bounciness: 4,
    }).start();
  }, [expanded, expandedHeight, sheetHeight]);
  const enter = () => { startEntry('delivery'); router.push('/recipes'); };
  const finish = async () => {
    if (await confirmCooking()) { setExpanded(false); router.push('/profile'); }
    // A network/business error keeps the cooking screen open with its message.
  };
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <View style={styles.stage} onLayout={(event) => { const next = event.nativeEvent.layout.height; if (next > 0) setStageHeight(next); }}>
      <KitchenScene products={products} height={sceneHeight} equipped={equipped} pose={cooking ? 'cooking' : 'idle'}
        speech={cooking ? '' : 'Что поедим? Подберём блюдо для готовки или без неё.'} />
      <View style={styles.sheetWrap} pointerEvents="box-none">
        <KitchenSheet height={sheetHeight} collapsedHeight={COLLAPSED_HEIGHT} expandedHeight={expandedHeight}
          expanded={expanded} onChange={setExpanded}>
          <ScrollView contentContainerStyle={styles.content}>
            {cooking && selectedMeal ? <>
              <Text style={ui.title}>Готовим: {selectedMeal.title}</Text>
              <Text style={ui.text}>Ингредиенты подтверждены планом. Готовку отмечаем отдельно от покупки.</Text>
              {steps.length ? <View style={styles.steps}>
                {steps.map((step, index) => <View key={step}
                  style={[styles.step, index === steps.length - 1 && styles.stepLast]}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>{index + 1}</Text></View>
                  <Text style={styles.stepTitle}>{step}</Text>
                </View>)}
              </View> : <Text style={ui.text}>Для этого состава инструкция ещё не подключена.</Text>}
              <ActionNotice />
              <View style={ui.choices}><Choice label="Вернуться к плану" disabled={busy}
                onPress={() => { pauseCooking(); router.push('/products'); }} /></View>
              <View style={styles.cta}>
                <PrimaryAction label="Я приготовил" tone="done" disabled={busy} onPress={() => void finish()} />
              </View>
            </> : <>
              <Text style={ui.title}>Что поесть?</Text>
              <Text style={ui.text}>Начните с блюда перед сборкой заказа.</Text>
              <View style={styles.cta}>
                <PrimaryAction label="Подобрать блюдо" disabled={busy} onPress={() => enter()} />
              </View>
              {plan ? (
                <View style={ui.choices}>
                  <Choice label="Мой план →" disabled={busy} onPress={() => router.push('/products')} />
                </View>
              ) : null}
              <View style={styles.pantryHead}>
                <Text style={ui.title}>Продукты на кухне</Text>
                <Text style={styles.pantryCount}>по чекам · {products.length}</Text>
              </View>
              <View style={styles.pantryGrid}>
                {products.map((item) => <View key={item.id} style={styles.pantryCard}>
                  <PhotoStub label="фото" style={styles.pantryPhoto} />
                  <Text style={styles.pantryName} numberOfLines={2}>{item.name}</Text>
                </View>)}
              </View>
              <Text style={styles.pantryNote}>Из чеков, не точный остаток дома.</Text>
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
  cta: { marginTop: 4, marginBottom: 10 },
  steps: { backgroundColor: color.white, borderRadius: 18, paddingHorizontal: 12, marginTop: 6, marginBottom: 12 },
  step: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 4,
    borderBottomWidth: 1, borderBottomColor: color.bg,
  },
  stepLast: { borderBottomWidth: 0 },
  stepNum: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: color.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  stepNumText: { color: color.ink, fontSize: 12.5, fontWeight: '700' },
  stepTitle: { flex: 1, color: color.ink, fontSize: 14, fontWeight: '500', lineHeight: 19 },
  pantryHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  pantryCount: { color: color.muted, fontSize: 12.5, fontWeight: '600' },
  pantryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 },
  pantryCard: {
    width: '31%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16,
    padding: 8, paddingBottom: 10,
  },
  pantryPhoto: { height: 74, borderRadius: 12, marginBottom: 8 },
  pantryName: { color: color.ink, fontSize: 12, lineHeight: 15, fontWeight: '600' },
  pantryNote: { color: color.muted, fontSize: 12, marginTop: 12 },
});
