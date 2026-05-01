import { Redirect, usePathname } from 'expo-router';
import { Platform, StyleSheet, Text, View } from 'react-native';

export default function NotFoundRoute() {
  const pathname = usePathname();

  // /index is served as SPA fallback — redirect to root instead of showing 404
  if (pathname === '/index' || pathname === '/index/') {
    return <Redirect href="/" />;
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Page introuvable</Text>
      <Text style={styles.subtitle}>{pathname}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f4f1ea',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: '#1f160c',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#6f5d49',
  },
});
