import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ChatMessage, DdgKnowledge, EntityContext, RelatedNote } from '../../types/domain';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { TagPill } from '../ui/tag-pill';

const ENTITY_IMAGE_SIZE = 112;

type ConversationEntitySidebarProps = {
  entities: EntityContext[];
  onOpenNote?: (notePath: string) => void;
  onOpenTag?: (tag: string) => void;
  compact?: boolean;
  maxHeight?: number;
};

export function ConversationEntitySidebar({ entities, onOpenNote, onOpenTag, compact = false, maxHeight }: ConversationEntitySidebarProps) {
  if (!entities.length) {
    return null;
  }

  return (
    <View
      testID="conversation-entity-sidebar"
      style={[
        styles.panel,
        compact ? styles.panelCompact : styles.panelAside,
        Platform.OS === 'web' && !compact ? styles.panelStickyWeb : null,
        !compact && typeof maxHeight === 'number' ? { maxHeight } : null,
      ]}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Entites detectees</Text>
        <Text style={styles.caption}>{entities.length} entree{entities.length > 1 ? 's' : ''}</Text>
      </View>
      <ScrollView
        testID="conversation-entity-sidebar-scroll"
        style={styles.listScroll}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={!compact}
        nestedScrollEnabled
      >
        {entities.map((entity) => {
          const entityTag = entity.tag;
          const summary = entity.ddgKnowledge?.abstractText || entity.ddgKnowledge?.answer || entity.ddgKnowledge?.definition;

          return (
            <View key={entityKey(entity)} style={styles.card}>
              <View style={[styles.cardHeader, compact ? styles.cardHeaderCompact : null]}>
                {entity.imageUrl ? <Image source={{ uri: entity.imageUrl }} style={styles.image} resizeMode="contain" /> : <View style={[styles.image, styles.imagePlaceholder]} />}
                <View style={styles.cardCopy}>
                  <Text style={styles.entityTitle}>{entity.value}</Text>
                  <Text style={styles.entityType}>{entity.typeLabel}</Text>
                  {typeof entity.mentions === 'number' ? <Text style={styles.entityMeta}>{entity.mentions} mention{entity.mentions > 1 ? 's' : ''}</Text> : null}
                  {entityTag ? <TagPill label={entityTag} tone="dark" {...(onOpenTag ? { onPress: () => onOpenTag(entityTag) } : {})} /> : null}
                </View>
              </View>
              {summary ? <Text style={styles.entitySummary} numberOfLines={compact ? 3 : 4}>{summary}</Text> : null}
              {entity.notes.length ? (
                <View style={styles.notesSection}>
                  <Text style={styles.sectionLabel}>Notes liees</Text>
                  <View style={styles.notePills}>
                    {entity.notes.map((note) => (
                      <Pressable key={`${entityKey(entity)}-${note.filePath}`} testID="entity-note-pill" style={[styles.notePill, { maxWidth: ENTITY_IMAGE_SIZE + 48 }]} onPress={() => onOpenNote?.(note.filePath)}>
                        <Text style={styles.notePillText} numberOfLines={1}>
                          {buildCompactNoteLabel(note, ENTITY_IMAGE_SIZE)}
                        </Text>
                        {joinMetadataParts([
                          note.dateModified ? formatMetadataDate(note.dateModified) : null,
                          formatSizeBytes(note.sizeBytes),
                        ]) ? (
                          <Text style={styles.notePillMeta} numberOfLines={2}>
                            {joinMetadataParts([
                              note.dateModified ? formatMetadataDate(note.dateModified) : null,
                              formatSizeBytes(note.sizeBytes),
                            ])}
                          </Text>
                        ) : null}
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

export function aggregateConversationEntityContexts(messages: ChatMessage[]): EntityContext[] {
  const entitiesByKey = new Map<string, EntityContext>();

  for (const message of messages) {
    for (const entity of message.entityContexts ?? []) {
      const key = entityKey(entity);
      const current = entitiesByKey.get(key);
      if (!current) {
        const normalizedKnowledge = normalizeDdgKnowledge(entity.ddgKnowledge);
        entitiesByKey.set(key, {
          ...entity,
          notes: normalizeNotes(entity.notes),
          ...(normalizedKnowledge ? { ddgKnowledge: normalizedKnowledge } : {}),
        });
        continue;
      }

      const mergedKnowledge = mergeDdgKnowledge(current.ddgKnowledge, entity.ddgKnowledge);
      entitiesByKey.set(key, {
        type: current.type || entity.type,
        typeLabel: current.typeLabel || entity.typeLabel,
        value: current.value || entity.value,
        ...(((current.mentions ?? 0) + (entity.mentions ?? 0)) > 0
          ? { mentions: (current.mentions ?? 0) + (entity.mentions ?? 0) }
          : {}),
        ...(current.imageUrl || entity.imageUrl ? { imageUrl: current.imageUrl || entity.imageUrl } : {}),
        ...(current.tag || entity.tag ? { tag: current.tag || entity.tag } : {}),
        notes: mergeNotes(current.notes, entity.notes),
        ...(mergedKnowledge ? { ddgKnowledge: mergedKnowledge } : {}),
      });
    }
  }

  return [...entitiesByKey.values()].sort((left, right) => left.value.localeCompare(right.value, 'fr', { sensitivity: 'base' }));
}

export function buildCompactNoteLabel(note: RelatedNote, imageSize: number): string {
  const rawTitle = (note.title || note.filePath.split('/').pop() || note.filePath).replace(/\.md$/i, '').trim();
  const maxChars = Math.max(12, Math.floor(imageSize / 6));
  if (rawTitle.length <= maxChars) {
    return rawTitle;
  }
  return `${rawTitle.slice(0, maxChars).trimEnd()}…`;
}

function entityKey(entity: Pick<EntityContext, 'tag' | 'value'>): string {
  return String(entity.tag || entity.value || '').trim().toLocaleLowerCase('fr');
}

function normalizeNotes(notes: RelatedNote[]): RelatedNote[] {
  return mergeNotes([], notes);
}

function mergeNotes(current: RelatedNote[], incoming: RelatedNote[]): RelatedNote[] {
  const notesByPath = new Map<string, RelatedNote>();
  for (const note of [...current, ...incoming]) {
    if (!note.filePath) {
      continue;
    }
    notesByPath.set(note.filePath, note);
  }
  return [...notesByPath.values()].sort((left, right) => (left.title || left.filePath).localeCompare(right.title || right.filePath, 'fr', { sensitivity: 'base' }));
}

function normalizeDdgKnowledge(value?: DdgKnowledge): DdgKnowledge | undefined {
  if (!value) {
    return undefined;
  }
  return { ...value };
}

function mergeDdgKnowledge(current?: DdgKnowledge, incoming?: DdgKnowledge): DdgKnowledge | undefined {
  if (!current) {
    return normalizeDdgKnowledge(incoming);
  }
  if (!incoming) {
    return current;
  }

  const infobox = current.infobox?.length ? current.infobox : incoming.infobox;
  const relatedTopics = current.relatedTopics?.length ? current.relatedTopics : incoming.relatedTopics;

  return {
    ...(current.heading || incoming.heading ? { heading: current.heading || incoming.heading } : {}),
    ...(current.entity || incoming.entity ? { entity: current.entity || incoming.entity } : {}),
    ...(current.abstractText || incoming.abstractText ? { abstractText: current.abstractText || incoming.abstractText } : {}),
    ...(current.answer || incoming.answer ? { answer: current.answer || incoming.answer } : {}),
    ...(current.answerType || incoming.answerType ? { answerType: current.answerType || incoming.answerType } : {}),
    ...(current.definition || incoming.definition ? { definition: current.definition || incoming.definition } : {}),
    ...(infobox?.length ? { infobox } : {}),
    ...(relatedTopics?.length ? { relatedTopics } : {}),
  };
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: 18,
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#d8cfc0',
    padding: 14,
    gap: 12,
  },
  panelAside: {
    width: 320,
    alignSelf: 'flex-start',
  },
  panelCompact: {
    width: '100%',
  },
  panelStickyWeb: {
    position: 'sticky' as 'absolute',
    top: 18,
  },
  listScroll: {
    flexGrow: 0,
  },
  header: {
    gap: 2,
  },
  title: {
    color: '#1f160c',
    fontSize: 16,
    fontWeight: '800',
  },
  caption: {
    color: '#7a6855',
    fontSize: 12,
  },
  list: {
    gap: 12,
  },
  card: {
    borderRadius: 16,
    backgroundColor: '#f7f2ea',
    borderWidth: 1,
    borderColor: '#ded5c9',
    padding: 12,
    gap: 10,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  cardHeaderCompact: {
    alignItems: 'center',
  },
  image: {
    width: ENTITY_IMAGE_SIZE,
    height: ENTITY_IMAGE_SIZE,
    borderRadius: 14,
    backgroundColor: '#e7ded2',
    flexShrink: 0,
  },
  imagePlaceholder: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
  },
  cardCopy: {
    flex: 1,
    gap: 6,
  },
  entityTitle: {
    color: '#2f2419',
    fontSize: 18,
    fontWeight: '800',
  },
  entityType: {
    color: '#6d5a47',
    fontSize: 13,
    fontWeight: '600',
  },
  entityMeta: {
    color: '#7a6855',
    fontSize: 12,
  },
  entitySummary: {
    color: '#4f402d',
    lineHeight: 20,
  },
  notesSection: {
    gap: 6,
  },
  sectionLabel: {
    color: '#5d4b38',
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  notePills: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  notePill: {
    borderRadius: 14,
    backgroundColor: '#efe5d8',
    borderWidth: 1,
    borderColor: '#dbcdb8',
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 2,
  },
  notePillText: {
    color: '#4b3c2b',
    fontSize: 12,
    fontWeight: '700',
  },
  notePillMeta: {
    color: '#7a6855',
    fontSize: 11,
  },
});