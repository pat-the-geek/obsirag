import { useEffect, useRef } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';

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
  withEuria = false,
  withRag = false,
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
  const latestValueRef = useRef(value);

  useEffect(() => {
    latestValueRef.current = value;
  }, [value]);

  const handleChangeText = (nextValue: string) => {
    latestValueRef.current = nextValue;
    onChangeText(nextValue);
  };

  const submitValue = () => {
    const nextValue = latestValueRef.current;
    if (disabled || nextValue.trim().length === 0) {
      return;
    }
    onSubmit(nextValue);
  };

  const canSubmit = !disabled && latestValueRef.current.trim().length > 0;

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }] }>
      <TextInput
        testID="message-composer-input"
        value={value}
        onChangeText={handleChangeText}
        multiline
        returnKeyType="send"
        onKeyPress={(event) => {
          const nativeEvent = event.nativeEvent as { key?: string; shiftKey?: boolean };
          if (nativeEvent.key !== 'Enter' || nativeEvent.shiftKey || !canSubmit) {
            return;
          }

          (event as unknown as { preventDefault?: () => void }).preventDefault?.();
          submitValue();
        }}
        placeholder="Posez une question sur votre coffre..."
        placeholderTextColor={theme.colors.textSubtle}
        style={[styles.input, { color: theme.colors.text }]}
      />
      <View style={styles.bottomRow}>
        <View style={styles.leftActions}>
          {onToggleWithEuria ? (
            <Pressable
              testID="message-composer-euria-toggle"
              disabled={disabled}
              onPress={() => onToggleWithEuria(!withEuria)}
              style={[
                styles.toggleButton,
                {
                  backgroundColor: withEuria ? theme.colors.primaryMuted : theme.colors.surfaceMuted,
                  borderColor: withEuria ? theme.colors.primary : theme.colors.border,
                },
                disabled && styles.buttonDisabled,
              ]}
            >
              <Text style={[styles.toggleLabel, { color: withEuria ? theme.colors.primaryText : theme.colors.textMuted }]}>
                {withEuria ? 'Euria ON' : 'Euria OFF'}
              </Text>
            </Pressable>
          ) : null}
          {withEuria && onToggleWithRag ? (
            <Pressable
              testID="message-composer-rag-toggle"
              disabled={disabled}
              onPress={() => onToggleWithRag(!withRag)}
              style={[
                styles.toggleButton,
                {
                  backgroundColor: withRag ? theme.colors.successSurface : theme.colors.surfaceMuted,
                  borderColor: withRag ? theme.colors.successText : theme.colors.border,
                },
                disabled && styles.buttonDisabled,
              ]}
            >
              <Text style={[styles.toggleLabel, { color: withRag ? theme.colors.successText : theme.colors.textMuted }]}>
                {withRag ? 'RAG ON' : 'RAG OFF'}
              </Text>
            </Pressable>
          ) : null}
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
        <Pressable testID="message-composer-submit" disabled={!canSubmit} onPress={submitValue} style={[styles.button, { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary }, !canSubmit && styles.buttonDisabled]}>
          <Text style={[styles.buttonLabel, { color: theme.colors.primaryText }]}>Envoyer</Text>
        </Pressable>
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
  spacer: {
    flex: 1,
  },
  toggleButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
  },
  toggleLabel: {
    fontWeight: '700',
    fontSize: 12,
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
