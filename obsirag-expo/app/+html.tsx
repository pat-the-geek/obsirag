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
                background: #f4f1ea;
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
