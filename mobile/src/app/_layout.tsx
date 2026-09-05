import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { DemoProvider } from '../state/DemoContext';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <DemoProvider>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right' }} />
      </DemoProvider>
    </SafeAreaProvider>
  );
}
