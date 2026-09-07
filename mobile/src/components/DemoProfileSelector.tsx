import { Text, View } from 'react-native';
import { useDemo } from '../state/DemoContext';
import { Choice, flowStyles as ui } from './FlowControls';

export function DemoProfileSelector() {
  const { profile, profiles, switchProfile } = useDemo();
  return <View>
    <Text style={ui.text}>Только для демонстрации — синтетические покупатели</Text>
    <View style={ui.choices}>{profiles.map((item) =>
      <Choice key={item.id} label={item.label} selected={profile.id === item.id}
        onPress={() => switchProfile(item.id)} />)}</View>
    <Text style={ui.text}>{profile.description} В истории {profile.purchaseHistory.length} чека.
      {' '}При смене покупателя текущий план и кухня сбрасываются; книга и XP загружаются с сервера.</Text>
  </View>;
}
