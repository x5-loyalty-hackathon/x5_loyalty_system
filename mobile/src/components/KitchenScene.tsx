import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { placeProducts } from '../data/kitchenPlacement';
import { slotRect } from '../data/kitchenSlots';
import type { KitchenProduct } from '../domain/kitchen';
import { color } from '../theme/tokens';

/** Высота полосы по умолчанию — как в макете экрана «после чека». */
const BAND_HEIGHT = 286;
/**
 * Арт комнаты: сетка 117×156 по 4 точки на клетку, сдвиг влево как в макете.
 * Показываем столько, сколько влезает: лишнее обрезается по высоте полосы.
 */
const ART = { left: -39, top: 0, width: 468, height: 624 };

/**
 * Позы Домового.
 *
 * Масштаб считается по самому персонажу, а не по холсту: у спрайтов разные
 * прозрачные поля (у позы готовки снизу их вдвое больше), поэтому одинаковая
 * ширина картинки давала бы разный рост и разную линию пола.
 *
 * Рост задан пропорцией к самой кухне: столешница поднята на 200 точек над
 * полом и должна приходиться Домовому примерно на бедро — это его кухня, он
 * за ней работает. Отсюда рост 333 точки.
 *
 * `top` рассчитан так, чтобы ступни стояли на нарисованном полу (строка 117
 * сетки). У поз разные прозрачные поля снизу, поэтому значение своё для
 * каждой. Домовой стоит в комнате и не привязан к шторке: она проходит
 * поверх него.
 */
const MASCOT = {
  idle: {
    source: require('../../assets/domovoi/mascot-spoon.png'),
    width: 411,
    height: 456,
    top: 80,
  },
  cooking: {
    source: require('../../assets/domovoi/mascot-cook.png'),
    width: 458,
    height: 458,
    top: 98,
  },
} as const;


export function KitchenScene({
  products,
  speech,
  pose = 'idle',
  height = BAND_HEIGHT,
  onMenuPress,
}: {
  products: readonly KitchenProduct[];
  /** Реплика Домового. Пустая строка — облачко не показывается. */
  speech: string;
  /** Поза Домового: обычная или у плиты, когда готовим. */
  pose?: keyof typeof MASCOT;
  /** Сколько комнаты показать по высоте. */
  height?: number;
  onMenuPress?: () => void;
}) {
  const { placed } = placeProducts(products);

  return (
    <View style={[styles.band, { height }]}>
      <Image source={require('../../assets/kitchen/kitchen-full.png')} style={styles.art} />

      {placed.map(({ sprite, slot }) => (
        <Image
          key={slot.id}
          source={sprite.source}
          style={[styles.sprite, slotRect(slot)]}
          resizeMode="stretch"
        />
      ))}

      <LinearGradient colors={['rgba(244,231,205,0)', color.cream]} style={styles.fade} />

      {speech ? (
        <View style={styles.speech}>
          <Text style={styles.speechText}>{speech}</Text>
        </View>
      ) : null}
      {onMenuPress ? <Pressable accessibilityLabel="Меню" style={styles.menu} onPress={onMenuPress}>
        <Text style={styles.menuText}>≡</Text>
      </Pressable> : null}
      <Image
        source={MASCOT[pose].source}
        resizeMode="contain"
        style={[
          styles.mascot,
          {
            width: MASCOT[pose].width,
            height: MASCOT[pose].height,
            top: MASCOT[pose].top,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  band: { backgroundColor: color.cream, overflow: 'hidden' },
  art: { position: 'absolute', ...ART },
  // Домовой стоит на нарисованном полу; шторка проходит поверх него.

  /** Спрайт занимает слот клетка в клетку: габариты арта равны размеру слота. */
  sprite: { position: 'absolute' },

  fade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 46 },
  speech: {
    position: 'absolute', left: 20, top: 14, maxWidth: 200, paddingVertical: 10,
    paddingHorizontal: 13, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 16,
    borderBottomLeftRadius: 4,
  },
  speechText: { color: color.brown, fontSize: 13, lineHeight: 17.5, fontWeight: '600' },
  menu: {
    position: 'absolute', right: 18, top: 14, width: 36, height: 36, borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.94)', alignItems: 'center', justifyContent: 'center',
  },
  menuText: { color: color.brown, fontSize: 16, fontWeight: '700' },
  /** Размеры задаются позой: см. MASCOT. */
  mascot: { position: 'absolute', alignSelf: 'center' },
});
