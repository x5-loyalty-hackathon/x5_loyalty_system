import { StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { color } from '../theme/tokens';

export function PhotoStub({ label = 'фото', style }: { label?: string; style?: ViewStyle }) {
  return (
    <View style={[styles.stub, style]}>
      <View style={styles.stripeOne} />
      <View style={styles.stripeTwo} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stub: { overflow: 'hidden', backgroundColor: color.ghost, alignItems: 'center', justifyContent: 'flex-end' },
  stripeOne: { position: 'absolute', width: 220, height: 12, backgroundColor: color.ghostAlt, transform: [{ rotate: '-35deg' }] },
  stripeTwo: { position: 'absolute', width: 220, height: 12, top: 25, backgroundColor: color.ghostAlt, transform: [{ rotate: '-35deg' }] },
  label: { marginBottom: 8, color: color.ghostText, fontFamily: 'Courier', fontSize: 9 },
});
