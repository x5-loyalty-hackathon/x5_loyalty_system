import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { plural } from '../utils/plural';
import {
  formatPrice, productsForIngredient, readyMeal, type CatalogProduct,
} from '../data/demo';

export default function ProductsScreen() {
  const router = useRouter();
  const {
    selectedRecipe, selectedIngredient, basket, addToBasket,
    confirmPurchase, purchaseStatus, purchaseError,
  } = useDemo();
  const [note, setNote] = useState<string | null>(null);

  const products = productsForIngredient(selectedIngredient);
  const total = basket.reduce((sum, product) => sum + product.price, 0);
  const totalParts = formatPrice(total);

  const onConfirm = async () => {
    const status = await confirmPurchase();
    // duplicate тоже несёт актуальный прогресс: повторный прогон демо не ломается,
    // просто ничего не начисляется второй раз — это и есть идемпотентность.
    if (status === 'verified' || status === 'duplicate') {
      router.replace('/');
      return;
    }
    if (status) {
      // pending_review / rejected — честно показываем решение антифрода.
      setNote(`Backend вернул статус «${status}»: чек ушёл на проверку, прогресс не начислен.`);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <AppHeader
          title={selectedIngredient.name}
          subtitle={`для рецепта «${selectedRecipe.title}» · ${selectedIngredient.amount}`}
        />
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={styles.sectionTitle}>Можно не готовить</Text>
          <View style={styles.readyCard}>
            <PhotoStub style={styles.readyPhoto} />
            <View style={styles.readyCopy}>
              <View style={styles.readyBadge}>
                <Text style={styles.readyBadgeText}>Готовое блюдо</Text>
              </View>
              <Price value={readyMeal.price} size="large" />
              <Text style={styles.readyUnit}>{readyMeal.unit}</Text>
              <Text style={styles.readyName}>{readyMeal.name}</Text>
            </View>
            <Pressable style={styles.readyAdd} onPress={() => addToBasket(readyMeal)}>
              <Text style={styles.readyAddText}>В корзину</Text>
            </Pressable>
          </View>

          <View style={styles.sectionRow}>
            <Text style={styles.sectionTitle}>{selectedIngredient.name} на замену</Text>
            <Text style={styles.sectionMeta}>
              {products.length} {plural(products.length, 'товар', 'товара', 'товаров')}
            </Text>
          </View>
          <View style={styles.assistant}>
            <Image
              source={require('../../assets/domovoi/mascot-think.png')}
              resizeMode="contain"
              style={styles.assistantMascot}
            />
            <Text style={styles.assistantText}>
              Подобрано под {selectedIngredient.amount} из рецепта
            </Text>
          </View>

          <View style={styles.grid}>
            {products.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                inBasket={basket.some((item) => item.id === product.id)}
                onAdd={() => addToBasket(product)}
              />
            ))}
          </View>

          {note ? <Text style={styles.note}>{note}</Text> : null}
          {purchaseError ? <Text style={styles.error}>{purchaseError}</Text> : null}
        </ScrollView>

        <View style={styles.basketBar}>
          <Text style={styles.basketHint}>
            {basket.length === 0 ? 'Добавьте товары в корзину' : 'Подтвердить покупку ›'}
          </Text>
          <Pressable
            style={[styles.basket, basket.length === 0 && styles.basketOff]}
            disabled={basket.length === 0 || purchaseStatus === 'loading'}
            onPress={onConfirm}
          >
            <View style={styles.basketIcon} />
            <Text style={styles.basketText}>
              {purchaseStatus === 'loading' ? '…' : `${totalParts.rubles},${totalParts.kopecks} ₽`}
            </Text>
          </Pressable>
        </View>
        <BottomNav active="recipes" />
      </View>
    </SafeAreaView>
  );
}

function ProductCard({
  product, inBasket, onAdd,
}: { product: CatalogProduct; inBasket: boolean; onAdd: () => void }) {
  return (
    <View style={styles.card}>
      <PhotoStub style={styles.cardPhoto} />
      <Price value={product.price} />
      <Text style={styles.cardUnit}>{product.unit}</Text>
      <Text style={styles.cardName} numberOfLines={2}>{product.name}</Text>
      <View style={styles.rating}>
        <View style={styles.ratingDot} />
        <Text style={styles.ratingText}>{product.rating.toFixed(2)}</Text>
      </View>
      <Pressable style={[styles.cardAdd, inBasket && styles.cardAddDone]} onPress={onAdd}>
        <Text style={[styles.cardAddText, inBasket && { color: color.white }]}>
          {inBasket ? 'В корзине' : 'В корзину'}
        </Text>
      </Pressable>
    </View>
  );
}

function Price({ value, size = 'small' }: { value: number; size?: 'small' | 'large' }) {
  const { rubles, kopecks } = formatPrice(value);
  const large = size === 'large';
  return (
    <Text style={large ? styles.priceLarge : styles.price}>
      {rubles}
      <Text style={large ? styles.kopecksLarge : styles.kopecks}>{kopecks}</Text> ₽
    </Text>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.bg },
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
