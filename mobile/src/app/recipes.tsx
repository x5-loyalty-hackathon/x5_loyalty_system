import { useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { plural } from '../utils/plural';
import type { DemoRecipe, DemoRecipeMode } from '../data/demo';

const tabs: Array<{ mode: DemoRecipeMode; label: string }> = [
  { mode: 'current', label: 'Из корзины' },
  { mode: 'repeat', label: 'Повторить' },
  { mode: 'explore', label: 'Новые' },
];

export default function RecipesScreen() {
  const router = useRouter();
  const { recipes, recipesStatus, recipesError, loadRecipes, selectRecipe } = useDemo();
  const [tab, setTab] = useState<DemoRecipeMode>('current');

  useEffect(() => { if (recipesStatus === 'idle') void loadRecipes(); }, [loadRecipes, recipesStatus]);

  const openRecipe = (recipe: DemoRecipe) => {
    selectRecipe(recipe.id);
    router.push('/recipe');
  };
  const current = recipes.filter((recipe) => recipe.mode === 'current').slice(0, 3);
  const repeat = recipes.filter((recipe) => recipe.mode === 'repeat').slice(0, 3);
  const fresh = recipes.filter((recipe) => recipe.mode === 'explore').slice(0, 4);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <AppHeader title="Что приготовить" />
        <View style={styles.tabs}>
          {tabs.map((item) => (
            <Pressable key={item.mode} onPress={() => setTab(item.mode)} style={[styles.tab, tab === item.mode && styles.tabActive]}>
              <Text style={[styles.tabText, tab === item.mode && styles.tabTextActive]}>{item.label}</Text>
            </Pressable>
          ))}
        </View>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.domovoiHint}>
            <Image source={require('../../assets/domovoi/mascot-bag.png')} resizeMode="contain" style={styles.hintMascot} />
            <Text style={styles.hintText}>
              {recipesStatus === 'mock' ? 'Показываю демо-рецепты: backend сейчас недоступен.' : 'Собрал рецепты под то, что уже лежит на кухне. Чего не хватает — докупим одним тапом.'}
            </Text>
          </View>
          {recipesError ? <Pressable onPress={() => void loadRecipes()}><Text style={styles.retry}>Повторить подключение</Text></Pressable> : null}

          <SectionTitle title="Из корзины" right={`${current.length} ${plural(current.length, 'рецепт', 'рецепта', 'рецептов')} ›`} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontalList}>
            {current.map((recipe) => <LargeRecipeCard key={recipe.id} recipe={recipe} onPress={() => openRecipe(recipe)} />)}
          </ScrollView>

          <SectionTitle title="Повторить" right="любимые ›" />
          <View style={styles.repeatList}>
            {repeat.map((recipe) => <RepeatRecipeRow key={recipe.id} recipe={recipe} onPress={() => openRecipe(recipe)} />)}
          </View>

          <SectionTitle title="Новые рецепты" right="все ›" />
          <View style={styles.freshGrid}>
            {fresh.map((recipe) => <FreshRecipeCard key={recipe.id} recipe={recipe} onPress={() => openRecipe(recipe)} />)}
          </View>
        </ScrollView>
        <BottomNav active="recipes" />
      </View>
    </SafeAreaView>
  );
}

function SectionTitle({ title, right }: { title: string; right: string }) {
  return <View style={styles.sectionTitle}><Text style={styles.sectionTitleText}>{title}</Text><Text style={styles.sectionTitleRight}>{right}</Text></View>;
}

function LargeRecipeCard({ recipe, onPress }: { recipe: DemoRecipe; onPress: () => void }) {
  const have = recipe.ingredients.filter((item) => item.defaultAvailable).length;
  return (
    <Pressable style={styles.largeCard} onPress={onPress}>
      <PhotoStub label="фото блюда" style={styles.largePhoto} />
      <View style={styles.coverage}><Text style={styles.coverageText}>хватает {have} из {recipe.ingredients.length}</Text></View>
      <Text style={styles.largeName}>{recipe.title}</Text><Text style={styles.meta}>{recipe.time} мин</Text>
    </Pressable>
  );
}

function RepeatRecipeRow({ recipe, onPress }: { recipe: DemoRecipe; onPress: () => void }) {
  return (
    <Pressable style={styles.repeatRow} onPress={onPress}>
      <PhotoStub style={styles.repeatPhoto} />
      <View style={styles.repeatCopy}><Text style={styles.repeatName}>{recipe.title}</Text><Text style={styles.meta}>{recipe.time} мин · {recipe.lastCooked ?? 'любимый рецепт'}</Text></View>
      <View style={styles.heart}><Text style={styles.heartText}>♥</Text></View>
    </Pressable>
  );
}

function FreshRecipeCard({ recipe, onPress }: { recipe: DemoRecipe; onPress: () => void }) {
  return (
    <Pressable style={styles.freshCard} onPress={onPress}>
      <PhotoStub style={styles.freshPhoto} /><Text style={styles.freshName}>{recipe.title}</Text><Text style={styles.meta}>{recipe.time} мин · {recipe.note ?? 'новое'}</Text>
    </Pressable>
  );
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
