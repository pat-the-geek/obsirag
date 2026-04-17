import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type MessageComposerProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
};

export function MessageComposer({ value, onChangeText, onSubmit, disabled }: MessageComposerProps) {
  return (
    <View style={styles.container}>
      <View style={styles.topRow}>
        <View style={styles.addButton}>
          <Text style={styles.addButtonLabel}>+</Text>
        </View>
        <Text style={styles.hint}>Repondre...</Text>
      </View>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        multiline
        placeholder="Posez une question sur votre coffre..."
        placeholderTextColor="#8a7760"
        style={styles.input}
      />
      <View style={styles.bottomRow}>
        <Text style={styles.modelLabel}>ObsiRAG live</Text>
        <Pressable disabled={disabled || !value.trim()} onPress={onSubmit} style={[styles.button, disabled && styles.buttonDisabled]}>
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
    borderColor: '#3a3a3a',
    gap: 10,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  addButton: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#575757',
  },
  addButtonLabel: {
    color: '#d7d7d7',
    fontSize: 16,
    lineHeight: 18,
  },
  hint: {
    color: '#9f9f9f',
    fontSize: 14,
  },
  input: {
    minHeight: 72,
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
  modelLabel: {
    color: '#a7a7a7',
    fontSize: 12,
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
