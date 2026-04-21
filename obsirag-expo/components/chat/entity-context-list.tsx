import { useEffect, useMemo, useState } from 'react';
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
  const [isTypeMenuOpen, setIsTypeMenuOpen] = useState(false);
  const typeOptions = useMemo(() => buildEntityTypeOptions(entities ?? []), [entities]);
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

  if (!entities?.length) {
    return null;
  }

  const effectiveSelectedTypeValue = selectedTypeValue === undefined ? preferredTypeValue : selectedTypeValue ?? undefined;
  const selectedTypeOption = typeOptions.find((option) => option.value === effectiveSelectedTypeValue);
  const visibleEntities = effectiveSelectedTypeValue
    ? entities.filter((entity) => entityTypeKey(entity.type, entity.typeLabel) === effectiveSelectedTypeValue)
    : entities;

  return (
    <View
      testID="entity-contexts-panel"
      style={[styles.container, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}
    >
      <Pressable testID="entity-contexts-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>Entités détectées</Text>
          <Text style={[styles.caption, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>
            {visibleEntities.length} entité{visibleEntities.length > 1 ? 's' : ''}
            {selectedTypeOption ? ` sur ${entities.length}` : ''}
          </Text>
        </View>
        <Text style={[styles.chevron, { color: theme.colors.primary, fontSize: scaleFontSize(12, scale) }]}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-contexts-panel-content" style={styles.content}>
          <EntityTypeFilterDropdown
            label={selectedTypeOption?.label ?? 'Tous les types d\'entités'}
            isOpen={isTypeMenuOpen}
            onToggle={() => setIsTypeMenuOpen((value) => !value)}
            onClose={() => setIsTypeMenuOpen(false)}
            options={[
              { label: 'Tous les types d\'entités', onSelect: () => setSelectedTypeValue(null), testID: 'entity-contexts-filter-option-all' },
              ...typeOptions.map((option) => ({
                label: `${option.label} · ${option.count}`,
                onSelect: () => setSelectedTypeValue(option.value),
                testID: `entity-contexts-filter-option-${option.value}`,
              })),
            ]}
          />
          <MarkdownNote markdown={buildEntityContextsMarkdown(visibleEntities)} tone={theme.isDark ? 'dark' : 'light'} theme={theme} />
        </View>
      ) : null}
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
};

function EntityTypeFilterDropdown({ label, isOpen, onToggle, onClose, options }: EntityTypeFilterDropdownProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();

  return (
    <View testID="entity-contexts-filter" style={[styles.dropdownWrapper, isOpen ? styles.dropdownWrapperOpen : null]}>
      <Pressable
        testID="entity-contexts-filter-trigger"
        style={[
          styles.dropdownTrigger,
          {
            backgroundColor: isOpen ? theme.colors.text : theme.colors.backgroundAlt,
            borderColor: isOpen ? theme.colors.text : theme.colors.border,
          },
        ]}
        onPress={onToggle}
      >
        <Text style={[styles.dropdownTriggerText, { color: isOpen ? theme.colors.background : theme.colors.text, fontSize: scaleFontSize(12, scale) }]} numberOfLines={1}>{label}</Text>
        <Text style={[styles.dropdownChevron, { color: isOpen ? theme.colors.background : theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>▾</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-contexts-filter-menu" style={[styles.dropdownMenu, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, shadowColor: theme.colors.shadow }]}>
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
              <Text style={[styles.dropdownOptionText, { color: theme.colors.text, fontSize: scaleFontSize(12, scale) }]}>{option.label}</Text>
            </Pressable>
          ))}
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
  dropdownWrapper: {
    position: 'relative',
    alignSelf: 'flex-start',
    zIndex: 20,
  },
  dropdownWrapperOpen: {
    zIndex: 40,
  },
  dropdownTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  dropdownTriggerText: {
    maxWidth: 190,
    fontWeight: '600',
  },
  dropdownChevron: {
    fontWeight: '700',
  },
  dropdownMenu: {
    position: 'absolute',
    top: 40,
    left: 0,
    minWidth: 220,
    borderRadius: 14,
    borderWidth: 1,
    paddingVertical: 6,
    shadowOpacity: 0.14,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 12,
  },
  dropdownOption: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  dropdownOptionText: {
    fontWeight: '600',
  },
});