const baseExpoConfig = {
  name: 'ObsiRAG',
  slug: 'obsirag-expo',
  scheme: 'obsirag',
  version: '0.1.0',
  icon: './assets/app-icon.png',
  orientation: 'portrait',
  userInterfaceStyle: 'automatic',
  assetBundlePatterns: ['**/*'],
  plugins: ['expo-router', 'expo-secure-store', 'expo-asset', 'expo-font'],
  experiments: {
    typedRoutes: false,
  },
  web: {
    bundler: 'metro',
    favicon: './assets/app-icon.png',
  },
  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.obsirag.mobile',
    buildNumber: '1',
  },
};

function normalizeUrl(value) {
  if (!value || typeof value !== 'string') {
    return undefined;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  return trimmed.replace(/\/$/, '');
}

module.exports = () => {
  const configuredBackendUrl = normalizeUrl(process.env.EXPO_PUBLIC_DEFAULT_BACKEND_URL)
    ?? normalizeUrl(process.env.API_PUBLIC_BASE_URL);
  const iosBundleIdentifier = process.env.OBSIRAG_IOS_BUNDLE_IDENTIFIER?.trim() || baseExpoConfig.ios?.bundleIdentifier || 'com.obsirag.mobile';
  const iosBuildNumber = process.env.OBSIRAG_IOS_BUILD_NUMBER?.trim() || baseExpoConfig.ios?.buildNumber || '1';

  return {
    ...baseExpoConfig,
    extra: {
      ...(baseExpoConfig.extra ?? {}),
      ...(configuredBackendUrl ? { defaultBackendUrl: configuredBackendUrl } : {}),
    },
    ios: {
      ...(baseExpoConfig.ios ?? {}),
      bundleIdentifier: iosBundleIdentifier,
      buildNumber: iosBuildNumber,
    },
  };
};