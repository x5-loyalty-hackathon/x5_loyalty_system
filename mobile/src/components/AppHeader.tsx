import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { color } from '../theme/tokens';

export function AppHeader({ title, subtitle, back = true }: { title: string; subtitle?: string; back?: boolean }) {
  const router = useRouter();
  return (
    <View style={styles.root}>
      {back ? (
        <Pressable onPress={() => router.back()} accessibilityLabel="Назад" style={styles.back}>
          <Text style={styles.backText}>‹</Text>
        </Pressable>
      ) : null}
      <View style={styles.copy}>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { minHeight: 58, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: color.white },
  back: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: color.bg },
  backText: { color: color.ink, fontSize: 24, fontWeight: '700', marginTop: -2 },
  copy: { flex: 1 },
  title: { color: color.ink, fontSize: 21, fontWeight: '700' },
  subtitle: { color: color.muted, fontSize: 12, marginTop: 3 },
});
