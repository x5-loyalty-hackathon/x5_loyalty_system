import { useEffect } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from '../components/AppHeader';
import { BottomNav } from '../components/BottomNav';
import { useDemo } from '../state/DemoContext';
import { KITCHEN_UPGRADES, isUnlocked, nextUpgrade, type KitchenUpgrade } from '../data/kitchenUpgrades';
import { color } from '../theme/tokens';

export default function KitchenStyleScreen() {
  const { progress, progressStatus, loadProgress, equipped, toggleUpgrade } = useDemo();

  useEffect(() => {
    if (progressStatus === 'idle') void loadProgress();
  }, [loadProgress, progressStatus]);

  const level = progress?.avatar_level ?? 1;
  const opened = KITCHEN_UPGRADES.filter((upgrade) => isUnlocked(upgrade, level)).length;
  const next = nextUpgrade(level);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.shell}>
        <AppHeader title="Убранство кухни" subtitle={`Открыто ${opened} из ${KITCHEN_UPGRADES.length}`} />
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={styles.intro}>
            Предметы открываются с уровнем и остаются навсегда. Опыт за них не
            тратится — отметьте, что поставить на кухню.
          </Text>

          {next ? (
            <View style={styles.nextCard}>
              <Text style={styles.nextTitle}>Дальше: {next.title}</Text>
              <Text style={styles.nextHint}>
                откроется на {next.level} уровне, сейчас {level}
              </Text>
            </View>
          ) : (
            <View style={styles.nextCard}>
              <Text style={styles.nextTitle}>Открыто всё</Text>
              <Text style={styles.nextHint}>Кухня обставлена полностью</Text>
            </View>
          )}

          <View style={styles.grid}>
            {KITCHEN_UPGRADES.map((upgrade) => (
              <UpgradeCard
                key={upgrade.id}
                upgrade={upgrade}
                unlocked={isUnlocked(upgrade, level)}
                on={!!equipped[upgrade.id]}
                onToggle={() => toggleUpgrade(upgrade.id)}
              />
            ))}
          </View>
        </ScrollView>
        <BottomNav active="profile" />
      </View>
    </SafeAreaView>
  );
}

function UpgradeCard({
  upgrade, unlocked, on, onToggle,
}: { upgrade: KitchenUpgrade; unlocked: boolean; on: boolean; onToggle: () => void }) {
  return (
    <Pressable
      style={[styles.card, on && styles.cardOn, !unlocked && styles.cardLocked]}
      disabled={!unlocked}
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: on, disabled: !unlocked }}
    >
      <View style={styles.preview}>
        <Image
          source={upgrade.source}
          style={[styles.previewImage, !unlocked && styles.previewLocked]}
          resizeMode="contain"
        />
        <View style={[styles.check, on && styles.checkOn]}>
          <Text style={[styles.checkMark, on && styles.checkMarkOn]}>{on ? '✓' : ''}</Text>
        </View>
      </View>
      <Text style={styles.cardTitle} numberOfLines={1}>{upgrade.title}</Text>
      <Text style={styles.cardHint} numberOfLines={2}>
        {unlocked ? upgrade.hint : `Уровень ${upgrade.level}`}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: color.white },
  shell: { flex: 1, backgroundColor: color.bg },
  scroll: { padding: 16, paddingBottom: 100 },

  intro: { color: color.body, fontSize: 13, lineHeight: 18, marginBottom: 12 },
  nextCard: { backgroundColor: color.white, borderRadius: 18, padding: 14, marginBottom: 14 },
  nextTitle: { color: color.ink, fontSize: 15, fontWeight: '700', marginBottom: 3 },
  nextHint: { color: color.muted, fontSize: 12.5 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: {
    width: '48%', flexGrow: 1, backgroundColor: color.white, borderRadius: 16,
    padding: 10, borderWidth: 2, borderColor: 'transparent',
  },
  cardOn: { borderColor: color.green },
  cardLocked: { opacity: 0.55 },

  preview: {
    height: 84, borderRadius: 12, backgroundColor: color.cream,
    alignItems: 'center', justifyContent: 'center', marginBottom: 8, overflow: 'hidden',
  },
  previewImage: { width: '80%', height: '80%' },
  previewLocked: { opacity: 0.35 },
  check: {
    position: 'absolute', right: 6, top: 6, width: 22, height: 22, borderRadius: 11,
    borderWidth: 1, borderColor: color.line, backgroundColor: color.white,
    alignItems: 'center', justifyContent: 'center',
  },
  checkOn: { backgroundColor: color.green, borderColor: color.green },
  checkMark: { fontSize: 12, fontWeight: '700', color: color.white },
  checkMarkOn: { color: color.white },

  cardTitle: { color: color.ink, fontSize: 13.5, fontWeight: '700', marginBottom: 3 },
  cardHint: { color: color.muted, fontSize: 11.5, lineHeight: 15 },
});
