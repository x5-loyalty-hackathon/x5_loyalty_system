import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, ActionNotice, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { explain, money, sourceText, warningText } from '../domain/copy';
import { recipeDetails } from '../fixtures/recipeDetails';
import { matchingSteps } from '../domain/mealFlow';

export default function RecipeScreen() {
  const router = useRouter();
  const { selectedMeal: meal, route, chooseRoute, book, saveToBook, busy, editable } = useDemo();
  if (!meal) return <SafeAreaView style={styles.safe}><AppHeader title="Выберите блюдо" />
    <Choice label="К предложениям" onPress={() => router.replace('/recipes')} /></SafeAreaView>;
  const cook = meal.cook_variant;
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
        <Text style={ui.text}>{explain(meal.reason_codes)}</Text>
        <Text style={ui.text}>{explain(meal.route_reason_codes)}</Text>
        <View style={ui.choices}>{meal.available_routes.map((option) =>
          <Choice key={option} label={option === 'cook' ? 'Приготовить' : 'Нет времени — без готовки'}
            selected={route === option} disabled={!editable} onPress={() => chooseRoute(option)} />)}</View>
        {route === 'cook' && cook ? <>
          <Text style={ui.text}>{cook.preparation_minutes ? `${cook.preparation_minutes} мин · ` : ''}Докупить: {cook.missing_count}</Text>
          <Text style={styles.hint}>Недавний чек не гарантирует наличие продуктов дома. В этой версии поправка «закончилось» ещё не подключена.</Text>
          <Text style={styles.sectionTitle}>Ингредиенты</Text>
          <View style={styles.ingredients}>{cook.ingredients.map((item) =>
            <View style={styles.row} key={item.ingredient_id}><View style={styles.rowCopy}>
              <Text style={styles.rowTitle}>{item.name}{item.required ? '' : ' · необязательно'}</Text>
              <Text style={styles.rowMeta}>{sourceText[item.source]}</Text>
            </View></View>)}</View>
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
          <Text style={ui.title}>Готовое блюдо к этому рецепту</Text>
          {meal.ready_variant?.product_options.map((product) =>
            <Text key={product.sku_id} style={ui.text}>{product.name} · {money(product.price)} · {product.store_id}</Text>)}
          <Text style={ui.text}>Выберите конкретный вариант в плане. Замена на произвольную готовую еду не производится.</Text>
        </View>}
        {[...new Set([...meal.warnings, ...(route === 'cook' ? cook?.warnings ?? [] : meal.ready_variant?.warnings ?? [])])]
          .map((warning) => <Text key={warning} style={ui.text}>{warningText(warning)}</Text>)}
        <ActionNotice />
        <Choice label={route === 'cook' && cook?.missing_count === 0 ? 'Всё есть — к плану готовки' : 'Выбрать товары и способ получения'}
          disabled={busy} onPress={() => router.push('/products')} />
      </View>
    </ScrollView>
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
