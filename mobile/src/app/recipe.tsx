import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, ActionNotice, PrimaryAction, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { explain, money, sourceText, warningText } from '../domain/copy';
import { recipeDetails } from '../fixtures/recipeDetails';
import { matchingSteps } from '../domain/mealFlow';

/** Цвет статуса ингредиента: что уже есть — зелёным, что покупать — акцентом. */
function sourceTone(source: keyof typeof sourceText): string {
  if (source === 'receipt' || source === 'home') return color.green;
  if (source === 'unavailable') return color.muted;
  return color.orange;
}

export default function RecipeScreen() {
  const router = useRouter();
  const { selectedMeal: meal, route, takeReadyMeal, readyProduct, book, saveToBook, busy, editable, savePlanAndCook } = useDemo();
  if (!meal) return <SafeAreaView style={styles.safe}><AppHeader title="Выберите блюдо" />
    <Choice label="К предложениям" onPress={() => router.replace('/recipes')} /></SafeAreaView>;
  const cook = meal.cook_variant;
  // Докупать нечего: задание создаётся здесь же, и человек сразу уходит на
  // кухню к шагам. Раньше между «хочу это блюдо» и готовкой стоял лишний
  // экран плана. Само задание не пропускается — оно нужно для привязки чека
  // и награды.
  const readyToCook = route === 'cook' && cook?.missing_count === 0;
  const cookNow = async () => {
    if (await savePlanAndCook()) router.replace('/');
  };
  const saved = cook ? book.includes(cook.recipe_id) : false;
  const steps = matchingSteps(meal, recipeDetails);
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <AppHeader title="Ваше блюдо" />
    <ScrollView contentContainerStyle={{ paddingBottom: 24 }}>
      <View style={styles.hero}>
        <PhotoStub label="фото готового блюда" style={styles.heroPhoto} />
        {cook ? <Pressable disabled={busy || saved} accessibilityRole="button"
          accessibilityLabel={saved ? 'Рецепт сохранён' : 'Сохранить рецепт'} onPress={() => void saveToBook()} style={styles.heroHeart}>
          <Text style={styles.heroHeartText}>{saved ? '♥' : '♡'}</Text>
        </Pressable> : null}
        <Image source={require('../../assets/domovoi/mascot-cook.png')} resizeMode="contain" style={styles.heroMascot} />
      </View>
      <View style={styles.body}>
        <Text style={styles.title}>{meal.title}</Text>
        <View style={styles.chips}>
          {cook?.preparation_minutes ? <View style={styles.chip}>
            <Text style={styles.chipText}>{cook.preparation_minutes} мин</Text></View> : null}
          {route === 'cook' && cook ? <View style={[styles.chip, cook.missing_count ? styles.chipWarn : styles.chipOk]}>
            <Text style={[styles.chipText, { color: cook.missing_count ? color.orange : color.green }]}>
              {cook.missing_count ? `докупить ${cook.missing_count}` : 'всё есть'}</Text></View> : null}
          {route === 'ready' ? <View style={[styles.chip, styles.chipOk]}>
            <Text style={[styles.chipText, { color: color.green }]}>без готовки</Text></View> : null}
        </View>
        <Text style={styles.lead}>{[explain(meal.reason_codes), explain(meal.route_reason_codes)]
          .filter(Boolean).join(' ')}</Text>
        {route === 'cook' && cook ? <>
          <Text style={styles.hint}>Проверьте, что эти продукты действительно есть дома.</Text>
          <Text style={styles.sectionTitle}>Ингредиенты</Text>
          <View style={styles.ingredients}>{cook.ingredients.map((item) =>
            <View style={[styles.row, item.source === 'unavailable' && styles.rowNeeded]} key={item.ingredient_id}>
              <View style={[styles.rowDot, { backgroundColor: sourceTone(item.source) }]} />
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle}>{item.name}{item.required ? '' : ' · необязательно'}</Text>
                <Text style={[styles.rowMeta, { color: sourceTone(item.source) }]}>{sourceText[item.source]}</Text>
              </View>
            </View>)}</View>
          <Choice label={saved ? '♥ В книге рецептов' : '♡ Сохранить рецепт'} disabled={busy || saved} onPress={() => void saveToBook()} />
          <Text style={styles.hint}>Книга сохраняется на demo-сервере. Сохранение не даёт XP.</Text>
          <Text style={styles.sectionTitle}>Как приготовить</Text>
          {steps.length ? <>
            <Text style={styles.hint}>Инструкция из demo-каталога, не результат ML. Точные порции и граммовки ещё не согласованы.</Text>
            <View style={styles.steps}>{steps.map((step, index) => <View style={styles.step} key={step}>
              <View style={styles.stepNum}><Text style={styles.stepNumText}>{index + 1}</Text></View>
              <Text style={styles.stepTitle}>{step}</Text>
            </View>)}</View>
          </> : <Text style={styles.hint}>Для этого состава проверенная инструкция пока не подключена.</Text>}
        </> : <View style={ui.panel}>
          <Text style={ui.title}>Без готовки</Text>
          <Text style={ui.text}>Готовое блюдо и его цену выберете в плане — там же, где обычные товары.</Text>
        </View>}
        {[...new Set([...meal.warnings, ...(route === 'cook' ? cook?.warnings ?? [] : meal.ready_variant?.warnings ?? [])])]
          .map((warning) => <Text key={warning} style={ui.text}>{warningText(warning)}</Text>)}
        <ActionNotice />
      </View>
    </ScrollView>
    <View style={styles.ctaBar}>
      <View style={styles.ctaMain}>
        <PrimaryAction label={readyToCook ? 'Всё есть — начать готовить' : 'Выбрать товары'}
          tone={readyToCook ? 'done' : 'go'} disabled={busy}
          onPress={() => void (readyToCook ? cookNow() : router.push('/products'))} />
      </View>
      {meal.available_routes.includes('ready') ? <View style={styles.ctaAlt}>
        <PrimaryAction label="Купить готовое" tone="alt" disabled={!editable || !readyProduct}
          onPress={() => { if (takeReadyMeal()) router.push('/products'); }} />
      </View> : null}
    </View>
    <BottomNav active="recipes" />
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.white },
  scroll: { paddingBottom: 170 },

  hero: { height: 250 },
  heroPhoto: { height: 250 },
  heroBack: {
    position: 'absolute', left: 16, top: 52, width: 40, height: 40, borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.94)', alignItems: 'center', justifyContent: 'center',
  },
  heroBackText: { color: color.ink, fontSize: 24, fontWeight: '700', marginTop: -2 },
  heroHeart: {
    position: 'absolute', right: 16, top: 52, width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.94)', alignItems: 'center', justifyContent: 'center',
  },
  heroHeartText: { color: color.red, fontSize: 16, fontWeight: '700' },
  heroMascot: { position: 'absolute', right: 8, bottom: -6, width: 120, height: 132 },

  body: { paddingHorizontal: 16, paddingTop: 18 },
  title: { color: color.ink, fontSize: 25, fontWeight: '700', marginBottom: 10 },
  chips: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  chip: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 12, backgroundColor: color.bg },
  chipText: { color: color.body, fontSize: 12, fontWeight: '600' },
  description: { color: color.body, fontSize: 14, lineHeight: 21, marginBottom: 22 },

  sectionRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionTitle: { color: color.ink, fontSize: 18, fontWeight: '700', marginBottom: 12 },
  sectionMeta: { color: color.muted, fontSize: 12, fontWeight: '600' },
  hint: { color: color.muted, fontSize: 12, lineHeight: 17.4, marginBottom: 12 },

  chipOk: { backgroundColor: color.greenSoft },
  chipWarn: { backgroundColor: '#FFF1E6' },
  lead: { color: color.body, fontSize: 14, lineHeight: 20, marginBottom: 16 },
  rowDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
  ctaBar: {
    flexDirection: 'row', gap: 10, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12,
    backgroundColor: color.white, borderTopWidth: 1, borderTopColor: color.line,
  },
  /** Основное действие шире альтернативы: они равнозначны, но не равны. */
  ctaMain: { flex: 3 },
  ctaAlt: { flex: 2 },
  ingredients: { gap: 8, marginBottom: 24 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12, paddingVertical: 11,
    borderRadius: 16, borderWidth: 1, borderColor: color.line, backgroundColor: color.white,
  },
  rowNeeded: { backgroundColor: '#FFF6F7' },
  rowMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48 },
  rowGlyph: {
    width: 46, height: 46, borderRadius: 13, backgroundColor: color.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  rowGlyphText: { color: color.body, fontSize: 18 },
  rowCopy: { flex: 1 },
  rowTitle: { color: color.ink, fontSize: 14.5, fontWeight: '700', marginBottom: 4 },
  rowMeta: { color: color.muted, fontSize: 12 },
  mark: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  markText: { fontSize: 13, fontWeight: '700' },

  steps: { marginBottom: 20 },
  step: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 4,
    borderBottomWidth: 1, borderBottomColor: color.bg,
  },
  stepNum: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: color.bg,
    alignItems: 'center', justifyContent: 'center',
  },
  stepNumText: { color: color.ink, fontSize: 12.5, fontWeight: '700' },
  stepTitle: { flex: 1, color: color.ink, fontSize: 14, fontWeight: '500' },
  stepTime: { color: color.red, fontSize: 12.5, fontWeight: '700' },

  ctaWrap: {
    position: 'absolute', left: 0, right: 0, bottom: 74, paddingHorizontal: 16,
    paddingTop: 12, paddingBottom: 12, backgroundColor: color.white,
    borderTopWidth: 1, borderTopColor: color.line,
  },
  cta: {
    height: 56, borderRadius: 16, backgroundColor: color.red, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20,
  },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.75 },
});
