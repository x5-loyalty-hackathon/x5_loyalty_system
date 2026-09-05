import { useEffect } from 'react';
import {
  ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BottomNav } from '../components/BottomNav';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';

export default function KitchenScreen() {
  const router = useRouter();
  const { progress, progressStatus, progressError, loadProgress, receiptStatus } = useDemo();

  useEffect(() => {
    if (progressStatus === 'idle') void loadProgress();
  }, [loadProgress, progressStatus]);

  const xpShare = progress
    ? progress.avatar_xp / Math.max(1, progress.avatar_xp + progress.xp_to_next_level)
    : 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.hero}>
            {/* Кадр как в макете: арт 468×248 со сдвигом влево на 39, полоса 286. */}
            <Image
              source={require('../../assets/kitchen/kitchen-band.png')}
              style={styles.kitchenArt}
            />
            <LinearGradient
              colors={['rgba(244,231,205,0)', color.cream]}
              style={styles.heroFade}
            />
            <View style={styles.speech}>
              <Text style={styles.speechText}>
                {receiptStatus
                  ? 'Чек пришёл — я разложил продукты и записал рецепт в книгу.'
                  : 'Молоко надо выпить сегодня. Сварим что-нибудь?'}
              </Text>
            </View>
            <Pressable accessibilityLabel="Меню" style={styles.menu}>
              <Text style={styles.menuText}>≡</Text>
            </Pressable>
            <Image
              source={require('../../assets/domovoi/mascot-spoon.png')}
              resizeMode="contain"
              style={styles.mascot}
            />
          </View>

          <View style={styles.sheet}>
            {progressStatus === 'loading' || progressStatus === 'idle' ? (
              <View style={styles.center}>
                <ActivityIndicator color={color.red} />
                <Text style={styles.centerText}>Домовой считает прогресс…</Text>
              </View>
            ) : progressStatus === 'error' || !progress ? (
              <View style={styles.center}>
                <Text style={styles.centerTitle}>Кухня не отвечает</Text>
                <Text style={styles.centerText}>{progressError}</Text>
                <Pressable style={styles.retry} onPress={loadProgress}>
                  <Text style={styles.retryText}>Повторить</Text>
                </Pressable>
              </View>
            ) : (
              <>
                <View style={styles.sectionTitleRow}>
                  <Text style={styles.title}>Кухня Домового</Text>
                  <Text style={styles.count}>уровень {progress.avatar_level}</Text>
                </View>

                <View style={styles.xpCard}>
                  <View style={styles.xpRow}>
                    <Text style={styles.xpValue}>{progress.avatar_xp} XP</Text>
                    <Text style={styles.xpHint}>
                      до уровня {progress.avatar_level + 1} — {progress.xp_to_next_level}
                    </Text>
                  </View>
                  <View style={styles.xpTrack}>
                    <View style={[styles.xpFill, { width: `${Math.round(xpShare * 100)}%` }]} />
                  </View>
                </View>

                <View style={styles.grid}>
                  <Stat value={String(progress.recipes_completed)} label="рецептов приготовлено" />
                  <Stat
                    value={`${Math.round(progress.markdown_savings)} ₽`}
                    label="фактическая экономия"
                    tone={color.green}
                  />
                  <Stat value={String(Math.round(progress.rescue_items))} label="куплено из подбора" />
                  <Stat value={String(progress.purchase_days)} label="дней с покупками" />
                </View>

                <View style={styles.hint}>
                  <View style={styles.hintMark}>
                    <Text style={styles.hintMarkText}>#{progress.private_rank.position}</Text>
                  </View>
                  <Text style={styles.hintText}>
                    Ваше место среди {progress.private_rank.cohort_size} участников.
                    Список других покупателей не показывается.
                  </Text>
                </View>
              </>
            )}
          </View>
        </ScrollView>

        <View style={styles.ctaWrap}>
          <Pressable style={styles.cta} onPress={() => router.push('/recipes')}>
            <Text style={styles.ctaText}>Что приготовить</Text>
            <Text style={styles.ctaArrow}>›</Text>
          </Pressable>
        </View>
        <BottomNav active="kitchen" />
      </View>
    </SafeAreaView>
  );
}

function Stat({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, tone ? { color: tone } : null]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
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
    borderTopLeftRadius: 22, borderTopRightRadius: 22, minHeight: 380,
  },
  sectionTitleRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12,
  },
  title: { color: color.ink, fontSize: 22, fontWeight: '700' },
  count: { color: color.muted, fontSize: 13, fontWeight: '600' },

  xpCard: { backgroundColor: color.white, borderRadius: 18, padding: 14, marginBottom: 12 },
  xpRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  xpValue: { color: color.ink, fontSize: 20, fontWeight: '700' },
  xpHint: { color: color.muted, fontSize: 12 },
  xpTrack: { height: 8, borderRadius: 4, backgroundColor: color.bg, marginTop: 10, overflow: 'hidden' },
  xpFill: { height: 8, borderRadius: 4, backgroundColor: color.red },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  stat: { width: '48%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16, padding: 14 },
  statValue: { color: color.ink, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  statLabel: { color: color.muted, fontSize: 11.5, lineHeight: 15 },

  hint: {
    marginTop: 12, padding: 14, backgroundColor: color.white, borderRadius: 18,
    flexDirection: 'row', alignItems: 'center', gap: 12,
  },
  hintMark: {
    minWidth: 44, height: 38, paddingHorizontal: 8, borderRadius: 12,
    backgroundColor: color.greenSoft, alignItems: 'center', justifyContent: 'center',
  },
  hintMarkText: { color: color.green, fontSize: 14, fontWeight: '700' },
  hintText: { flex: 1, color: color.body, fontSize: 12.5, lineHeight: 17.5 },

  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: 60, gap: 10 },
  centerTitle: { color: color.ink, fontSize: 17, fontWeight: '700' },
  centerText: { color: color.muted, fontSize: 13, textAlign: 'center' },
  retry: { marginTop: 6, paddingHorizontal: 22, paddingVertical: 12, borderRadius: 14, backgroundColor: color.red },
  retryText: { color: color.white, fontWeight: '700' },

  ctaWrap: { position: 'absolute', left: 0, right: 0, bottom: 74, paddingHorizontal: 16, paddingBottom: 12 },
  cta: {
    height: 54, borderRadius: 16, backgroundColor: color.red, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  ctaText: { color: color.white, fontSize: 16, fontWeight: '700' },
  ctaArrow: { color: color.white, fontSize: 16, fontWeight: '700', opacity: 0.7 },
});
