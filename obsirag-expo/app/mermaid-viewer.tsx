import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { MermaidDiagram } from '../components/markdown/mermaid-diagram';
import { Screen } from '../components/ui/screen';
import { useAppStore } from '../store/app-store';

export default function MermaidViewerScreen() {
  const router = useRouter();
  const mermaidViewer = useAppStore((state) => state.mermaidViewer);
  const clearMermaidViewer = useAppStore((state) => state.clearMermaidViewer);

  const closeViewer = () => {
    clearMermaidViewer();
    router.back();
  };

  return (
    <Screen scroll={false} backgroundColor="#f4f1ea" contentStyle={styles.screen}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Diagramme Mermaid</Text>
          <Text style={styles.subtitle}>Vue plein ecran avec zoom, deplacement et defilement.</Text>
        </View>
        <Pressable style={styles.closeButton} onPress={closeViewer}>
          <Text style={styles.closeButtonText}>Fermer</Text>
        </Pressable>
      </View>
      {mermaidViewer?.code ? (
        <MermaidDiagram code={mermaidViewer.code} tone={mermaidViewer.tone} fullscreen />
      ) : (
        <View style={styles.emptyState}>
          <Text style={styles.emptyTitle}>Aucun diagramme charge</Text>
          <Text style={styles.emptyBody}>Ouvrez un diagramme Mermaid depuis le chat ou une note pour l'afficher ici.</Text>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    paddingTop: 18,
    gap: 14,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  headerCopy: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#1f160c',
    fontSize: 24,
    fontWeight: '800',
  },
  subtitle: {
    color: '#6f5d49',
    lineHeight: 20,
  },
  closeButton: {
    borderRadius: 999,
    backgroundColor: '#2f2f2f',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  closeButtonText: {
    color: '#f3f3f3',
    fontWeight: '700',
  },
  emptyState: {
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#fffdfa',
    padding: 18,
    gap: 8,
  },
  emptyTitle: {
    color: '#1f160c',
    fontSize: 18,
    fontWeight: '700',
  },
  emptyBody: {
    color: '#6f5d49',
    lineHeight: 20,
  },
});