const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Zustand expose une version ESM (.mjs) via la condition "import" des package exports.
// Cette version utilise import.meta.env qui est invalide dans les bundles Metro/CommonJS
// et fait crasher Safari avec "import.meta is only valid inside a module".
// On retire "import" des conditions résolues pour forcer la version CJS (.js).
config.resolver = config.resolver || {};
config.resolver.unstable_conditionNames = ['require', 'default', 'react-native'];

module.exports = config;