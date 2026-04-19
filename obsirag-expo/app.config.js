const baseConfig = require('./app.json');

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
  const baseExpoConfig = baseConfig.expo ?? {};
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