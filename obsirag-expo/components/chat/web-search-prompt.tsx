import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type WebSearchPromptProps = {
  value: string;
  onChangeText: (value: string) => void;
  onSubmit: () => void;
  onUseInChat?: () => void;
  disabled?: boolean;
};

export function WebSearchPrompt({ value, onChangeText, onSubmit, onUseInChat, disabled }: WebSearchPromptProps) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Recherche sur le web</Text>
      <Text style={styles.caption}>Ajustez la requete avant de lancer une recherche sur le web.</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder="Ex. Ada Lovelace biographie resume"
        placeholderTextColor="#7b8b99"
        style={styles.input}
      />
      <View style={styles.actionsRow}>
        <Pressable style={[styles.button, disabled && styles.buttonDisabled]} disabled={disabled || !value.trim()} onPress={onSubmit}>
          <Text style={styles.buttonLabel}>Lancer la recherche</Text>
        </Pressable>
        {onUseInChat ? (
          <Pressable style={styles.secondaryButton} disabled={!value.trim()} onPress={onUseInChat}>
            <Text style={styles.secondaryButtonLabel}>Utiliser dans le chat</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 18,
    backgroundColor: '#242424',
    borderWidth: 1,
    borderColor: '#353535',
    padding: 14,
    gap: 10,
  },
  title: {
    color: '#f1f1f1',
    fontWeight: '800',
  },
  caption: {
    color: '#a8a8a8',
    lineHeight: 19,
  },
  input: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3f3f3f',
    backgroundColor: '#1b1b1b',
    color: '#f3f3f3',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#f2f2f2',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonLabel: {
    color: '#151515',
    fontWeight: '700',
  },
  actionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  secondaryButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#4a4a4a',
    backgroundColor: '#1b1b1b',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  secondaryButtonLabel: {
    color: '#e6e6e6',
    fontWeight: '700',
  },
});