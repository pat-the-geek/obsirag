import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const scriptDirectory = resolve(fileURLToPath(new URL('.', import.meta.url)));
const projectRoot = resolve(scriptDirectory, '..');
const distDirectory = resolve(projectRoot, 'dist');
const indexHtmlPath = resolve(distDirectory, 'index.html');
const host = '127.0.0.1';

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpg': 'image/jpeg',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function runCommand(command, args, options = {}) {
  return new Promise((resolveCommand, rejectCommand) => {
    const child = spawn(command, args, {
      cwd: projectRoot,
      stdio: 'inherit',
      env: process.env,
      shell: false,
      ...options,
    });

    child.on('error', rejectCommand);
    child.on('exit', (code, signal) => {
      if (code === 0) {
        resolveCommand();
        return;
      }

      rejectCommand(new Error(`${command} ${args.join(' ')} failed with code ${code ?? 'unknown'}${signal ? ` (signal: ${signal})` : ''}`));
    });
  });
}

function contentTypeFor(filePath) {
  return mimeTypes[extname(filePath).toLowerCase()] ?? 'application/octet-stream';
}

function resolveRequestPath(urlPathname) {
  const decodedPath = decodeURIComponent(urlPathname.split('?')[0]);
  const normalizedPath = normalize(decodedPath).replace(/^([.][.][/\\])+/, '');
  const requestedPath = normalizedPath === '/' ? '/index.html' : normalizedPath;
  return join(distDirectory, requestedPath);
}

async function withStaticServer(callback) {
  const server = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? '/', `http://${host}`);
    const candidatePath = resolveRequestPath(requestUrl.pathname);
    const servePath = existsSync(candidatePath) ? candidatePath : indexHtmlPath;

    try {
      const body = readFileSync(servePath);
      response.writeHead(200, {
        'Content-Type': contentTypeFor(servePath),
        'Cache-Control': 'no-store',
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end(error instanceof Error ? error.message : String(error));
    }
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, host, () => {
      server.off('error', rejectListen);
      resolveListen();
    });
  });

  const address = server.address();
  assert(address && typeof address === 'object' && typeof address.port === 'number');
  const baseUrl = `http://${host}:${address.port}`;

  try {
    return await callback(baseUrl);
  } finally {
    await new Promise((resolveClose, rejectClose) => {
      server.close((error) => {
        if (error) {
          rejectClose(error);
          return;
        }

        resolveClose();
      });
    });
  }
}

async function assertRootRendered(baseUrl) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const pageErrors = [];
  const consoleErrors = [];

  page.on('pageerror', (error) => {
    pageErrors.push(error instanceof Error ? error.message : String(error));
  });

  page.on('console', (message) => {
    if (message.type() !== 'error') {
      return;
    }

    consoleErrors.push(message.text());
  });

  try {
    const response = await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    assert(response, 'The exported page did not return an HTTP response.');
    assert.equal(response.status(), 200, `Expected 200 from exported web app, received ${response.status()}.`);

    await page.waitForSelector('#root', { state: 'attached', timeout: 15000 });
    await page.waitForFunction(
      () => {
        const root = document.querySelector('#root');
        if (!root) {
          return false;
        }

        if (root.children.length > 0) {
          return true;
        }

        const textContent = (root.textContent || '').replace(/\s+/g, ' ').trim();
        return textContent.length > 0;
      },
      { timeout: 15000 },
    );

    await page.waitForFunction(
      () => {
        const shell = document.querySelector('#obsirag-preboot');
        if (!shell) {
          return true;
        }

        const style = window.getComputedStyle(shell);
        return document.body?.getAttribute('data-obsirag-booted') === 'true'
          && style.visibility === 'hidden'
          && style.pointerEvents === 'none'
          && style.opacity === '0';
      },
      { timeout: 10000 },
    );

    assert.equal(pageErrors.length, 0, `Browser page errors detected during bootstrap: ${pageErrors.join(' | ')}`);
    assert.equal(consoleErrors.length, 0, `Browser console errors detected during bootstrap: ${consoleErrors.join(' | ')}`);

    const rootSnapshot = await page.locator('#root').evaluate((element) => ({
      childCount: element.children.length,
      text: (element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200),
    }));

    const prebootState = await page.evaluate(() => {
      const shell = document.querySelector('#obsirag-preboot');
      if (!shell) {
        return { present: false, hidden: true };
      }

      const style = window.getComputedStyle(shell);
      return {
        present: true,
        hidden: style.visibility === 'hidden' && style.pointerEvents === 'none' && style.opacity === '0',
      };
    });

    assert(rootSnapshot.childCount > 0 || rootSnapshot.text.length > 0, 'The exported page mounted #root but did not render useful content.');
    assert.equal(prebootState.hidden, true, 'The exported page rendered #root but the preboot shell did not hide.');
    return {
      ...rootSnapshot,
      prebootState,
    };
  } finally {
    await page.close();
    await browser.close();
  }
}

async function main() {
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  await runCommand(npmCommand, ['run', 'web:export']);

  assert(existsSync(indexHtmlPath), `Missing exported HTML shell at ${indexHtmlPath}.`);

  const rootSnapshot = await withStaticServer((baseUrl) => assertRootRendered(baseUrl));

  console.log('Smoke web export OK');
  console.log(`Rendered root snapshot: ${JSON.stringify(rootSnapshot)}`);
}

main().catch((error) => {
  console.error('Smoke web export failed');
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});