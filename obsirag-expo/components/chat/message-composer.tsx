import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type MessageComposerProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  secondaryActionDisabled?: boolean;
};

export function MessageComposer({
  value,
  onChangeText,
  onSubmit,
  disabled,
  secondaryActionLabel,
  onSecondaryAction,
  secondaryActionDisabled,
}: MessageComposerProps) {
  const canSubmit = !disabled && value.trim().length > 0;

  return (
    <View style={styles.container}>
      <TextInput
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
        placeholderTextColor="#8a7760"
        style={styles.input}
      />
      <View style={styles.bottomRow}>
        {secondaryActionLabel && onSecondaryAction ? (
          <Pressable
            testID="message-composer-secondary-action"
            disabled={secondaryActionDisabled}
            onPress={onSecondaryAction}
            style={[styles.secondaryButton, secondaryActionDisabled && styles.buttonDisabled]}
          >
            <Text style={styles.secondaryButtonLabel}>{secondaryActionLabel}</Text>
          </Pressable>
        ) : (
          <View style={styles.spacer} />
        )}
        <Pressable disabled={!canSubmit} onPress={onSubmit} style={[styles.button, !canSubmit && styles.buttonDisabled]}>
          <Text style={styles.buttonLabel}>Envoyer</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 22,
    padding: 14,
    backgroundColor: '#2b2b2b',
    borderWidth: 1,
    borderColor: '#2b2b2b',
    gap: 10,
  },
  input: {
    minHeight: 56,
    color: '#f2f2f2',
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
  spacer: {
    flex: 1,
  },
  secondaryButton: {
    alignSelf: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: '#353535',
    borderWidth: 1,
    borderColor: '#4a4a4a',
  },
  secondaryButtonLabel: {
    color: '#f0f0f0',
    fontWeight: '700',
  },
  button: {
    alignSelf: 'flex-end',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: '#151515',
    borderWidth: 1,
    borderColor: '#414141',
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonLabel: {
    color: '#f5f5f5',
    fontWeight: '700',
  },
});
