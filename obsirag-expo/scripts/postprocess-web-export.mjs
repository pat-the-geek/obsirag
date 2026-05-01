#!/usr/bin/env node
import { access, readFile, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { resolve } from 'node:path';

const distIndex = resolve(process.cwd(), 'dist', 'index.html');

try {
  await access(distIndex, constants.R_OK);
  const html = await readFile(distIndex, 'utf8');
  const patchedHtml = html.replace(
    /<script\s+src="([^\"]+\/entry-[^\"]+\.js)"\s+defer><\/script>/,
    '<script type="module" src="$1"></script>',
  );

  if (patchedHtml !== html) {
    await writeFile(distIndex, patchedHtml, 'utf8');
    console.log('Postprocess web export: script tag converted to module in dist/index.html.');
  } else {
    console.log('Postprocess web export: no script tag rewrite needed.');
  }
} catch {
  console.error('Postprocess web export: dist/index.html is missing.');
  process.exitCode = 1;
}
