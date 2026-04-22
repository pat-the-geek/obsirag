import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { PersistStorage, StorageValue } from 'zustand/middleware';

import { normalizeBackendUrlInput } from '../features/auth/backend-url';
import type { FontSizeMode, ThemeMode } from '../theme/app-theme';

const DEFAULT_BACKEND_URL = normalizeBackendUrlInput(process.env.EXPO_PUBLIC_DEFAULT_BACKEND_URL ?? process.env.API_PUBLIC_BASE_URL ?? '') || 'http://localhost:8000';

function logStorageFailure(operation: 'read' | 'write' | 'delete', error: unknown): void {
  console.error(`App store persistence ${operation} failed. Falling back to in-memory state.`, error);
}

function migrateBackendUrl(value: unknown): string {
  if (typeof value !== 'string') {
    return DEFAULT_BACKEND_URL;
  }

  const trimmedValue = normalizeBackendUrlInput(value);
  if (trimmedValue === 'http://localhost:8501') {
    return DEFAULT_BACKEND_URL;
  }

  if (trimmedValue === 'http://127.0.0.1:8501') {
    return 'http://127.0.0.1:8000';
  }

  return trimmedValue || DEFAULT_BACKEND_URL;
}

function coerceThemeMode(value: unknown): ThemeMode {
  return value === 'light' || value === 'dark' || value === 'quiet' || value === 'abyss' || value === 'system'
    ? value
    : 'system';
}

function coerceFontSizeMode(value: unknown): FontSizeMode {
  return value === 'small' || value === 'medium' || value === 'large' || value === 'xlarge'
    ? value
    : 'medium';
}

function coerceStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return Object.fromEntries(Object.entries(value).filter(([, entryValue]) => typeof entryValue === 'string'));
}

function coerceBooleanRecord(value: unknown): Record<string, boolean> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  return Object.fromEntries(Object.entries(value).filter(([, entryValue]) => typeof entryValue === 'boolean'));
}

type AppStoreState = {
  hasHydrated: boolean;
  backendUrl: string;
  accessToken: string;
  useMockServer: boolean;
  useEuriaForConversation: boolean;
  useRagForConversation: boolean;
  activeConversationId: string | undefined;
  themeMode: 'system' | 'light' | 'dark' | 'quiet' | 'abyss';
  fontSizeMode: 'small' | 'medium' | 'large' | 'xlarge';
  drafts: Record<string, string>;
  sourcePanels: Record<string, boolean>;
  mermaidViewer: {
    code: string;
    tone: 'light' | 'dark';
  } | null;
  setBackendUrl: (value: string) => void;
  setAccessToken: (value: string) => void;
  setUseMockServer: (value: boolean) => void;
  setUseEuriaForConversation: (value: boolean) => void;
  setUseRagForConversation: (value: boolean) => void;
  setActiveConversationId: (value?: string) => void;
  setThemeMode: (value: 'system' | 'light' | 'dark' | 'quiet' | 'abyss') => void;
  setFontSizeMode: (value: 'small' | 'medium' | 'large' | 'xlarge') => void;
  increaseFontSize: () => void;
  decreaseFontSize: () => void;
  setDraft: (conversationId: string, value: string) => void;
  clearDraft: (conversationId: string) => void;
  setSourcePanelOpen: (conversationId: string, value: boolean) => void;
  openMermaidViewer: (value: { code: string; tone: 'light' | 'dark' }) => void;
  clearMermaidViewer: () => void;
  setHasHydrated: (value: boolean) => void;
};

function sanitizePersistedState(state: unknown): Partial<AppStoreState> {
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    return {};
  }

  const candidate = state as Partial<AppStoreState>;

  return {
    backendUrl: migrateBackendUrl(candidate.backendUrl),
    accessToken: typeof candidate.accessToken === 'string' ? candidate.accessToken : '',
    useMockServer: typeof candidate.useMockServer === 'boolean' ? candidate.useMockServer : false,
    useEuriaForConversation: typeof candidate.useEuriaForConversation === 'boolean' ? candidate.useEuriaForConversation : false,
    useRagForConversation: typeof candidate.useRagForConversation === 'boolean' ? candidate.useRagForConversation : true,
    activeConversationId: typeof candidate.activeConversationId === 'string' ? candidate.activeConversationId : undefined,
    themeMode: coerceThemeMode(candidate.themeMode),
    fontSizeMode: coerceFontSizeMode(candidate.fontSizeMode),
    drafts: coerceStringRecord(candidate.drafts),
    sourcePanels: coerceBooleanRecord(candidate.sourcePanels),
  };
}

const safeAppStoreStorage: PersistStorage<Partial<AppStoreState>> = {
  getItem: async (name) => {
    let rawValue: string | null;

    try {
      rawValue = await AsyncStorage.getItem(name);
    } catch (error) {
      logStorageFailure('read', error);
      return null;
    }

    if (!rawValue) {
      return null;
    }

    try {
      const parsedValue = JSON.parse(rawValue) as StorageValue<Partial<AppStoreState>>;

      return {
        state: sanitizePersistedState(parsedValue?.state),
        version: typeof parsedValue?.version === 'number' ? parsedValue.version : 0,
      };
    } catch (error) {
      try {
        await AsyncStorage.removeItem(name);
      } catch (removeError) {
        logStorageFailure('delete', removeError);
      }

      logStorageFailure('read', error);
      return null;
    }
  },
  setItem: async (name, value) => {
    try {
      await AsyncStorage.setItem(name, JSON.stringify(value));
    } catch (error) {
      logStorageFailure('write', error);
    }
  },
  removeItem: async (name) => {
    try {
      await AsyncStorage.removeItem(name);
    } catch (error) {
      logStorageFailure('delete', error);
    }
  },
};

export const useAppStore = create<AppStoreState>()(
  persist(
    (set) => ({
      hasHydrated: false,
      backendUrl: DEFAULT_BACKEND_URL,
      accessToken: '',
      useMockServer: false,
      useEuriaForConversation: false,
      useRagForConversation: true,
      activeConversationId: undefined,
      themeMode: 'system',
      fontSizeMode: 'medium',
      drafts: {},
      sourcePanels: {},
      mermaidViewer: null,
      setBackendUrl: (value) => set({ backendUrl: normalizeBackendUrlInput(value) }),
      setAccessToken: (value) => set({ accessToken: value }),
      setUseMockServer: (value) => set({ useMockServer: value }),
      setUseEuriaForConversation: (value) => set({ useEuriaForConversation: value }),
      setUseRagForConversation: (value) => set({ useRagForConversation: value }),
      setActiveConversationId: (value) => set({ activeConversationId: value }),
      setThemeMode: (value) => set({ themeMode: value }),
      setFontSizeMode: (value) => set({ fontSizeMode: value }),
      increaseFontSize: () => set((state) => ({
        fontSizeMode:
          state.fontSizeMode === 'small'
            ? 'medium'
            : state.fontSizeMode === 'medium'
              ? 'large'
              : state.fontSizeMode === 'large'
                ? 'xlarge'
                : 'xlarge',
      })),
      decreaseFontSize: () => set((state) => ({
        fontSizeMode:
          state.fontSizeMode === 'xlarge'
            ? 'large'
            : state.fontSizeMode === 'large'
              ? 'medium'
              : state.fontSizeMode === 'medium'
                ? 'small'
                : 'small',
      })),
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
      version: 6,
      storage: safeAppStoreStorage,
      migrate: (persistedState) => {
        return sanitizePersistedState(persistedState);
      },
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
      partialize: (state) => ({
        backendUrl: state.backendUrl,
        accessToken: state.accessToken,
        useMockServer: state.useMockServer,
        useEuriaForConversation: state.useEuriaForConversation,
        useRagForConversation: state.useRagForConversation,
        ...(state.activeConversationId ? { activeConversationId: state.activeConversationId } : {}),
        themeMode: state.themeMode,
        fontSizeMode: state.fontSizeMode,
        drafts: state.drafts,
        sourcePanels: state.sourcePanels,
      }),
    },
  ),
);

export function useStoreHydrated() {
  return useAppStore((state) => state.hasHydrated);
}
