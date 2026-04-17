import { Pressable, StyleSheet, Text } from 'react-native';
import { useRouter } from 'expo-router';

import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';

export default function LoginScreen() {
  const router = useRouter();

  return (
    <Screen>
      <SectionCard title="Session locale" subtitle="Ce projet scaffold laisse le choix entre token simple, mot de passe local ou auth plus complete.">
        <Text style={styles.copy}>
          La specification prevoit un mode single-user simple. Ce point est volontairement leger ici pour laisser la strategie d'authentification ouverte.
        </Text>
        <Pressable style={styles.button} onPress={() => router.replace('/(auth)/server-config')}>
          <Text style={styles.buttonText}>Configurer le serveur</Text>
        </Pressable>
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  copy: {
    color: '#4f402d',
    lineHeight: 22,
  },
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  buttonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
});
