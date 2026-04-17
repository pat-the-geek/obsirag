import { Pressable, StyleSheet, Text, View } from 'react-native';

import { EntityContext } from '../../types/domain';
import { MarkdownNote } from '../notes/markdown-note';

type EntityContextListProps = {
  entities?: EntityContext[];
  isOpen?: boolean;
  onToggleOpen?: () => void;
};

export function EntityContextList({ entities, isOpen = false, onToggleOpen }: EntityContextListProps) {
  if (!entities?.length) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Pressable testID="entity-contexts-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Entités détectées</Text>
          <Text style={styles.caption}>{entities.length} entité{entities.length > 1 ? 's' : ''}</Text>
        </View>
        <Text style={styles.chevron}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-contexts-panel-content" style={styles.content}>
          <MarkdownNote markdown={buildEntityContextsMarkdown(entities)} tone="light" />
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
    backgroundColor: '#fbf8f3',
    borderWidth: 1,
    borderColor: '#ded5c9',
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
    color: '#3a2c1f',
  },
  caption: {
    fontSize: 12,
    color: '#7a6855',
  },
  chevron: {
    color: '#8a562b',
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    gap: 8,
  },
});