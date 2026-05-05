module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      '@babel/plugin-transform-class-static-block',
      // Remplace import.meta.env par un objet statique pour éviter le crash
      // "import.meta is only valid inside a module" sur Safari / Metro bundles.
      ['babel-plugin-transform-import-meta', { module: 'ES6' }],
    ],
  };
};
