import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const ACCESS_TOKEN_KEY = 'obsirag-access-token';

function hasWebStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function saveWebToken(token: string): void {
  if (!hasWebStorage()) {
    return;
  }
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

function loadWebToken(): string {
  if (!hasWebStorage()) {
    return '';
  }
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? '';
}

function clearWebToken(): void {
  if (!hasWebStorage()) {
    return;
  }
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export async function saveAccessToken(token: string): Promise<void> {
  if (Platform.OS === 'web') {
    saveWebToken(token);
    return;
  }

  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
}

export async function loadAccessToken(): Promise<string> {
  if (Platform.OS === 'web') {
    return loadWebToken();
  }

  return (await SecureStore.getItemAsync(ACCESS_TOKEN_KEY)) ?? '';
}

export async function clearAccessToken(): Promise<void> {
  if (Platform.OS === 'web') {
    clearWebToken();
    return;
  }

  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
}
