import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const ACCESS_TOKEN_KEY = 'obsirag-access-token';

const isWeb = Platform.OS === 'web';

function logSecureSessionFailure(operation: 'read' | 'write' | 'delete', error: unknown): void {
  console.error(`Secure session ${operation} failed. Continuing without persisted token.`, error);
}

export async function saveAccessToken(token: string): Promise<void> {
  if (isWeb) {
    return;
  }

  try {
    await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
  } catch (error) {
    logSecureSessionFailure('write', error);
  }
}

export async function loadAccessToken(): Promise<string> {
  if (isWeb) {
    return '';
  }

  try {
    return (await SecureStore.getItemAsync(ACCESS_TOKEN_KEY)) ?? '';
  } catch (error) {
    logSecureSessionFailure('read', error);
    return '';
  }
}

export async function clearAccessToken(): Promise<void> {
  if (isWeb) {
    return;
  }

  try {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  } catch (error) {
    logSecureSessionFailure('delete', error);
  }
}
