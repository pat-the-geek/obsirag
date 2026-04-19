import { useMemo, useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { WebView } from 'react-native-webview';

import { normalizeMermaidCode } from './mermaid-code';
import { buildAppTheme, useAppTheme } from '../../theme/app-theme';

type MermaidDiagramProps = {
  code: string;
  tone?: 'light' | 'dark';
  fullscreen?: boolean;
};

export function MermaidDiagram({ code, tone = 'light', fullscreen = false }: MermaidDiagramProps) {
  const activeTheme = useAppTheme();
  const theme = activeTheme.resolvedMode === tone ? activeTheme : buildAppTheme(tone === 'dark' ? 'dark' : 'light');
  const { height: viewportHeight } = useWindowDimensions();
  const [isCodeOpen, setIsCodeOpen] = useState(false);
  const sourceCode = useMemo(() => code.trim().replace(/\r\n/g, '\n'), [code]);
  const trimmedCode = useMemo(() => normalizeMermaidCode(sourceCode), [sourceCode]);
  const codeLineCount = useMemo(() => trimmedCode.split('\n').filter(Boolean).length, [trimmedCode]);
  const height = useMemo(() => estimateMermaidHeight(trimmedCode, fullscreen ? viewportHeight : undefined), [fullscreen, trimmedCode, viewportHeight]);
  const html = useMemo(() => buildMermaidHtml(trimmedCode, theme, { fullscreen }), [fullscreen, theme, trimmedCode]);

  return (
    <View style={[styles.card, fullscreen ? styles.cardFullscreen : null, { backgroundColor: theme.colors.mediaSurface, borderColor: theme.colors.border }]}>
      <View style={styles.headerRow}>
        <Text style={[styles.title, { color: theme.colors.text }]}>Diagramme Mermaid</Text>
        <View style={styles.headerActions}>
          {!fullscreen ? (
            <Pressable
              onPress={() => {
                require('../../store/app-store').useAppStore.getState().openMermaidViewer({ code: trimmedCode, tone });
                require('expo-router').router.push('/mermaid-viewer');
              }}
            >
              <Text style={[styles.link, { color: theme.colors.link }]}>Plein ecran</Text>
            </Pressable>
          ) : null}
          <Pressable onPress={() => { void Linking.openURL(buildMermaidLiveUrl(trimmedCode)); }}>
            <Text style={[styles.link, { color: theme.colors.link }]}>Live</Text>
          </Pressable>
        </View>
      </View>
      {Platform.OS === 'web' ? (
        <iframe
          srcDoc={html}
          data-testid="markdown-mermaid-diagram"
          style={{ width: '100%', height, border: 'none', backgroundColor: theme.colors.mediaCanvas }}
          sandbox="allow-scripts allow-same-origin"
          title="Diagramme Mermaid"
        />
      ) : (
        <WebView
          originWhitelist={['*']}
          source={{ html }}
          style={[styles.webview, { height, backgroundColor: theme.colors.mediaCanvas }]}
          scrollEnabled={false}
          nestedScrollEnabled={false}
        />
      )}
      <Text style={[styles.caption, { color: theme.colors.textMuted }]}>
        {fullscreen
          ? 'Utilisez les boutons de zoom ou faites glisser le diagramme pour le deplacer.'
          : Platform.OS === 'web'
            ? 'Un mode plein ecran permet de zoomer et de deplacer le diagramme.'
            : 'Touchez Plein ecran pour zoomer et deplacer le diagramme.'}
      </Text>
      <View style={[styles.codePanel, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
        <Pressable testID="mermaid-code-toggle" style={styles.codePanelHeader} onPress={() => setIsCodeOpen((current) => !current)}>
          <View style={styles.codePanelHeaderCopy}>
            <Text style={[styles.codePanelTitle, { color: theme.colors.text }]}>Code Mermaid</Text>
            <Text style={[styles.codePanelCaption, { color: theme.colors.textMuted }]}>
              {codeLineCount} ligne{codeLineCount > 1 ? 's' : ''}
            </Text>
          </View>
          <Text style={[styles.link, { color: theme.colors.link }]}>{isCodeOpen ? 'Masquer' : 'Afficher'}</Text>
        </Pressable>
        {isCodeOpen ? (
          <View testID="mermaid-code-panel-content" style={styles.codePanelContent}>
            <Text selectable style={[styles.codeBlock, { backgroundColor: theme.colors.codeSurface, color: theme.colors.codeText }]}>
              {trimmedCode}
            </Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function estimateMermaidHeight(code: string, viewportHeight?: number) {
  if (viewportHeight) {
    return Math.max(420, viewportHeight - 180);
  }
  const lines = code.split('\n').filter(Boolean).length;
  return Math.max(220, Math.min(560, 140 + lines * 22));
}

export { normalizeMermaidCode } from './mermaid-code';

function buildMermaidHtml(code: string, theme: ReturnType<typeof buildAppTheme>, options?: { fullscreen?: boolean }) {
  const codeJson = JSON.stringify(code);
  const fullscreen = Boolean(options?.fullscreen);
  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html, body {
        width: 100%;
        min-height: 100%;
        background: ${theme.colors.mediaCanvas};
        color: ${theme.colors.text};
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      body {
        overflow: hidden;
      }
      #wrap {
        padding: 10px;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      #toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        background: ${theme.colors.surface};
        border: 1px solid ${theme.colors.border};
      }
      #toolbarLeft {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      #zoomValue {
        color: ${theme.colors.text};
        font-size: 12px;
        font-weight: 700;
      }
      .toolButton {
        border: 1px solid ${theme.colors.border};
        border-radius: 999px;
        background: ${theme.colors.surfaceMuted};
        color: ${theme.colors.text};
        font-weight: 700;
        font-size: 12px;
        padding: 6px 10px;
        cursor: pointer;
      }
      #viewport {
        position: relative;
        flex: 1;
        min-height: ${fullscreen ? '420px' : '220px'};
        overflow: auto;
        border-radius: 10px;
        background: ${theme.colors.mediaCanvas};
        border: 1px solid ${theme.colors.border};
      }
      #out {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        min-width: 100%;
        min-height: 100%;
        padding: 18px;
        transform-origin: top left;
        cursor: grab;
      }
      #out.dragging { cursor: grabbing; }
      #out svg {
        max-width: none;
        height: auto;
        display: block;
      }
      #err {
        color: ${theme.colors.text};
        background: ${theme.colors.surface};
        border: 1px solid ${theme.colors.border};
        border-radius: 10px;
        padding: 10px;
        white-space: pre-wrap;
        font-size: 12px;
        line-height: 18px;
        margin-top: 8px;
        display: none;
      }
      #loading {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 120px;
        color: ${theme.colors.textMuted};
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <div id="wrap">
      <div id="toolbar">
        <div id="toolbarLeft">
          <button class="toolButton" id="zoomOut" type="button">-</button>
          <button class="toolButton" id="zoomIn" type="button">+</button>
          <button class="toolButton" id="zoomReset" type="button">Reset</button>
          <span id="zoomValue">100%</span>
        </div>
        <div id="zoomHint">Glisser pour deplacer</div>
      </div>
      <div id="loading">Rendu Mermaid en cours…</div>
      <div id="viewport"><div id="out"></div></div>
      <div id="err"></div>
    </div>
    <script>
      (function () {
        const code = ${codeJson};
        const loading = document.getElementById('loading');
        const errorElement = document.getElementById('err');
        const viewport = document.getElementById('viewport');
        const outputElement = document.getElementById('out');
        const zoomValue = document.getElementById('zoomValue');
        const zoomInButton = document.getElementById('zoomIn');
        const zoomOutButton = document.getElementById('zoomOut');
        const zoomResetButton = document.getElementById('zoomReset');
        let scale = 1;
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let scrollStartLeft = 0;
        let scrollStartTop = 0;
        const themeVariables = ${JSON.stringify(buildThemeVariables(theme))};

        function applyScale() {
          if (outputElement) {
            outputElement.style.transform = 'scale(' + scale + ')';
          }
          if (zoomValue) {
            zoomValue.textContent = Math.round(scale * 100) + '%';
          }
        }

        function setScale(nextValue) {
          scale = Math.max(0.4, Math.min(3, nextValue));
          applyScale();
        }

        function bindPanAndZoom() {
          if (zoomInButton) {
            zoomInButton.addEventListener('click', function () { setScale(scale + 0.2); });
          }
          if (zoomOutButton) {
            zoomOutButton.addEventListener('click', function () { setScale(scale - 0.2); });
          }
          if (zoomResetButton) {
            zoomResetButton.addEventListener('click', function () {
              setScale(1);
              if (viewport) {
                viewport.scrollTo({ left: 0, top: 0, behavior: 'smooth' });
              }
            });
          }
          if (!viewport || !outputElement) {
            return;
          }

          outputElement.addEventListener('pointerdown', function (event) {
            isDragging = true;
            dragStartX = event.clientX;
            dragStartY = event.clientY;
            scrollStartLeft = viewport.scrollLeft;
            scrollStartTop = viewport.scrollTop;
            outputElement.classList.add('dragging');
          });

          window.addEventListener('pointerup', function () {
            isDragging = false;
            outputElement.classList.remove('dragging');
          });

          outputElement.addEventListener('pointermove', function (event) {
            if (!isDragging) {
              return;
            }
            viewport.scrollLeft = scrollStartLeft - (event.clientX - dragStartX);
            viewport.scrollTop = scrollStartTop - (event.clientY - dragStartY);
          });
        }

        function finishLoading() {
          if (loading) {
            loading.remove();
          }
        }

        function findValidationError(value) {
          for (let index = 0; index < value.length; index += 1) {
            const current = value.charCodeAt(index);
            if (current === 9 || current === 10 || current === 13) {
              continue;
            }
            if (current < 32 || current > 126) {
              return 'Caracteres non ASCII detectes';
            }
          }
          return null;
        }

        function showError(reason) {
          finishLoading();
          if (outputElement) {
            outputElement.innerHTML = '';
          }
          if (errorElement) {
            errorElement.style.display = 'block';
            errorElement.textContent = reason || 'Le diagramme Mermaid n\'a pas pu etre affiche. Consultez la rubrique Code Mermaid ci-dessous.';
          }
        }

        function renderDiagram(mermaidLib) {
          mermaidLib.initialize({
            startOnLoad: false,
            securityLevel: 'loose',
            theme: 'base',
            themeVariables
          });
          return mermaidLib.render('obsirag_mermaid', code).then(function(result) {
            if (outputElement) {
              outputElement.innerHTML = result.svg;
            }
            applyScale();
            bindPanAndZoom();
            finishLoading();
          });
        }

        function loadScriptSources(sources, index) {
          if (index >= sources.length) {
            showError();
            return;
          }

          const script = document.createElement('script');
          script.src = sources[index];
          script.async = true;
          script.onload = function() {
            if (!window.mermaid) {
              loadScriptSources(sources, index + 1);
              return;
            }

            const validationError = findValidationError(code);
            if (validationError) {
              showError(validationError + '. Consultez la rubrique Code Mermaid ci-dessous.');
              return;
            }

            renderDiagram(window.mermaid).catch(function(error) {
              showError('Le rendu Mermaid a echoue. Consultez la rubrique Code Mermaid ci-dessous.');
            });
          };
          script.onerror = function() {
            loadScriptSources(sources, index + 1);
          };
          document.head.appendChild(script);
        }

        window.setTimeout(function() {
          if (loading && loading.isConnected) {
            showError('Le moteur Mermaid est indisponible pour le moment. Consultez la rubrique Code Mermaid ci-dessous.');
          }
        }, 8000);

        loadScriptSources([
          'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js',
          'https://unpkg.com/mermaid@11/dist/mermaid.min.js'
        ], 0);
      })();
    </script>
  </body>
</html>`;
}

function buildThemeVariables(theme: ReturnType<typeof buildAppTheme>) {
  return {
    fontFamily: "system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",
    fontSize: '13px',
    background: theme.colors.mediaCanvas,
    primaryColor: theme.colors.entityPersonSurface,
    primaryTextColor: theme.colors.entityPersonText,
    primaryBorderColor: theme.colors.primary,
    lineColor: theme.colors.primary,
    secondaryColor: theme.colors.entityOrganizationSurface,
    tertiaryColor: theme.colors.entityConceptSurface,
    mainBkg: theme.colors.entityPersonSurface,
    nodeBorder: theme.colors.primary,
    clusterBkg: theme.colors.surfaceMuted,
    clusterBorder: theme.colors.warningText,
    titleColor: theme.colors.text,
    edgeLabelBackground: theme.colors.surface,
    textColor: theme.colors.text,
    secondaryTextColor: theme.colors.entityOrganizationText,
    tertiaryTextColor: theme.colors.entityConceptText,
    clusterTextColor: theme.colors.text,
  };
}

type MermaidRuntime = {
  initialize: (config: Record<string, unknown>) => void;
  render: (id: string, code: string, container?: Element) => Promise<{ svg: string }>;
};

export function resolveMermaidLibrary(moduleValue: unknown): MermaidRuntime {
  const candidate = extractDefaultExport(moduleValue);

  if (
    !candidate ||
    typeof candidate !== 'object' ||
    typeof (candidate as { initialize?: unknown }).initialize !== 'function' ||
    typeof (candidate as { render?: unknown }).render !== 'function'
  ) {
    throw new Error('Mermaid library export is invalid.');
  }

  return candidate as MermaidRuntime;
}

function extractDefaultExport(moduleValue: unknown) {
  if (!moduleValue || typeof moduleValue !== 'object') {
    return moduleValue;
  }

  return 'default' in (moduleValue as Record<string, unknown>)
    ? (moduleValue as { default: unknown }).default
    : moduleValue;
}

export function buildStaticMermaidHtml({
  svg,
  error,
  fullscreen = false,
}: {
  svg: string | null;
  error: string | null;
  fullscreen?: boolean;
}) {
  const content = error
    ? `<div id="err">${escapeHtml(error)}</div>`
    : svg
      ? `<div id="out">${svg}</div>`
      : '<div id="loading">Rendu Mermaid en cours...</div>';
  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html, body {
        width: 100%;
        min-height: 100%;
        background: #f6fbff;
        color: #111111;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      body { overflow: auto; }
      #wrap {
        padding: 10px;
        min-height: ${fullscreen ? '420px' : '220px'};
      }
      #out {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        min-width: 100%;
        min-height: 100%;
        padding: 18px;
        border-radius: 10px;
        background: #f6fbff;
        border: 1px solid #d9e6f0;
        overflow: auto;
      }
      #out svg {
        max-width: 100%;
        height: auto;
        display: block;
      }
      #err {
        color: #2f2419;
        background: #fffdfa;
        border: 1px solid #ded5c9;
        border-radius: 10px;
        padding: 10px;
        white-space: pre-wrap;
        font-size: 12px;
        line-height: 18px;
      }
      #loading {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 120px;
        color: #49657f;
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <div id="wrap">${content}</div>
  </body>
</html>`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildMermaidLiveUrl(code: string) {
  return `https://mermaid.live/`;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 12,
    gap: 8,
  },
  cardFullscreen: {
    flex: 1,
    borderRadius: 18,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  title: {
    fontWeight: '700',
  },
  link: {
    fontWeight: '700',
  },
  codePanel: {
    gap: 8,
    borderRadius: 16,
    borderWidth: 1,
    padding: 12,
  },
  codePanelHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  codePanelHeaderCopy: {
    gap: 2,
    flexShrink: 1,
  },
  codePanelTitle: {
    fontSize: 13,
    fontWeight: '700',
  },
  codePanelCaption: {
    fontSize: 12,
  },
  codePanelContent: {
    gap: 8,
  },
  codeBlock: {
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 12,
    lineHeight: 18,
    fontFamily: Platform.select({
      ios: 'Menlo',
      android: 'monospace',
      default: 'monospace',
    }),
  },
  webview: {
    width: '100%',
    backgroundColor: '#f6fbff',
  },
  caption: {
    fontSize: 12,
    lineHeight: 18,
  },
});