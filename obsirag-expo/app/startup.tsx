import { Redirect } from 'expo-router';

export default function StartupRoute() {
  return <Redirect href="/(tabs)" />;
}