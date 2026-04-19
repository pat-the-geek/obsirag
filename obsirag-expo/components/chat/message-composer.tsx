import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';

type MessageComposerProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
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
  secondaryActionLabel,
  onSecondaryAction,
  secondaryActionDisabled,
  tertiaryActionLabel,
  onTertiaryAction,
  tertiaryActionDisabled,
}: MessageComposerProps) {
  const theme = useAppTheme();
  const canSubmit = !disabled && value.trim().length > 0;

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }] }>
      <TextInput
        testID="message-composer-input"
        value={value}
        onChangeText={onChangeText}
        multiline
        returnKeyType="send"
        onKeyPress={(event) => {
          const nativeEvent = event.nativeEvent as { key?: string; shiftKey?: boolean };
          if (nativeEvent.key !== 'Enter' || nativeEvent.shiftKey || !canSubmit) {
            return;
          }

          (event as unknown as { preventDefault?: () => void }).preventDefault?.();
          onSubmit();
        }}
        placeholder="Posez une question sur votre coffre..."
        placeholderTextColor={theme.colors.textSubtle}
        style={[styles.input, { color: theme.colors.text }]}
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
        <Pressable testID="message-composer-submit" disabled={!canSubmit} onPress={onSubmit} style={[styles.button, { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary }, !canSubmit && styles.buttonDisabled]}>
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
