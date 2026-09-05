import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import type { DemoIngredient } from '../data/demo';

/** «Добавить 2 продукта в корзину» — согласование числительного. */
function missingLabel(count: number): string {
  if (count === 0) return 'Всё есть — начать готовить';
  const noun = count === 1 ? 'продукт' : count < 5 ? 'продукта' : 'продуктов';
  return `Добавить ${count} ${noun} в корзину`;
}

export default function RecipeScreen() {
  const router = useRouter();
  const {
    selectedRecipe, isIngredientAvailable, toggleIngredient, selectIngredient, startCooking,
  } = useDemo();

  const missing = selectedRecipe.ingredients.filter((item) => !isIngredientAvailable(item));
  const have = selectedRecipe.ingredients.length - missing.length;

  const beginCooking = () => {
    startCooking(selectedRecipe.id);
    router.replace('/');
  };

  const openProducts = (ingredient?: DemoIngredient) => {
    const target = ingredient ?? missing[0] ?? selectedRecipe.ingredients[0];
    if (target) selectIngredient(target.id);
    router.push('/products');
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.shell}>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.hero}>
            <PhotoStub label="фото готового блюда" style={styles.heroPhoto} />
            <Pressable onPress={() => router.back()} accessibilityLabel="Назад" style={styles.heroBack}>
              <Text style={styles.heroBackText}>‹</Text>
            </Pressable>
            <View style={styles.heroHeart}>
              <Text style={styles.heroHeartText}>♥</Text>
            </View>
            <Image
              source={require('../../assets/domovoi/mascot-cook.png')}
              resizeMode="contain"
              style={styles.heroMascot}
            />
          </View>

          <View style={styles.body}>
            <Text style={styles.title}>{selectedRecipe.title}</Text>
            <View style={styles.chips}>
              <Chip text={`${selectedRecipe.time} мин`} />
              <Chip text={`${selectedRecipe.servings} порции`} />
              <Chip
                text={`хватает ${have} из ${selectedRecipe.ingredients.length}`}
                tone={color.green}
                background={color.greenSoft}
              />
            </View>
            <Text style={styles.description}>{selectedRecipe.description}</Text>

            <View style={styles.sectionRow}>
              <Text style={styles.sectionTitle}>Ингредиенты</Text>
              <Text style={styles.sectionMeta}>{selectedRecipe.ingredients.length} позиций</Text>
            </View>
            <Text style={styles.hint}>
              Тапни по карточке, чтобы выбрать товар. Значок справа переключает статус:
              ✕ — «нет», ✓ — «есть дома или куплено».
            </Text>

            <View style={styles.ingredients}>
              {selectedRecipe.ingredients.map((ingredient) => {
                const available = isIngredientAvailable(ingredient);
                return (
                  <View
                    key={ingredient.id}
                    style={[styles.row, !available && styles.rowNeeded]}
                  >
                    <Pressable style={styles.rowMain} onPress={() => openProducts(ingredient)}>
                      <View style={styles.rowGlyph}>
                        <Text style={styles.rowGlyphText}>{ingredient.emoji}</Text>
                      </View>
                      <View style={styles.rowCopy}>
                        <Text style={styles.rowTitle}>{ingredient.name}</Text>
                        <Text style={styles.rowMeta}>
                          {ingredient.amount} ·{' '}
                          <Text style={{ color: available ? color.green : color.red, fontWeight: '600' }}>
                            {available ? 'есть на кухне' : 'нужно купить'}
                          </Text>
                        </Text>
                      </View>
                    </Pressable>
                    <Pressable
                      accessibilityLabel="Переключить статус"
                      onPress={() => toggleIngredient(ingredient)}
                      style={[
                        styles.mark,
                        available
                          ? { backgroundColor: color.white, borderColor: color.line }
                          : { backgroundColor: color.green, borderColor: color.green },
                      ]}
                    >
                      <Text style={[styles.markText, { color: available ? color.muted : color.white }]}>
                        {available ? '✕' : '✓'}
                      </Text>
                    </Pressable>
                  </View>
                );
              })}
            </View>

            <Text style={styles.sectionTitle}>Этапы</Text>
            <View style={styles.steps}>
              {selectedRecipe.steps.map((step, index) => (
                <View key={step.title} style={styles.step}>
                  <View style={styles.stepNum}>
                    <Text style={styles.stepNumText}>{index + 1}</Text>
                  </View>
                  <Text style={styles.stepTitle}>{step.title}</Text>
                  <Text style={styles.stepTime}>{step.minutes} мин</Text>
                </View>
              ))}
            </View>
          </View>
        </ScrollView>

        <View style={styles.ctaWrap}>
          {missing.length > 0 ? (
            <>
              <Pressable style={styles.cta} onPress={() => openProducts()}>
                <Text style={styles.ctaText}>{missingLabel(missing.length)}</Text>
                <Text style={styles.ctaArrow}>›</Text>
              </Pressable>
              <Pressable style={styles.ctaGhost} onPress={beginCooking}>
                <Text style={styles.ctaGhostText}>Начать готовить без них</Text>
              </Pressable>
            </>
          ) : (
            <Pressable style={[styles.cta, styles.ctaCook]} onPress={beginCooking}>
              <Text style={styles.ctaText}>Начать готовить</Text>
              <Text style={styles.ctaArrow}>›</Text>
            </Pressable>
          )}
        </View>
        <BottomNav active="recipes" />
      </View>
    </SafeAreaView>
  );
}

function Chip({ text, tone, background }: { text: string; tone?: string; background?: string }) {
  return (
    <View style={[styles.chip, background ? { backgroundColor: background } : null]}>
      <Text style={[styles.chipText, tone ? { color: tone } : null]}>{text}</Text>
    </View>
  );
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
  ctaCook: { backgroundColor: color.green },
  ctaGhost: { marginTop: 8, height: 44, alignItems: 'center', justifyContent: 'center' },
  ctaGhostText: { color: color.body, fontSize: 14, fontWeight: '600' },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.75 },
});
