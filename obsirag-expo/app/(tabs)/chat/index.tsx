import { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput } from 'react-native';
import { useRouter } from 'expo-router';

import { ConversationListItem } from '../../../components/chat/conversation-list-item';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useConversations, useCreateConversation, useDeleteConversation } from '../../../features/chat/use-chat';
import { useAppStore } from '../../../store/app-store';

export default function ConversationsScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const setActiveConversationId = useAppStore((state) => state.setActiveConversationId);
  const clearDraft = useAppStore((state) => state.clearDraft);
  const { data, isLoading, isRefetching, refetch } = useConversations();
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();

  const filteredData = useMemo(() => {
    const searchValue = search.trim().toLowerCase();
    if (!searchValue) {
      return data ?? [];
    }
    return (data ?? []).filter(
      (item) => item.title.toLowerCase().includes(searchValue) || item.preview.toLowerCase().includes(searchValue),
    );
  }, [data, search]);

  const openConversation = (conversationId: string) => {
    setActiveConversationId(conversationId);
    router.push(`/(tabs)/chat/${conversationId}`);
  };

  const onCreate = async () => {
    setActiveConversationId(undefined);
    const created = await createConversation.mutateAsync();
    clearDraft(created.id);
    openConversation(created.id);
  };

  const onDelete = (conversationId: string) => {
    Alert.alert('Supprimer la conversation', 'Cette suppression affectera le stockage backend de ce fil.', [
      { text: 'Annuler', style: 'cancel' },
      {
        text: 'Supprimer',
        style: 'destructive',
        onPress: () => {
          void deleteConversation.mutateAsync(conversationId);
        },
      },
    ]);
  };

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <SectionCard title="Conversations" subtitle="Fils persistants, brouillons locaux et reprise multi-plateforme.">
        <Pressable onPress={onCreate} style={styles.button}>
          <Text style={styles.buttonText}>Nouveau fil</Text>
        </Pressable>
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Rechercher une conversation"
          placeholderTextColor="#8a7760"
          style={styles.input}
        />
        {isLoading ? <ActivityIndicator /> : null}
        {filteredData.map((item) => (
          <ConversationListItem
            key={item.id}
            item={item}
            onPress={() => openConversation(item.id)}
            onDelete={() => onDelete(item.id)}
          />
        ))}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  buttonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
  input: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
});
