import { Pressable, StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { EntityContext } from '../../types/domain';
import { MarkdownNote } from '../notes/markdown-note';

type EntityContextListProps = {
  entities?: EntityContext[];
  isOpen?: boolean;
  onToggleOpen?: () => void;
};

export function EntityContextList({ entities, isOpen = false, onToggleOpen }: EntityContextListProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  if (!entities?.length) {
    return null;
  }

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
      <Pressable testID="entity-contexts-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>Entités détectées</Text>
          <Text style={[styles.caption, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>{entities.length} entité{entities.length > 1 ? 's' : ''}</Text>
        </View>
        <Text style={[styles.chevron, { color: theme.colors.primary, fontSize: scaleFontSize(12, scale) }]}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-contexts-panel-content" style={styles.content}>
          <MarkdownNote markdown={buildEntityContextsMarkdown(entities)} tone={theme.isDark ? 'dark' : 'light'} theme={theme} />
        </View>
      ) : null}
    </View>
  );
}

function buildEntityContextsMarkdown(entities: EntityContext[]) {
  const lines = [
    '| N° | Nom de l\'entité | Explication de pourquoi l\'entité est en relation |',
    '| --- | --- | --- |',
  ];

  for (const [index, entity] of entities.entries()) {
    lines.push(
      `| ${index + 1} | ${escapeMarkdownTableCell(entity.value)} | ${escapeMarkdownTableCell(buildRelationExplanation(entity))} |`,
    );
  }

  return lines.join('\n');
}

function buildRelationExplanation(entity: EntityContext) {
  const explanation = entity.relationExplanation?.trim();
  if (explanation) {
    return explanation;
  }

  if (entity.ddgKnowledge?.abstractText?.trim()) {
    return entity.ddgKnowledge.abstractText.trim();
  }

  if (entity.notes[0]?.title) {
    return `${entity.value} est reliée à la réponse via ${entity.notes[0].title}.`;
  }

  return `${entity.value} est reliée au sujet traité dans cette réponse.`;
}

function escapeMarkdownTableCell(value: string) {
  return String(value || '')
    .replace(/\|/g, '\\|')
    .replace(/\r?\n+/g, ' ')
    .trim();
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
    borderRadius: 16,
    borderWidth: 1,
    padding: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  headerCopy: {
    gap: 2,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
  },
  caption: {
    fontSize: 12,
  },
  chevron: {
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    gap: 8,
  },
});