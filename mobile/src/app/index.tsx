import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { PhotoStub } from '../components/PhotoStub';
import { Choice, flowStyles as ui } from '../components/FlowControls';
import { recentReceipt } from '../fixtures/recommendationRequest';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';

export default function KitchenScreen() {
  const router = useRouter();
  const { startEntry, busy } = useDemo();
  const enter = (delivery: boolean) => {
    startEntry(delivery ? 'delivery' : 'next_visit');
    router.push('/recipes');
  };
  return <SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.shell}>
    <ScrollView contentContainerStyle={{ paddingBottom: 24 }}>
      <View style={styles.hero}>
        <Image source={require('../../assets/kitchen/kitchen-band.png')} style={styles.kitchenArt} />
        <LinearGradient colors={['rgba(244,231,205,0)', color.cream]} style={styles.heroFade} />
        <View style={styles.speech}><Text style={styles.speechText}>Что поедим? Подберём блюдо для готовки или без неё.</Text></View>
        <Image source={require('../../assets/domovoi/mascot-spoon.png')} resizeMode="contain" style={styles.mascot} />
      </View>
      <View style={styles.sheet}>
        <View style={ui.panel}>
          <Text style={ui.title}>Планируете доставку?</Text>
          <Text style={ui.text}>Сначала выберите, что поесть, затем — недостающие продукты. Это demo-точка входа рядом с доставкой, не checkout.</Text>
          <Choice label="Что поесть? → для доставки" disabled={busy} onPress={() => enter(true)} />
        </View>
        <Text style={styles.title}>Недавние покупки</Text>
        <Text style={ui.text}>Синтетический чек от 04.09.2026. Это не точный остаток на кухне; срок годности из чека неизвестен.</Text>
        <View style={styles.grid}>{recentReceipt.items.map((item) => <View key={item.sku_id} style={styles.card}>
          <PhotoStub style={styles.cardPhoto} /><Text style={styles.cardName}>{item.name}</Text>
          <Text style={styles.cardQty}>В недавнем чеке</Text>
        </View>)}</View>
        <View style={ui.choices}>
          <Choice label="Что приготовить из покупок?" disabled={busy} onPress={() => enter(false)} />
        </View>
        <Text style={ui.text}>Работает без push-уведомлений и без нового чека. Все данные и события покупки в этой сборке — демонстрационные.</Text>
      </View>
    </ScrollView>
    <BottomNav active="kitchen" />
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.cream },
  shell: { flex: 1, backgroundColor: color.bg },
  scroll: { paddingBottom: 168 },

  hero: { height: 286, backgroundColor: color.cream, overflow: 'hidden' },
  kitchenArt: { position: 'absolute', left: -39, top: 0, width: 468, height: 248 },
  heroFade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 46 },
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

  sheet: {
    marginTop: -18, paddingHorizontal: 16, paddingTop: 18, backgroundColor: color.bg,
    borderTopLeftRadius: 22, borderTopRightRadius: 22, minHeight: 420,
  },
  sectionTitleRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12,
  },
  title: { color: color.ink, fontSize: 22, fontWeight: '700' },
  count: { color: color.muted, fontSize: 13, fontWeight: '600' },

  filters: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  filter: {
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 18, backgroundColor: color.white,
    minHeight: 36, justifyContent: 'center',
  },
  filterSelected: { backgroundColor: color.ink },
  filterText: { color: color.ink, fontSize: 13, fontWeight: '600' },
  filterTextSelected: { color: color.white },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: {
    width: '31%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16,
    padding: 8, paddingBottom: 12,
  },
  cardPhoto: { height: 78, borderRadius: 12, marginBottom: 8 },
  cardName: { color: color.ink, fontSize: 12, lineHeight: 15, fontWeight: '600', marginBottom: 3 },
  cardQty: { color: color.muted, fontSize: 11, marginBottom: 7 },
  pill: {
    alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 7, paddingVertical: 4, borderRadius: 9, backgroundColor: color.bg,
  },
  pillDot: { width: 6, height: 6, borderRadius: 3 },
  pillText: { color: color.body, fontSize: 10.5, fontWeight: '600' },

  hint: {
    marginTop: 16, padding: 14, backgroundColor: color.white, borderRadius: 18,
    flexDirection: 'row', alignItems: 'center', gap: 12,
  },
  hintMark: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: color.greenSoft,
    alignItems: 'center', justifyContent: 'center',
  },
  hintMarkText: { color: color.green, fontSize: 15, fontWeight: '700' },
  hintText: { flex: 1, color: color.body, fontSize: 12.5, lineHeight: 17.5 },

  ctaWrap: { position: 'absolute', left: 0, right: 0, bottom: 74, paddingHorizontal: 16, paddingBottom: 12 },
  cta: {
    height: 54, borderRadius: 16, backgroundColor: color.red, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.7 },
});
