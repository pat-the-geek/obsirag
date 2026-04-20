import { Pressable, StyleSheet, Text } from 'react-native';
import { useRouter } from 'expo-router';

import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';

export default function LoginScreen() {
  const router = useRouter();
  const theme = useAppTheme();
  const { scale } = useAppFontScale();

  return (
    <Screen>
      <SectionCard title="Session locale" subtitle="Ce projet scaffold laisse le choix entre token simple, mot de passe local ou auth plus complete.">
        <Text style={[styles.copy, { color: theme.colors.textMuted, fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(22, scale) }]}>
          La specification prevoit un mode single-user simple. Ce point est volontairement leger ici pour laisser la strategie d'authentification ouverte.
        </Text>
        <Pressable style={[styles.button, { backgroundColor: theme.colors.primary }]} onPress={() => router.replace('/(auth)/server-config')}>
          <Text style={[styles.buttonText, { color: theme.colors.primaryText, fontSize: scaleFontSize(13, scale) }]}>Configurer le serveur</Text>
        </Pressable>
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  copy: {
    lineHeight: 22,
  },
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  buttonText: {
    fontWeight: '700',
  },
});
