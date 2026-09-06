import { useEffect } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { DemoProfileSelector } from '../components/DemoProfileSelector';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';
import { levelShare } from '../domain/mealFlow';
import { money } from '../domain/copy';

export default function ProfileScreen() {
  const router = useRouter();
  const { progress, progressStatus, progressError, loadProgress } = useDemo();

  useEffect(() => {
    if (progressStatus === 'idle') void loadProgress();
  }, [loadProgress, progressStatus]);

  const xpShare = progress
    ? levelShare(progress)
    : 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <AppHeader title="Профиль" subtitle="Прогресс Домового" back={false} />
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {progressStatus === 'loading' || progressStatus === 'idle' ? (
            <View style={styles.center}>
              <ActivityIndicator color={color.red} />
              <Text style={styles.centerText}>Домовой считает прогресс…</Text>
            </View>
          ) : progressStatus === 'error' || !progress ? (
            <View style={styles.center}>
              <Image
                source={require('../../assets/domovoi/mascot-think.png')}
                resizeMode="contain"
                style={styles.centerMascot}
              />
              <Text style={styles.centerTitle}>Кухня не отвечает</Text>
              <Text style={styles.centerText}>{progressError}</Text>
              <Pressable style={styles.retry} onPress={loadProgress}>
                <Text style={styles.retryText}>Повторить</Text>
              </Pressable>
            </View>
          ) : (
            <>
              <View style={styles.header}>
                <Image
                  source={require('../../assets/domovoi/mascot-cook.png')}
                  resizeMode="contain"
                  style={styles.avatar}
                />
                <View style={styles.headerCopy}>
                  <Text style={styles.name}>Домовой</Text>
                  <Text style={styles.level}>уровень {progress.avatar_level}</Text>
                </View>
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
                <Stat value={String(progress.rewarded_meals)} label="заданий с наградой" />
                <Stat value={String(progress.recipes_completed)} label="отметок «приготовлено»" />
                <Stat value={String(progress.rescue_items)} label="уценённых единиц куплено" />
                <Stat value={String(progress.ready_meals_completed)} label="готовых блюд куплено" />
                <Stat value={money(progress.markdown_savings)} label="сэкономлено по чекам" />
                <Stat value={String(progress.purchase_days)} label="дней с покупками" />
                <Stat value={String(progress.verified_receipts)} label="подтверждённых чеков" />
              </View>

              <Pressable style={styles.styleLink} onPress={() => router.push('/kitchen-style')}>
                <View style={styles.styleLinkCopy}>
                  <Text style={styles.styleLinkTitle}>Убранство кухни</Text>
                  <Text style={styles.styleLinkHint}>
                    Предметы открываются с уровнем — выберите, что поставить
                  </Text>
                </View>
                <Text style={styles.styleLinkArrow}>›</Text>
              </Pressable>

              <Text style={styles.footnote}>
                До 20 XP за выбранное задание: готовку с подтверждённой покупкой или покупку готового блюда.
                Не больше одного бонуса за блюдо на покупочный день.
                Личная demo-статистика. Публичного рейтинга и денежных наград нет.
                Синтетические покупки не доказывают рост частоты покупок в реальности.
              </Text>
            </>
          )}
          <DemoProfileSelector />
        </ScrollView>
        <BottomNav active="profile" />
      </View>
    </SafeAreaView>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.bg },
  scroll: { padding: 16, paddingBottom: 100 },

  header: { flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 16 },
  avatar: { width: 84, height: 84 },
  headerCopy: { flex: 1 },
  name: { color: color.ink, fontSize: 22, fontWeight: '700', marginBottom: 4 },
  level: { color: color.muted, fontSize: 13, fontWeight: '600' },

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

  styleLink: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 12,
    padding: 14, backgroundColor: color.white, borderRadius: 18,
  },
  styleLinkCopy: { flex: 1 },
  styleLinkTitle: { color: color.ink, fontSize: 15, fontWeight: '700', marginBottom: 3 },
  styleLinkHint: { color: color.muted, fontSize: 12.5, lineHeight: 17 },
  styleLinkArrow: { color: color.muted, fontSize: 20, fontWeight: '700' },
  footnote: { marginTop: 16, color: color.muted, fontSize: 12, lineHeight: 17 },

  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: 80, gap: 10 },
  centerMascot: { width: 96, height: 96 },
  centerTitle: { color: color.ink, fontSize: 17, fontWeight: '700' },
  centerText: { color: color.muted, fontSize: 13, textAlign: 'center' },
  retry: { marginTop: 6, paddingHorizontal: 22, paddingVertical: 12, borderRadius: 14, backgroundColor: color.red },
  retryText: { color: color.white, fontWeight: '700' },
});
