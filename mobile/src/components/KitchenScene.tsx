import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { placeProducts } from '../data/kitchenPlacement';
import { slotRect } from '../data/kitchenSlots';
import type { KitchenProduct } from '../data/demo';
import { color } from '../theme/tokens';

const BAND_HEIGHT = 286;
/** Арт: 117×62 клетки по 4 точки, со сдвигом влево как в макете. */
const ART = { left: -39, top: 0, width: 468, height: 248 };

export function KitchenScene({
  products,
  speech,
  onMenuPress,
}: {
  products: readonly KitchenProduct[];
  speech: string;
  onMenuPress?: () => void;
}) {
  const { placed } = placeProducts(products);

  return (
    <View style={styles.band}>
      <Image source={require('../../assets/kitchen/kitchen-band.png')} style={styles.art} />

      {placed.map(({ sprite, slot }) => (
        <Image
          key={slot.id}
          source={sprite.source}
          style={[styles.sprite, slotRect(slot)]}
          resizeMode="stretch"
        />
      ))}

      <LinearGradient colors={['rgba(244,231,205,0)', color.cream]} style={styles.fade} />

      <View style={styles.speech}>
        <Text style={styles.speechText}>{speech}</Text>
      </View>
      <Pressable accessibilityLabel="Меню" style={styles.menu} onPress={onMenuPress}>
        <Text style={styles.menuText}>≡</Text>
      </Pressable>
      <Image
        source={require('../../assets/domovoi/mascot-spoon.png')}
        resizeMode="contain"
        style={styles.mascot}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  band: { height: BAND_HEIGHT, backgroundColor: color.cream, overflow: 'hidden' },
  art: { position: 'absolute', ...ART },

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
  mascot: { position: 'absolute', alignSelf: 'center', bottom: -24, width: 172, height: 190 },
});
