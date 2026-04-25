import { useEffect, useMemo, useState } from 'react';
import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { ChatMessage, DdgKnowledge, EntityContext, RelatedNote } from '../../types/domain';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { TagPill } from '../ui/tag-pill';

const ENTITY_IMAGE_SIZE = 112;

type ConversationEntitySidebarProps = {
  entities: EntityContext[];
  hiddenEntities?: EntityContext[];
  onOpenNote?: (notePath: string) => void;
  onOpenTag?: (tag: string) => void;
  onHideEntity?: (entityValue: string) => void;
  onUnhideEntity?: (entityValue: string) => void;
  compact?: boolean;
  maxHeight?: number;
};

export function ConversationEntitySidebar({ entities, hiddenEntities = [], onOpenNote, onOpenTag, onHideEntity, onUnhideEntity, compact = false, maxHeight }: ConversationEntitySidebarProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  const [isTypeMenuOpen, setIsTypeMenuOpen] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const typeOptions = useMemo(() => buildEntityTypeOptions(entities), [entities]);
  const preferredTypeValue = useMemo(() => typeOptions.find((option) => option.isPreferred)?.value, [typeOptions]);
  const [selectedTypeValue, setSelectedTypeValue] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (!typeOptions.length) {
      setSelectedTypeValue(undefined);
      return;
    }

    if (selectedTypeValue === undefined) {
      setSelectedTypeValue(preferredTypeValue ?? null);
      return;
    }

    if (selectedTypeValue === null || typeOptions.some((option) => option.value === selectedTypeValue)) {
      return;
    }

    setSelectedTypeValue(preferredTypeValue ?? null);
  }, [preferredTypeValue, selectedTypeValue, typeOptions]);

  if (!entities.length) {
    return null;
  }

  const effectiveSelectedTypeValue = selectedTypeValue === undefined ? preferredTypeValue : selectedTypeValue ?? undefined;
  const selectedTypeOption = typeOptions.find((option) => option.value === effectiveSelectedTypeValue);
  const filterLabel = selectedTypeOption?.label ?? 'Tous les types d\'entites';
  const visibleEntities = effectiveSelectedTypeValue
    ? entities.filter((entity) => entityTypeKey(entity.type, entity.typeLabel) === effectiveSelectedTypeValue)
    : entities;

  return (
    <View
      testID="conversation-entity-sidebar"
      style={[
        styles.panel,
        { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
        compact ? styles.panelCompact : styles.panelAside,
        Platform.OS === 'web' && !compact ? styles.panelStickyWeb : null,
        !compact && typeof maxHeight === 'number' ? { maxHeight } : null,
      ]}
    >
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(16, scale) }]}>Entites detectees</Text>
          <Text style={[styles.caption, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>
            {visibleEntities.length} entree{visibleEntities.length > 1 ? 's' : ''}
            {selectedTypeOption ? ` sur ${entities.length}` : ''}
          </Text>
        </View>
        <EntityTypeFilterDropdown
          label={filterLabel}
          isOpen={isTypeMenuOpen}
          onToggle={() => setIsTypeMenuOpen((value) => !value)}
          onClose={() => setIsTypeMenuOpen(false)}
          compact={compact}
          options={[
            { label: 'Tous les types d\'entites', onSelect: () => setSelectedTypeValue(null), testID: 'entity-type-filter-option-all' },
            ...typeOptions.map((option) => ({
              label: `${option.label} · ${option.count}`,
              onSelect: () => setSelectedTypeValue(option.value),
              testID: `entity-type-filter-option-${option.value}`,
            })),
          ]}
        />
      </View>
      <ScrollView
        testID="conversation-entity-sidebar-scroll"
        style={styles.listScroll}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={!compact}
        nestedScrollEnabled
      >
        {visibleEntities.length ? visibleEntities.map((entity) => {
          const entityTag = entity.tag;
          const summary = entity.ddgKnowledge?.abstractText || entity.ddgKnowledge?.answer || entity.ddgKnowledge?.definition;

          return (
            <View testID="conversation-entity-card" key={entityKey(entity)} style={[styles.card, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
              <View style={[styles.cardHeader, compact ? styles.cardHeaderCompact : null]}>
                {entity.imageUrl ? (
                  <Image source={{ uri: entity.imageUrl }} style={[styles.image, { backgroundColor: theme.colors.mediaSurface }]} resizeMode="contain" />
                ) : (
                  <View style={[styles.image, styles.imagePlaceholder, { backgroundColor: theme.colors.mediaSurface, borderColor: theme.colors.border }]} />
                )}
                <View style={styles.cardCopy}>
                  <Text style={[styles.entityTitle, { color: theme.colors.text, fontSize: scaleFontSize(18, scale) }]}>{entity.value}</Text>
                  <Text style={[styles.entityType, { color: theme.colors.textMuted, fontSize: scaleFontSize(13, scale) }]}>{entity.typeLabel}</Text>
                  {typeof entity.mentions === 'number' ? <Text style={[styles.entityMeta, { color: theme.colors.textSubtle, fontSize: scaleFontSize(12, scale) }]}>{entity.mentions} mention{entity.mentions > 1 ? 's' : ''}</Text> : null}
                  {entityTag ? <TagPill label={entityTag} tone={theme.isDark ? 'dark' : 'light'} {...(onOpenTag ? { onPress: () => onOpenTag(entityTag) } : {})} /> : null}
                </View>
              </View>
              {summary ? <Text style={[styles.entitySummary, { color: theme.colors.textMuted, fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(20, scale) }]} numberOfLines={compact ? 3 : 4}>{summary}</Text> : null}
              {entity.notes.length ? (
                <View style={styles.notesSection}>
                  <Text style={[styles.sectionLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>Notes liees</Text>
                  <View style={styles.notePills}>
                    {entity.notes.map((note) => (
                      <Pressable key={`${entityKey(entity)}-${note.filePath}`} testID="entity-note-pill" style={[styles.notePill, { maxWidth: ENTITY_IMAGE_SIZE + 48, backgroundColor: theme.colors.backgroundAlt, borderColor: theme.colors.border }]} onPress={() => onOpenNote?.(note.filePath)}>
                        <Text style={[styles.notePillText, { color: theme.colors.text, fontSize: scaleFontSize(12, scale) }]} numberOfLines={1}>
                          {buildCompactNoteLabel(note, ENTITY_IMAGE_SIZE)}
                        </Text>
                        {joinMetadataParts([
                          note.dateModified ? formatMetadataDate(note.dateModified) : null,
                          formatSizeBytes(note.sizeBytes),
                        ]) ? (
                          <Text style={[styles.notePillMeta, { color: theme.colors.textSubtle, fontSize: scaleFontSize(11, scale) }]} numberOfLines={2}>
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
              {onHideEntity ? (
                <Pressable
                  testID={`sidebar-entity-hide-${entity.value}`}
                  style={[styles.hideButton, { borderColor: theme.colors.border, backgroundColor: theme.colors.backgroundAlt }]}
                  onPress={() => onHideEntity(entity.value)}
                >
                  <Text style={[styles.hideButtonText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>Masquer</Text>
                </Pressable>
              ) : null}
            </View>
          );
        }) : (
          <View style={[styles.emptyState, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
            <Text style={[styles.emptyStateTitle, { color: theme.colors.text, fontSize: scaleFontSize(14, scale) }]}>Aucune entite pour ce filtre</Text>
            <Text style={[styles.emptyStateBody, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale), lineHeight: scaleLineHeight(18, scale) }]}>Choisissez un autre type d'entite ou revenez a Tous les types d'entites.</Text>
          </View>
        )}
        {hiddenEntities.length > 0 ? (
          <View style={styles.hiddenSection}>
            <Pressable
              testID="sidebar-toggle-hidden"
              style={[styles.hiddenToggle, { borderColor: theme.colors.border }]}
              onPress={() => setShowHidden((v) => !v)}
            >
              <Text style={[styles.hiddenToggleText, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>
                {showHidden ? 'Masquer les entités cachées' : `Afficher les entités masquées (${hiddenEntities.length})`}
              </Text>
            </Pressable>
            {showHidden ? hiddenEntities.map((entity) => (
              <View key={entityKey(entity)} style={[styles.hiddenCard, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
                <View style={styles.hiddenCardRow}>
                  <View style={styles.hiddenCardCopy}>
                    <Text style={[styles.hiddenEntityTitle, { color: theme.colors.textMuted, fontSize: scaleFontSize(14, scale) }]}>{entity.value}</Text>
                    {entity.typeLabel ? <Text style={[styles.hiddenEntityType, { color: theme.colors.textSubtle, fontSize: scaleFontSize(12, scale) }]}>{entity.typeLabel}</Text> : null}
                  </View>
                  {onUnhideEntity ? (
                    <Pressable
                      testID={`sidebar-entity-unhide-${entity.value}`}
                      style={[styles.unhideButton, { borderColor: theme.colors.primary, backgroundColor: theme.colors.primaryMuted }]}
                      onPress={() => onUnhideEntity(entity.value)}
                    >
                      <Text style={[styles.unhideButtonText, { color: theme.colors.primary, fontSize: scaleFontSize(11, scale) }]}>Reprendre</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            )) : null}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

type EntityTypeFilterDropdownProps = {
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  options: Array<{
    label: string;
    onSelect: () => void;
    testID?: string;
  }>;
  compact?: boolean;
};

function EntityTypeFilterDropdown({ label, isOpen, onToggle, onClose, options, compact = false }: EntityTypeFilterDropdownProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();

  return (
    <View
      testID="entity-type-filter"
      style={[
        styles.dropdownWrapper,
        compact ? styles.dropdownWrapperCompact : styles.dropdownWrapperWide,
        isOpen ? styles.dropdownWrapperOpen : null,
      ]}
    >
      <Pressable
        testID="entity-type-filter-trigger"
        style={[
          styles.dropdownTrigger,
          {
            backgroundColor: isOpen ? theme.colors.text : theme.colors.backgroundAlt,
            borderColor: isOpen ? theme.colors.text : theme.colors.border,
          },
        ]}
        onPress={onToggle}
      >
        <Text
          style={[
            styles.dropdownTriggerText,
            compact ? styles.dropdownTriggerTextCompact : styles.dropdownTriggerTextWide,
            { color: isOpen ? theme.colors.background : theme.colors.text, fontSize: scaleFontSize(13, scale) },
          ]}
        >
          {label}
        </Text>
        <Text style={[styles.dropdownChevron, { color: isOpen ? theme.colors.background : theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>▾</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-type-filter-menu" style={[styles.dropdownMenu, compact ? styles.dropdownMenuCompact : styles.dropdownMenuWide, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, shadowColor: theme.colors.shadow }]}>
          {options.map((option) => (
            <Pressable
              key={option.label}
              {...(option.testID ? { testID: option.testID } : {})}
              style={styles.dropdownOption}
              onPress={() => {
                option.onSelect();
                onClose();
              }}
            >
              <Text style={[styles.dropdownOptionText, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
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

type EntityTypeOption = {
  value: string;
  label: string;
  count: number;
  isPreferred: boolean;
};

function buildEntityTypeOptions(entities: EntityContext[]): EntityTypeOption[] {
  const optionsByValue = new Map<string, EntityTypeOption>();

  for (const entity of entities) {
    const value = entityTypeKey(entity.type, entity.typeLabel);
    const existing = optionsByValue.get(value);
    if (existing) {
      existing.count += 1;
      continue;
    }

    optionsByValue.set(value, {
      value,
      label: entity.typeLabel?.trim() || entity.type?.trim() || 'Type inconnu',
      count: 1,
      isPreferred: isPersonEntityType(entity.type, entity.typeLabel),
    });
  }

  return [...optionsByValue.values()].sort((left, right) => {
    if (left.isPreferred !== right.isPreferred) {
      return left.isPreferred ? -1 : 1;
    }

    const countDelta = right.count - left.count;
    if (countDelta !== 0) {
      return countDelta;
    }

    return left.label.localeCompare(right.label, 'fr', { sensitivity: 'base' });
  });
}

function entityTypeKey(type: string, typeLabel: string): string {
  return String(type || typeLabel || '').trim().toLocaleLowerCase('fr');
}

function isPersonEntityType(type?: string, typeLabel?: string): boolean {
  const normalizedType = String(type || '').trim().toLocaleLowerCase('fr');
  const normalizedLabel = String(typeLabel || '').trim().toLocaleLowerCase('fr');
  return normalizedType === 'person' || normalizedType === 'personne' || normalizedLabel === 'personne' || normalizedLabel === 'person';
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
    borderWidth: 1,
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
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 10,
  },
  headerCopy: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 16,
    fontWeight: '800',
  },
  caption: {
    fontSize: 12,
  },
  dropdownWrapper: {
    position: 'relative',
    zIndex: 30,
  },
  dropdownWrapperWide: {
    width: '100%',
  },
  dropdownWrapperCompact: {
    width: '100%',
  },
  dropdownWrapperOpen: {
    zIndex: 60,
  },
  dropdownTrigger: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  dropdownTriggerText: {
    flex: 1,
    fontWeight: '600',
  },
  dropdownTriggerTextWide: {
    maxWidth: '100%',
  },
  dropdownTriggerTextCompact: {
    maxWidth: '100%',
  },
  dropdownChevron: {
    fontWeight: '700',
  },
  dropdownMenu: {
    marginTop: 8,
    zIndex: 120,
    borderRadius: 14,
    borderWidth: 1,
    paddingVertical: 6,
    shadowOpacity: 0.14,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 12,
  },
  dropdownMenuWide: {
    minWidth: 0,
  },
  dropdownMenuCompact: {
    minWidth: 0,
  },
  dropdownOption: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  dropdownOptionText: {
    fontWeight: '600',
  },
  list: {
    gap: 12,
  },
  emptyState: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 12,
    gap: 6,
  },
  emptyStateTitle: {
    fontWeight: '700',
  },
  emptyStateBody: {
    fontSize: 12,
  },
  card: {
    borderRadius: 16,
    borderWidth: 1,
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
    flexShrink: 0,
  },
  imagePlaceholder: {
    borderWidth: 1,
  },
  cardCopy: {
    flex: 1,
    gap: 6,
  },
  entityTitle: {
    fontSize: 18,
    fontWeight: '800',
  },
  entityType: {
    fontSize: 13,
    fontWeight: '600',
  },
  entityMeta: {
    fontSize: 12,
  },
  entitySummary: {
    lineHeight: 20,
  },
  notesSection: {
    gap: 6,
  },
  sectionLabel: {
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
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 2,
  },
  notePillText: {
    fontSize: 12,
    fontWeight: '700',
  },
  notePillMeta: {
    fontSize: 11,
  },
  hideButton: {
    alignSelf: 'flex-start',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  hideButtonText: {
    fontWeight: '600',
  },
  hiddenSection: {
    gap: 8,
    marginTop: 4,
  },
  hiddenToggle: {
    borderRadius: 8,
    borderWidth: 1,
    borderStyle: 'dashed',
    paddingHorizontal: 10,
    paddingVertical: 7,
    alignSelf: 'stretch',
  },
  hiddenToggleText: {
    fontWeight: '600',
    textAlign: 'center',
  },
  hiddenCard: {
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  hiddenCardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  hiddenCardCopy: {
    flex: 1,
    gap: 2,
  },
  hiddenEntityTitle: {
    fontWeight: '600',
  },
  hiddenEntityType: {
    fontWeight: '400',
  },
  unhideButton: {
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
    flexShrink: 0,
  },
  unhideButtonText: {
    fontWeight: '700',
  },
});