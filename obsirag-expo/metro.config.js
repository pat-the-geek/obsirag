const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const config = getDefaultConfig(__dirname);

const parserEntry = path.resolve(__dirname, 'node_modules/@mermaid-js/parser/dist/mermaid-parser.core.mjs');

const previousResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === '@mermaid-js/parser') {
    return context.resolveRequest(context, parserEntry, platform);
  }

  if (previousResolveRequest) {
    return previousResolveRequest(context, moduleName, platform);
  }

  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;