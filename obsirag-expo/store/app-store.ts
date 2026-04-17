import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

type AppStoreState = {
  hasHydrated: boolean;
  backendUrl: string;
  accessToken: string;
  useMockServer: boolean;
  activeConversationId: string | undefined;
  themeMode: 'system' | 'light' | 'dark';
  drafts: Record<string, string>;
  sourcePanels: Record<string, boolean>;
  mermaidViewer: {
    code: string;
    tone: 'light' | 'dark';
  } | null;
  setBackendUrl: (value: string) => void;
  setAccessToken: (value: string) => void;
  setUseMockServer: (value: boolean) => void;
  setActiveConversationId: (value?: string) => void;
  setThemeMode: (value: 'system' | 'light' | 'dark') => void;
  setDraft: (conversationId: string, value: string) => void;
  clearDraft: (conversationId: string) => void;
  setSourcePanelOpen: (conversationId: string, value: boolean) => void;
  openMermaidViewer: (value: { code: string; tone: 'light' | 'dark' }) => void;
  clearMermaidViewer: () => void;
  setHasHydrated: (value: boolean) => void;
};

export const useAppStore = create<AppStoreState>()(
  persist(
    (set) => ({
      hasHydrated: false,
      backendUrl: 'http://localhost:8000',
      accessToken: '',
      useMockServer: false,
      activeConversationId: undefined,
      themeMode: 'system',
      drafts: {},
      sourcePanels: {},
      mermaidViewer: null,
      setBackendUrl: (value) => set({ backendUrl: value }),
      setAccessToken: (value) => set({ accessToken: value }),
      setUseMockServer: (value) => set({ useMockServer: value }),
      setActiveConversationId: (value) => set({ activeConversationId: value }),
      setThemeMode: (value) => set({ themeMode: value }),
      setHasHydrated: (value) => set({ hasHydrated: value }),
      setDraft: (conversationId, value) =>
        set((state) => ({
          drafts: {
            ...state.drafts,
            [conversationId]: value,
          },
        })),
      clearDraft: (conversationId) =>
        set((state) => {
          const drafts = { ...state.drafts };
          delete drafts[conversationId];
          return { drafts };
        }),
      setSourcePanelOpen: (conversationId, value) =>
        set((state) => ({
          sourcePanels: {
            ...state.sourcePanels,
            [conversationId]: value,
          },
        })),
      openMermaidViewer: (value) => set({ mermaidViewer: value }),
      clearMermaidViewer: () => set({ mermaidViewer: null }),
    }),
    {
      name: 'obsirag-expo-store',
      storage: createJSONStorage(() => AsyncStorage),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
      partialize: (state) => ({
        backendUrl: state.backendUrl,
        accessToken: state.accessToken,
        useMockServer: state.useMockServer,
        ...(state.activeConversationId ? { activeConversationId: state.activeConversationId } : {}),
        themeMode: state.themeMode,
        drafts: state.drafts,
        sourcePanels: state.sourcePanels,
      }),
    },
  ),
);

export function useStoreHydrated() {
  return useAppStore((state) => state.hasHydrated);
}
