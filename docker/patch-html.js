const fs = require('fs');
let html = fs.readFileSync('dist/index.html', 'utf8');
html = html.replace('<html lang="en">', '<html lang="fr">');
html = html.replace('shrink-to-fit=no"', 'shrink-to-fit=no, viewport-fit=cover"');
const meta = [
  '    <meta name="theme-color" content="#12161c" />',
  '    <meta name="apple-mobile-web-app-capable" content="yes" />',
  '    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />',
  '    <meta name="apple-mobile-web-app-title" content="ObsiRAG" />',
  '    <meta name="application-name" content="ObsiRAG" />',
  '    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />',
].join('\n');
html = html.replace('<title>ObsiRAG</title>', meta + '\n    <title>ObsiRAG</title>');
fs.writeFileSync('dist/index.html', html);
console.log('index.html patché');
