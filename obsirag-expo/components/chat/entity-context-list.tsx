import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { EntityContext } from '../../types/domain';

type Props = {
  entities?: EntityContext[];
  hiddenEntityValues?: string[];
  isOpen?: boolean;
  onToggleOpen?: () => void;
  onHideEntity?: (entityValue: string) => void;
};

export function EntityContextList({ entities, hiddenEntityValues = [], isOpen = false, onToggleOpen, onHideEntity }: Props) {
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

  // Entities not hidden
  const visibleEntities = useMemo(() => {
    const hiddenSet = new Set(hiddenEntityValues);
    const base = (entities ?? []).filter((e) => !hiddenSet.has(e.value));
    const effectiveType = selectedTypeValue === undefined ? preferredTypeValue : selectedTypeValue ?? undefined;
    return effectiveType ? base.filter((e) => entityTypeKey(e.type, e.typeLabel) === effectiveType) : base;
  }, [entities, hiddenEntityValues, selectedTypeValue, preferredTypeValue]);

  const totalVisible = useMemo(() => {
    const hiddenSet = new Set(hiddenEntityValues);
    return (entities ?? []).filter((e) => !hiddenSet.has(e.value)).length;
  }, [entities, hiddenEntityValues]);

  if (!entities?.length || totalVisible === 0) {
    return null;
  }

  const effectiveSelectedTypeValue = selectedTypeValue === undefined ? preferredTypeValue : selectedTypeValue ?? undefined;
  const selectedTypeOption = typeOptions.find((option) => option.value === effectiveSelectedTypeValue);
  const filterLabel = selectedTypeOption?.label ?? 'Tous les types d\'entités';

  return (
    <View
      testID="entity-contexts-panel"
      style={[styles.container, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}
    >
      <Pressable testID="entity-contexts-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>Entités détectées</Text>
          <Text style={[styles.caption, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>
            {selectedTypeOption
              ? `${visibleEntities.length} entité${visibleEntities.length > 1 ? 's' : ''} sur ${totalVisible}`
              : `${totalVisible} entité${totalVisible > 1 ? 's' : ''}`}
          </Text>
        </View>
        <Text style={[styles.chevron, { color: theme.colors.primary, fontSize: scaleFontSize(12, scale) }]}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="entity-contexts-panel-content" style={styles.content}>
          <EntityTypeFilterDropdown
            label={filterLabel}
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
          <View style={styles.entityList}>
            {visibleEntities.map((entity) => (
              <View
                key={entity.value}
                style={[styles.entityRow, { borderBottomColor: theme.colors.border }]}
              >
                <View style={styles.entityContent}>
                  <Text style={[styles.entityValue, { color: theme.colors.text, fontSize: scaleFontSize(12, scale) }]}>
                    {entity.value}
                    {entity.typeLabel ? (
                      <Text style={[styles.entityType, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>
                        {' '}· {entity.typeLabel}
                      </Text>
                    ) : null}
                  </Text>
                  {buildRelationExplanation(entity) ? (
                    <Text style={[styles.entityExplanation, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]} numberOfLines={3}>
                      {buildRelationExplanation(entity)}
                    </Text>
                  ) : null}
                </View>
                {onHideEntity ? (
                  <Pressable
                    testID={`entity-hide-${entity.value}`}
                    onPress={() => onHideEntity(entity.value)}
                    style={[styles.hideButton, { borderColor: theme.colors.border, backgroundColor: theme.colors.backgroundAlt }]}
                  >
                    <Text style={[styles.hideButtonText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>Masquer</Text>
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>
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
  compact?: boolean;
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
        <Text style={[styles.dropdownTriggerText, { color: isOpen ? theme.colors.background : theme.colors.text, fontSize: scaleFontSize(12, scale) }]}>{label}</Text>
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

function buildRelationExplanation(entity: EntityContext): string {
  const explanation = entity.relationExplanation?.trim();
  if (explanation) return explanation;
  if (entity.ddgKnowledge?.abstractText?.trim()) return entity.ddgKnowledge.abstractText.trim();
  if (entity.notes[0]?.title) return `${entity.value} est reliée à la réponse via ${entity.notes[0].title}.`;
  return '';
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
    if (left.isPreferred !== right.isPreferred) return left.isPreferred ? -1 : 1;
    const countDelta = right.count - left.count;
    if (countDelta !== 0) return countDelta;
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
    gap: 10,
  },
  entityList: {
    gap: 0,
  },
  entityRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  entityContent: {
    flex: 1,
    gap: 3,
  },
  entityValue: {
    fontWeight: '600',
    fontSize: 12,
  },
  entityType: {
    fontWeight: '400',
    fontSize: 11,
  },
  entityExplanation: {
    fontSize: 11,
    lineHeight: 16,
  },
  hideButton: {
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignSelf: 'flex-start',
    marginTop: 2,
  },
  hideButtonText: {
    fontWeight: '600',
  },
  dropdownWrapper: {
    position: 'relative',
    alignSelf: 'stretch',
    zIndex: 20,
  },
  dropdownWrapperOpen: {
    zIndex: 40,
  },
  dropdownTrigger: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  dropdownTriggerText: {
    flex: 1,
    fontWeight: '600',
  },
  dropdownChevron: {
    fontWeight: '700',
  },
  dropdownMenu: {
    marginTop: 8,
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
