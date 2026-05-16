import type { ReactNode } from 'react';
import { ScrollViewStyleReset } from 'expo-router/html';

export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover" />
        <meta name="theme-color" content="#12161c" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="ObsiRAG" />
        <meta name="application-name" content="ObsiRAG" />
        <link rel="icon" type="image/png" href="/favicon.png" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <style
          dangerouslySetInnerHTML={{
            __html: `
              html, body {
                margin: 0;
                padding: 0;
                width: 100%;
                height: var(--obsirag-app-height, 100dvh);
                min-height: var(--obsirag-app-height, 100dvh);
                background: #f4f1ea;
                overscroll-behavior: none;
              }

              body {
                overflow: hidden;
                -webkit-text-size-adjust: 100%;
                -webkit-overflow-scrolling: touch;
                position: fixed;
                inset: 0;
              }

              #root,
              #__next,
              body > div:first-child {
                width: 100%;
                height: var(--obsirag-app-height, 100dvh);
                min-height: var(--obsirag-app-height, 100dvh);
              }

              html[data-obsirag-standalone='true'] [role='tablist'] {
                position: fixed !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                height: 64px !important;
                min-height: 64px !important;
                max-height: 64px !important;
                margin: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
                transform: none !important;
                z-index: 2147483646 !important;
              }

              html[data-obsirag-standalone='true'] [role='tablist'] > * {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
              }

              body[data-obsirag-booted='true'] #obsirag-preboot {
                opacity: 0;
                visibility: hidden;
                pointer-events: none;
              }

              #obsirag-preboot {
                position: fixed;
                inset: 0;
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 24px;
                background: #f4f1ea;
                color: #1f160c;
                font-family: "Segoe UI", Helvetica, Arial, sans-serif;
                transition: opacity 180ms ease, visibility 180ms ease;
              }

              #obsirag-preboot-card {
                width: 100%;
                max-width: 560px;
                border-radius: 24px;
                padding: 28px 24px;
                border: 1px solid #e2d3bd;
                background: #fffaf1;
                box-sizing: border-box;
              }

              #obsirag-preboot-eyebrow {
                margin: 0 0 12px;
                color: #8a562b;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
              }

              #obsirag-preboot-title {
                margin: 0 0 12px;
                font-size: 28px;
                font-weight: 800;
                line-height: 1.2;
              }

              #obsirag-preboot-copy {
                margin: 0;
                color: #5f4f3c;
                font-size: 15px;
                line-height: 1.5;
              }
            `,
          }}
        />
        <ScrollViewStyleReset />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function () {
                var tabObserver;
                function applyAppHeight() {
                  var vv = window.visualViewport;
                  var height = Math.round(Math.max(
                    window.innerHeight || 0,
                    vv && vv.height ? vv.height : 0,
                    document.documentElement.clientHeight || 0
                  ));
                  document.documentElement.style.setProperty('--obsirag-app-height', height + 'px');
                }
                function patchTabBar(standalone) {
                  var tablist = document.querySelector('[role="tablist"]');
                  if (!tablist) {
                    return;
                  }
                  if (!standalone) {
                    tablist.style.position = '';
                    tablist.style.left = '';
                    tablist.style.right = '';
                    tablist.style.bottom = '';
                    tablist.style.height = '';
                    tablist.style.minHeight = '';
                    tablist.style.maxHeight = '';
                    tablist.style.paddingTop = '';
                    tablist.style.paddingBottom = '';
                    tablist.style.marginTop = '';
                    tablist.style.marginBottom = '';
                    tablist.style.transform = '';
                    tablist.style.zIndex = '';
                    return;
                  }
                  tablist.style.position = 'fixed';
                  tablist.style.left = '0';
                  tablist.style.right = '0';
                  tablist.style.bottom = '0';
                  tablist.style.height = '64px';
                  tablist.style.minHeight = '64px';
                  tablist.style.maxHeight = '64px';
                  tablist.style.paddingTop = '0';
                  tablist.style.paddingBottom = '0';
                  tablist.style.marginTop = '0';
                  tablist.style.marginBottom = '0';
                  tablist.style.transform = 'none';
                  tablist.style.zIndex = '2147483646';
                }
                function ensureTabObserver(standalone) {
                  if (!standalone) {
                    if (tabObserver) {
                      tabObserver.disconnect();
                      tabObserver = undefined;
                    }
                    return;
                  }
                  if (tabObserver || typeof MutationObserver === 'undefined') {
                    return;
                  }
                  tabObserver = new MutationObserver(function () {
                    patchTabBar(true);
                  });
                  tabObserver.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
                }
                function applyStandaloneFlag() {
                  var standaloneByDisplayMode = window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
                  var standaloneByNavigator = window.navigator && window.navigator.standalone === true;
                  var standalone = !!(standaloneByDisplayMode || standaloneByNavigator);
                  document.documentElement.setAttribute('data-obsirag-standalone', standalone ? 'true' : 'false');
                  patchTabBar(standalone);
                  ensureTabObserver(standalone);
                }
                applyAppHeight();
                if (document.readyState === 'loading') {
                  document.addEventListener('DOMContentLoaded', function () {
                    applyStandaloneFlag();
                    applyAppHeight();
                  }, { once: true });
                } else {
                  applyStandaloneFlag();
                }
                requestAnimationFrame(function () {
                  applyStandaloneFlag();
                  applyAppHeight();
                });
                window.addEventListener('resize', applyAppHeight, { passive: true });
                window.addEventListener('orientationchange', applyAppHeight, { passive: true });
                if (window.visualViewport) {
                  window.visualViewport.addEventListener('resize', applyAppHeight, { passive: true });
                }
                if (window.matchMedia) {
                  var media = window.matchMedia('(display-mode: standalone)');
                  if (media && media.addEventListener) {
                    media.addEventListener('change', applyStandaloneFlag);
                  }
                }
              })();
            `,
          }}
        />
      </head>
      <body>
        <div id="obsirag-preboot" aria-live="polite">
          <div id="obsirag-preboot-card">
            <p id="obsirag-preboot-eyebrow">ObsiRAG</p>
            <h1 id="obsirag-preboot-title">Demarrage en cours</h1>
            <p id="obsirag-preboot-copy">
              Chargement de l&apos;application web. Si cet ecran reste affiche, un probleme de bootstrap
              JavaScript bloque le premier rendu.
            </p>
          </div>
        </div>
        {children}
      </body>
    </html>
  );
}
