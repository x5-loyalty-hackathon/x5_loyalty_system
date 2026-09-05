import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useDemo } from '../state/DemoContext';
import { color } from '../theme/tokens';

export function Choice({ label, selected = false, disabled = false, onPress }: {
  label: string; selected?: boolean; disabled?: boolean; onPress: () => void;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ selected, disabled }}
    disabled={disabled} onPress={onPress}
    style={[styles.choice, selected && styles.selected, disabled && styles.disabled]}>
    <Text style={[styles.label, selected && styles.selectedLabel]}>{label}</Text>
  </Pressable>;
}

export function ActionNotice() {
  const { busy, notice, actionError } = useDemo();
  return <View accessibilityLiveRegion="polite">
    {busy ? <Text style={styles.note}>Сохраняем на сервере…</Text> : null}
    {notice ? <Text style={styles.note}>{notice}</Text> : null}
    {actionError ? <Text style={[styles.note, { color: color.red }]}>{actionError}</Text> : null}
  </View>;
}

export const flowStyles = StyleSheet.create({
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 10 },
  panel: { backgroundColor: color.white, borderRadius: 18, padding: 16, marginBottom: 12 },
  text: { color: color.body, fontSize: 13, lineHeight: 19, marginVertical: 5 },
  title: { color: color.ink, fontWeight: '700', fontSize: 17, marginBottom: 8 },
});
const styles = StyleSheet.create({
  choice: { paddingHorizontal: 14, paddingVertical: 12, borderRadius: 16, borderWidth: 1,
    borderColor: color.line, backgroundColor: color.white, minHeight: 44 },
  selected: { backgroundColor: color.ink, borderColor: color.ink },
  disabled: { opacity: 0.45 },
  label: { color: color.ink, fontSize: 13, fontWeight: '600' },
  selectedLabel: { color: color.white },
  note: { color: color.body, fontSize: 13, lineHeight: 19, marginVertical: 8 },
});
