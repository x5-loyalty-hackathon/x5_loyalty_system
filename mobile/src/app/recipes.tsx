import { useEffect } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { DemoProfileSelector } from '../components/DemoProfileSelector';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, flowStyles as ui } from '../components/FlowControls';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { explain, modeText, warningText } from '../domain/copy';
import type { Anchor, RecommendationMode } from '../api/types';

const anchors: Array<[Anchor, string]> = [
  ['home', 'У дома'], ['work', 'У работы'], ['current_location', 'Рядом'], ['custom', 'Моё место'],
];
export default function RecipesScreen() {
  const router = useRouter();
  const { response, health, recipesStatus, recipesError, query, loadRecipes, selectMeal, busy } = useDemo();
  useEffect(() => { if (recipesStatus === 'idle') void loadRecipes(); }, [loadRecipes, recipesStatus]);
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
    <View style={styles.shell}>
      <AppHeader title="Что поесть?" subtitle="Перед заказом или следующим визитом" />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 24 }}>
        <DemoProfileSelector />
        <View style={ui.choices}>
          <Choice label="Для меня" selected={query.mode === null} disabled={busy} onPress={() => void loadRecipes({ mode: null })} />
          {(Object.keys(modeText) as RecommendationMode[]).map((mode) =>
            <Choice key={mode} label={modeText[mode]} selected={query.mode === mode} disabled={busy}
              onPress={() => void loadRecipes({ mode })} />)}
        </View>
        <View style={ui.choices}>{anchors.map(([anchor, label]) =>
          <Choice key={anchor} label={label} selected={query.anchor === anchor} disabled={busy}
            onPress={() => void loadRecipes({ anchor, storeId: null })} />)}</View>
        <Text style={ui.text}>До 750 м от выбранного места. Места, расстояния и покупки синтетические; геолокация не запрашивается.</Text>
        <View style={[styles.domovoiHint, { marginHorizontal: 0 }]}>
          <Image source={require('../../assets/domovoi/mascot-bag.png')} resizeMode="contain" style={styles.hintMascot} />
          <Text style={styles.hintText}>
            {recipesStatus === 'loading' ? 'Подбираю доступные блюда…' :
              recipesStatus === 'error' ? 'Не удалось получить предложения. Локальные рецепты не подставляются.' :
              'Начнём с блюда. Покупать ничего не нужно, если всё уже есть дома.'}
          </Text>
        </View>
        {recipesError ? <Text style={[ui.text, { color: color.red }]}>{recipesError}</Text> : null}
        {recipesStatus === 'error' ? <Choice label="Повторить подключение" onPress={() => void loadRecipes()} /> : null}
        {recipesStatus === 'ready' && response ? <>
          <Text style={ui.text}>API {response.contract_version} · движок {health?.recommendation_engine}
            {health?.model_fallback ? ' · резервный mock' : ''} · demo-данные</Text>
          {query.mode === 'explore' ? <Text style={ui.text}>Вы выбрали новые блюда: среди них может быть полная корзина покупок.</Text> : null}
          {response.warnings.map((warning) => <Text key={warning} style={ui.text}>{warningText(warning)}</Text>)}
          {!response.recommendations.length ? <View style={ui.panel}>
            <Text style={ui.title}>Пока нет подходящих предложений</Text>
            <Text style={ui.text}>{query.mode === 'repeat'
              ? 'Сохраните рецепт в книгу. В этом месте также должны быть доступны нужные товары.'
              : 'Можно изменить режим или место. Мы не будем расширять радиус без вашего выбора.'}</Text>
          </View> : null}
          {response.recommendations.map((meal, index) => {
            const needsChoice = response.challenge_selection.explicit_choice_required.includes(meal.mode);
            return <Pressable key={meal.meal_id} disabled={busy} style={ui.panel}
              onPress={() => {
                if (needsChoice) { void loadRecipes({ mode: meal.mode }); return; }
                selectMeal(meal.meal_id); router.push('/recipe');
              }}>
              <PhotoStub label="фото блюда" style={{ height: 110, borderRadius: 14, marginBottom: 12 }} />
              <Text style={ui.text}>{modeText[meal.mode]}{index === 0 && response.challenge_selection.default_mode === meal.mode ? ' · основной вариант' : ''}</Text>
              <Text style={ui.title}>{meal.title}</Text>
              <Text style={ui.text}>{meal.cook_variant
                ? `Докупить обязательных ингредиентов: ${meal.cook_variant.missing_count}`
                : 'Доступно без готовки'}</Text>
              <Text style={ui.text}>{explain(meal.reason_codes)}</Text>
              <Text style={ui.text}>{explain(response.challenge_selection.mode_reason_codes[meal.mode] ?? [])}</Text>
              {needsChoice ? <Text style={[ui.text, { color: color.red }]}>Собрать новое блюдо с нуля →</Text> : null}
            </Pressable>;
          })}
        </> : null}
      </ScrollView>
      <BottomNav active="recipes" />
    </View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.bg },
  tabs: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: color.white },
  tab: { minHeight: 38, paddingHorizontal: 15, borderRadius: 19, borderWidth: 1, borderColor: color.line, backgroundColor: color.white, alignItems: 'center', justifyContent: 'center' },
  tabActive: { backgroundColor: color.ink, borderColor: color.ink },
  tabText: { color: color.ink, fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: color.white },
  scroll: { paddingTop: 16, paddingBottom: 24 },
  domovoiHint: { marginHorizontal: 16, marginBottom: 12, minHeight: 80, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: 18, backgroundColor: color.white },
  hintMascot: { width: 58, height: 58 },
  hintText: { flex: 1, color: color.body, fontSize: 13, lineHeight: 18 },
  retry: { marginHorizontal: 16, marginBottom: 8, color: color.red, fontSize: 12, fontWeight: '600' },
  sectionTitle: { marginTop: 12, marginBottom: 10, marginHorizontal: 16, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionTitleText: { color: color.ink, fontSize: 18, fontWeight: '700' },
  sectionTitleRight: { color: color.muted, fontSize: 12, fontWeight: '600' },
  horizontalList: { gap: 12, paddingHorizontal: 16, paddingBottom: 4 },
  largeCard: { width: 206, padding: 8, paddingBottom: 14, borderRadius: 18, backgroundColor: color.white },
  largePhoto: { height: 116, borderRadius: 14, marginBottom: 10 },
  coverage: { position: 'absolute', left: 16, top: 16, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 9, backgroundColor: 'rgba(255,255,255,0.94)' },
  coverageText: { color: color.green, fontSize: 10, fontWeight: '700' },
  largeName: { paddingHorizontal: 6, color: color.ink, fontSize: 15, lineHeight: 19, fontWeight: '700' },
  meta: { marginTop: 5, color: color.muted, fontSize: 12 },
  repeatList: { gap: 8, paddingHorizontal: 16 },
  repeatRow: { minHeight: 84, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10, borderRadius: 18, backgroundColor: color.white },
  repeatPhoto: { width: 64, height: 64, borderRadius: 14 },
  repeatCopy: { flex: 1 },
  repeatName: { color: color.ink, fontSize: 15, fontWeight: '700' },
  heart: { width: 32, height: 32, borderRadius: 16, backgroundColor: color.redSoft, alignItems: 'center', justifyContent: 'center' },
  heartText: { color: color.red, fontWeight: '700' },
  freshGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, paddingHorizontal: 16 },
  freshCard: { width: '48.5%', minHeight: 160, padding: 8, paddingBottom: 12, borderRadius: 18, backgroundColor: color.white },
  freshPhoto: { height: 96, borderRadius: 14, marginBottom: 9 },
  freshName: { color: color.ink, fontSize: 14, lineHeight: 18, fontWeight: '700' },
});
