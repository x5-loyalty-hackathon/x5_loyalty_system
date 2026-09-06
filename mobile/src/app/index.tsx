import { useEffect, useRef, useState } from 'react';
import { Animated, ScrollView, StyleSheet, Text, View } from 'react-native';
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
      <KitchenScene products={products} height={stageHeight} equipped={equipped} pose={cooking ? 'cooking' : 'idle'}
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
              <View style={ui.choices}><Choice label="Вернуться к плану" disabled={busy}
                onPress={() => { pauseCooking(); router.push('/products'); }} /></View>
              <View style={styles.cta}>
                <PrimaryAction label="Я приготовил" tone="done" disabled={busy} onPress={() => void finish()} />
              </View>
            </> : <>
              <Text style={ui.title}>Что поесть?</Text>
              <Text style={ui.text}>Начните с блюда перед сборкой заказа.</Text>
              <View style={styles.cta}>
                <PrimaryAction label="Подобрать блюдо" disabled={busy} onPress={() => enter(true)} />
              </View>
              <View style={ui.choices}>
                <Choice label="Из недавних покупок →" disabled={busy} onPress={() => enter(false)} />
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
