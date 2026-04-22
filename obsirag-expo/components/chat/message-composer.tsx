import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';

type MessageComposerProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  withEuria?: boolean;
  withRag?: boolean;
  onToggleWithEuria?: (value: boolean) => void;
  onToggleWithRag?: (value: boolean) => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  secondaryActionDisabled?: boolean;
  tertiaryActionLabel?: string;
  onTertiaryAction?: () => void;
  tertiaryActionDisabled?: boolean;
};

export function MessageComposer({
  value,
  onChangeText,
  onSubmit,
  disabled,
  withEuria,
  withRag,
  onToggleWithEuria,
  onToggleWithRag,
  secondaryActionLabel,
  onSecondaryAction,
  secondaryActionDisabled,
  tertiaryActionLabel,
  onTertiaryAction,
  tertiaryActionDisabled,
}: MessageComposerProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  const [localValue, setLocalValue] = useState(value);
  const latestValueRef = useRef(value);
  const lastCommittedValueRef = useRef(value);
  const previousPropValueRef = useRef(value);
  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canSubmit = !disabled && localValue.trim().length > 0;

  useEffect(() => {
    latestValueRef.current = localValue;
  }, [localValue]);

  useEffect(() => {
    if (value === previousPropValueRef.current) {
      return;
    }

    previousPropValueRef.current = value;
    lastCommittedValueRef.current = value;
    latestValueRef.current = value;
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    if (localValue === lastCommittedValueRef.current) {
      return undefined;
    }

    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
    }

    syncTimerRef.current = setTimeout(() => {
      lastCommittedValueRef.current = latestValueRef.current;
      onChangeText(latestValueRef.current);
      syncTimerRef.current = null;
    }, 180);

    return () => {
      if (syncTimerRef.current) {
        clearTimeout(syncTimerRef.current);
        syncTimerRef.current = null;
      }
    };
  }, [localValue, onChangeText]);

  useEffect(() => () => {
    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = null;
    }

    if (latestValueRef.current !== lastCommittedValueRef.current) {
      lastCommittedValueRef.current = latestValueRef.current;
      onChangeText(latestValueRef.current);
    }
  }, [onChangeText]);

  const flushDraft = () => {
    if (latestValueRef.current === lastCommittedValueRef.current) {
      return;
    }
    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = null;
    }
    lastCommittedValueRef.current = latestValueRef.current;
    onChangeText(latestValueRef.current);
  };

  const submitDraft = () => {
    const nextValue = latestValueRef.current.trim();
    if (!nextValue || disabled) {
      return;
    }

    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
      syncTimerRef.current = null;
    }

    latestValueRef.current = '';
    lastCommittedValueRef.current = '';
    previousPropValueRef.current = '';
    setLocalValue('');
    onChangeText('');
    onSubmit(nextValue);
  };

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }] }>
      <TextInput
        testID="message-composer-input"
        value={localValue}
        onChangeText={(nextValue) => setLocalValue(nextValue)}
        onBlur={flushDraft}
        multiline
        returnKeyType="send"
        onKeyPress={(event) => {
          const nativeEvent = event.nativeEvent as { key?: string; shiftKey?: boolean };
          if (nativeEvent.key !== 'Enter' || nativeEvent.shiftKey || !canSubmit) {
            return;
          }

          (event as unknown as { preventDefault?: () => void }).preventDefault?.();
          submitDraft();
        }}
        placeholder="Posez une question sur votre coffre..."
        placeholderTextColor={theme.colors.textSubtle}
        style={[styles.input, { color: theme.colors.text, fontSize: scaleFontSize(16, scale), lineHeight: scaleLineHeight(24, scale) }]}
      />
      <View style={styles.bottomRow}>
        <View style={styles.leftActions}>
          {secondaryActionLabel && onSecondaryAction ? (
            <Pressable
              testID="message-composer-secondary-action"
              disabled={secondaryActionDisabled}
              onPress={onSecondaryAction}
              style={[styles.secondaryButton, { backgroundColor: theme.colors.secondaryButton, borderColor: theme.colors.border }, secondaryActionDisabled && styles.buttonDisabled]}
            >
              <Text style={[styles.secondaryButtonLabel, { color: theme.colors.secondaryButtonText }]}>{secondaryActionLabel}</Text>
            </Pressable>
          ) : null}
          {tertiaryActionLabel && onTertiaryAction ? (
            <Pressable
              testID="message-composer-tertiary-action"
              disabled={tertiaryActionDisabled}
              onPress={onTertiaryAction}
              style={[styles.tertiaryButton, { backgroundColor: theme.colors.warningSurface, borderColor: theme.colors.warningText }, tertiaryActionDisabled && styles.buttonDisabled]}
            >
              <Text style={[styles.tertiaryButtonLabel, { color: theme.colors.warningText }]}>{tertiaryActionLabel}</Text>
            </Pressable>
          ) : null}
          {!secondaryActionLabel && !tertiaryActionLabel ? <View style={styles.spacer} /> : null}
        </View>
        <View style={styles.rightActions}>
          {typeof withEuria === 'boolean' && onToggleWithEuria ? (
            <Pressable
              testID="message-composer-euria-toggle"
              accessibilityRole="checkbox"
              accessibilityState={{ checked: withEuria }}
              onPress={() => onToggleWithEuria(!withEuria)}
              style={styles.toggleRow}
            >
              <View
                style={[
                  styles.checkbox,
                  {
                    borderColor: withEuria ? theme.colors.primary : theme.colors.border,
                    backgroundColor: withEuria ? theme.colors.primary : theme.colors.surface,
                  },
                ]}
              >
                {withEuria ? <Text style={[styles.checkboxMark, { color: theme.colors.primaryText, fontSize: scaleFontSize(12, scale), lineHeight: scaleLineHeight(12, scale) }]}>✓</Text> : null}
              </View>
              <Text style={[styles.toggleLabel, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>Avec Euria</Text>
            </Pressable>
          ) : null}
          {withEuria && typeof withRag === 'boolean' && onToggleWithRag ? (
            <Pressable
              testID="message-composer-rag-toggle"
              accessibilityRole="checkbox"
              accessibilityState={{ checked: withRag }}
              onPress={() => onToggleWithRag(!withRag)}
              style={styles.toggleRow}
            >
              <View
                style={[
                  styles.checkbox,
                  {
                    borderColor: withRag ? theme.colors.primary : theme.colors.border,
                    backgroundColor: withRag ? theme.colors.primary : theme.colors.surface,
                  },
                ]}
              >
                {withRag ? <Text style={[styles.checkboxMark, { color: theme.colors.primaryText, fontSize: scaleFontSize(12, scale), lineHeight: scaleLineHeight(12, scale) }]}>✓</Text> : null}
              </View>
              <Text style={[styles.toggleLabel, { color: theme.colors.text, fontSize: scaleFontSize(13, scale) }]}>RAG</Text>
            </Pressable>
          ) : null}
          <Pressable testID="message-composer-submit" disabled={!canSubmit} onPress={submitDraft} style={[styles.button, { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary }, !canSubmit && styles.buttonDisabled]}>
            <Text style={[styles.buttonLabel, { color: theme.colors.primaryText, fontSize: scaleFontSize(13, scale) }]}>Envoyer</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 22,
    padding: 14,
    borderWidth: 1,
    gap: 10,
  },
  input: {
    minHeight: 56,
    fontSize: 16,
    lineHeight: 24,
    textAlignVertical: 'top',
  },
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  leftActions: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  rightActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  spacer: {
    flex: 1,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  checkbox: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxMark: {
    fontSize: 12,
    lineHeight: 12,
    fontWeight: '800',
  },
  toggleLabel: {
    fontSize: 13,
    fontWeight: '600',
  },
  secondaryButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
  },
  secondaryButtonLabel: {
    fontWeight: '700',
  },
  tertiaryButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
  },
  tertiaryButtonLabel: {
    fontWeight: '700',
  },
  button: {
    alignSelf: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonLabel: {
    fontWeight: '700',
  },
});
