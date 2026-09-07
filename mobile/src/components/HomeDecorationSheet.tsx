import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useDemo } from '../state/DemoContext';
import { hasWallpaperVisual, wallpaperStyle } from '../domain/homeDecoration';
import { color } from '../theme/tokens';

export function HomeDecorationSheet({ onClose, onPreview }: {
  onClose: () => void; onPreview: (itemId: string | null) => void;
}) {
  const {
    decoration, decorationStatus, decorationError, decorationBusy, decorationFailedAction,
    chooseDecorationGoal, applyDecoration, retryHomeDecoration, loadHomeDecoration,
  } = useDemo();
  const [selection, setSelection] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const selectedId = selection ?? decoration?.applied_item_id ?? 'wallpaper_default';
  const selected = decoration?.items.find((item) => item.item_id === selectedId);
  const applied = selectedId === decoration?.applied_item_id;
  const goal = decoration?.items.find((item) => item.item_id === decoration.goal_item_id);
  const remaining = Math.max(0, (selected?.required_xp ?? 0) - (decoration?.avatar_xp ?? 0));
  const canRender = hasWallpaperVisual(selectedId);
  useEffect(() => { onPreview(selected && canRender ? selectedId : null); }, [selected, selectedId, canRender, onPreview]);
  const apply = async () => {
    if (selected && await applyDecoration(selected.item_id) && mounted.current) onClose();
  };

  return <Modal transparent animationType="slide" onRequestClose={onClose}>
    <View style={styles.modal}>
      <Pressable accessibilityLabel="Закрыть выбор обоев" style={styles.backdrop} onPress={onClose} />
      <View style={styles.previewLabel} pointerEvents="none" testID="decoration-preview-label">
        <Text style={styles.previewText}>{applied ? 'Ваше оформление' : 'Предпросмотр · ещё не применено'}</Text>
      </View>
      <View style={styles.sheet} accessibilityViewIsModal testID="home-decoration-sheet">
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>Обои для вашей кухни</Text>
            <Text style={styles.meta}>{decoration
              ? `Уровень ${decoration.avatar_level} · ${decoration.avatar_xp} XP · смена бесплатно`
              : 'Загружаем ваше оформление'}</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Закрыть оформление"
            testID="close-home-decoration" onPress={onClose} style={styles.close}>
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {decorationStatus === 'loading' ? <View style={styles.loading}>
            <ActivityIndicator color={color.brown} /><Text style={styles.copy}>Проверяем доступ…</Text>
          </View> : null}
          {decorationError ? <View style={styles.error} accessibilityLiveRegion="polite">
            <Text style={styles.copy}>{decorationError}</Text>
            <Text style={styles.hint}>При ошибке последнее подтверждённое оформление остаётся на месте.</Text>
            <Pressable accessibilityRole="button" testID="decoration-retry" disabled={decorationBusy}
              onPress={() => void retryHomeDecoration()} style={styles.retry}>
              <Text style={styles.link}>{decorationFailedAction ? 'Повторить действие' : 'Повторить загрузку'}</Text>
            </Pressable>
            {decorationFailedAction ? <Pressable accessibilityRole="button" disabled={decorationBusy}
              onPress={() => void loadHomeDecoration()} style={styles.retry}>
              <Text style={styles.link}>Обновить доступ</Text>
            </Pressable> : null}
          </View> : null}
          {goal ? <View style={styles.goal} testID="decoration-current-goal">
            <Text style={styles.goalText}>Моя цель: {goal.title}</Text>
            <Text style={styles.copy}>{goal.unlocked ? 'Цель достигнута — обои можно применить.'
              : `До открытия ещё ${Math.max(0, goal.required_xp - (decoration?.avatar_xp ?? 0))} XP`}</Text>
          </View> : null}
          <View style={styles.grid}>
            {decoration?.items.map((item) => {
              const paper = wallpaperStyle(item.item_id);
              const active = item.item_id === selectedId;
              return <Pressable key={item.item_id} accessibilityRole="button"
                accessibilityLabel={`${item.title}, ${item.unlocked ? 'открыто' : `уровень ${item.unlock_level}, нужно ${Math.max(0, item.required_xp - decoration.avatar_xp)} XP`}`}
                accessibilityState={{ selected: active, disabled: decorationBusy }} disabled={decorationBusy}
                testID={`decoration-item-${item.item_id}`} onPress={() => setSelection(item.item_id)}
                style={[styles.card, active && styles.cardActive]}>
                <View style={[styles.swatch, { backgroundColor: paper.base }]}>
                  {[0, 1, 2].map((dot) => <View key={dot} style={[styles.swatchMark,
                    { backgroundColor: paper.ink, left: 8 + dot * 12, top: dot % 2 ? 20 : 10 }]} />)}
                </View>
                <View style={styles.cardCopy}>
                  <Text style={styles.itemTitle}>{item.title}</Text>
                  <Text style={styles.itemMeta}>{item.item_id === decoration.applied_item_id ? 'Применено'
                    : item.unlocked ? 'Открыто' : `Уровень ${item.unlock_level} · ${item.required_xp} XP`}</Text>
                </View>
              </Pressable>;
            })}
          </View>
          {selected ? <View testID="decoration-selection-details">
            <Text style={styles.selectionTitle}>{selected.title}</Text>
            <Text style={styles.copy}>{selected.description}</Text>
            <Text style={styles.copy}>{selected.unlocked ? 'Открыто. Можно свободно менять — XP сохраняются.'
              : `Откроется на уровне ${selected.unlock_level}. Нужно ещё ${remaining} XP.`}</Text>
            {!canRender ? <Text style={styles.copy}>Предпросмотр этого варианта пока не подключён.</Text> : null}
          </View> : null}
          {!decoration?.items.length && decorationStatus === 'ready'
            ? <Text style={styles.copy}>Варианты оформления пока не появились.</Text> : null}
          <Text style={styles.hint}>20 XP за выполненное задание с подтверждённой покупкой, максимум один бонус на покупочный день.
            Обои — отдельный элемент дома. XP на оформление не тратятся.</Text>
        </ScrollView>
        {selected ? <View style={styles.actions}>
          <Pressable accessibilityRole="button" testID="decoration-apply"
            disabled={decorationBusy || !selected.unlocked || applied || !canRender}
            accessibilityState={{ disabled: decorationBusy || !selected.unlocked || applied || !canRender }}
            onPress={() => void apply()}
            style={[styles.primary, (decorationBusy || !selected.unlocked || applied || !canRender) && styles.disabled]}>
            <Text style={styles.primaryText}>{decorationBusy ? 'Сохраняем…' : applied ? 'Уже применено'
              : selected.unlocked ? 'Применить бесплатно' : `Закрыто · ещё ${remaining} XP`}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" testID="decoration-set-goal" disabled={decorationBusy}
            onPress={() => void chooseDecorationGoal(decoration?.goal_item_id === selectedId ? null : selectedId)}
            style={[styles.secondary, decorationBusy && styles.disabled]}>
            <Text style={styles.link}>{decoration?.goal_item_id === selectedId ? 'Снять цель' : 'Выбрать целью'}</Text>
          </Pressable>
        </View> : null}
      </View>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  modal: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(40,27,20,0.08)' },
  previewLabel: { position: 'absolute', top: 18, left: 18, backgroundColor: '#FFFFFFF2', borderRadius: 12, padding: 10 },
  previewText: { color: color.brown, fontSize: 12, fontWeight: '700' },
  sheet: { maxHeight: '68%', backgroundColor: '#FFFDF8', borderTopLeftRadius: 26, borderTopRightRadius: 26,
    paddingTop: 18, shadowColor: '#38261A', shadowOpacity: 0.14, shadowRadius: 18, elevation: 12 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, paddingBottom: 10, gap: 8 },
  headerCopy: { flex: 1 },
  title: { fontSize: 20, fontWeight: '700', color: color.brown },
  meta: { color: color.body, fontSize: 12, marginTop: 5 },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  closeText: { color: color.brown, fontSize: 28 },
  content: { paddingHorizontal: 18, paddingBottom: 14 },
  loading: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  copy: { color: color.body, fontSize: 12, lineHeight: 17, marginTop: 3 },
  hint: { color: color.muted, fontSize: 11, lineHeight: 16, marginTop: 12 },
  error: { backgroundColor: color.redSoft, borderRadius: 12, padding: 12, marginBottom: 12 },
  retry: { minHeight: 44, justifyContent: 'center' },
  link: { color: color.brown, fontSize: 13, fontWeight: '700' },
  goal: { backgroundColor: '#EDF2E7', borderRadius: 12, padding: 12, marginBottom: 12 },
  goalText: { color: '#496044', fontSize: 13, fontWeight: '700' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 6 },
  card: { width: '48%', flexGrow: 1, flexDirection: 'row', alignItems: 'center', padding: 8, gap: 8,
    minHeight: 70, backgroundColor: color.white, borderColor: '#E6DFD2', borderWidth: 1, borderRadius: 14 },
  cardActive: { borderColor: color.brown, backgroundColor: '#F6F0E5' },
  swatch: { width: 42, height: 44, borderRadius: 7, overflow: 'hidden' },
  swatchMark: { position: 'absolute', width: 3, height: 5, opacity: 0.75 },
  cardCopy: { flex: 1 },
  itemTitle: { color: color.brown, fontSize: 12, lineHeight: 16, fontWeight: '700' },
  itemMeta: { color: color.body, fontSize: 10, lineHeight: 14, marginTop: 4 },
  selectionTitle: { color: color.brown, fontSize: 15, fontWeight: '700', marginTop: 10 },
  actions: { paddingHorizontal: 18, paddingTop: 10, paddingBottom: 16, borderTopWidth: 1, borderTopColor: '#E6DFD2', gap: 2 },
  primary: { backgroundColor: color.brown, alignItems: 'center', justifyContent: 'center', minHeight: 46, borderRadius: 14 },
  primaryText: { color: color.white, fontSize: 14, fontWeight: '700' },
  secondary: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  disabled: { opacity: 0.45 },
});
