import { useMemo } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { WebView } from 'react-native-webview';

type MermaidDiagramProps = {
  code: string;
  tone?: 'light' | 'dark';
  fullscreen?: boolean;
};

export function MermaidDiagram({ code, tone = 'light', fullscreen = false }: MermaidDiagramProps) {
  const { height: viewportHeight } = useWindowDimensions();
  const trimmedCode = useMemo(() => normalizeMermaidCode(code), [code]);
  const height = useMemo(() => estimateMermaidHeight(trimmedCode, fullscreen ? viewportHeight : undefined), [fullscreen, trimmedCode, viewportHeight]);
  const html = useMemo(() => buildMermaidHtml(trimmedCode, { fullscreen }), [fullscreen, trimmedCode]);

  return (
    <View style={[styles.card, fullscreen ? styles.cardFullscreen : null, tone === 'dark' ? styles.cardDark : styles.cardLight]}>
      <View style={styles.headerRow}>
        <Text style={[styles.title, tone === 'dark' ? styles.titleDark : styles.titleLight]}>Diagramme Mermaid</Text>
        <View style={styles.headerActions}>
          {!fullscreen ? (
            <Pressable
              onPress={() => {
                require('../../store/app-store').useAppStore.getState().openMermaidViewer({ code: trimmedCode, tone });
                require('expo-router').router.push('/mermaid-viewer');
              }}
            >
              <Text style={styles.link}>Plein ecran</Text>
            </Pressable>
          ) : null}
          <Pressable onPress={() => { void Linking.openURL(buildMermaidLiveUrl(trimmedCode)); }}>
            <Text style={styles.link}>Live</Text>
          </Pressable>
        </View>
      </View>
      {Platform.OS === 'web' ? (
        <iframe
          srcDoc={html}
          data-testid="markdown-mermaid-diagram"
          style={{ width: '100%', height, border: 'none', backgroundColor: '#f6fbff' }}
          sandbox="allow-scripts allow-same-origin"
          title="Diagramme Mermaid"
        />
      ) : (
        <WebView
          originWhitelist={['*']}
          source={{ html }}
          style={[styles.webview, { height }]}
          scrollEnabled={false}
          nestedScrollEnabled={false}
        />
      )}
      <Text style={[styles.caption, tone === 'dark' ? styles.captionDark : styles.captionLight]}>
        {fullscreen
          ? 'Utilisez les boutons de zoom ou faites glisser le diagramme pour le deplacer.'
          : Platform.OS === 'web'
            ? 'Un mode plein ecran permet de zoomer et de deplacer le diagramme.'
            : 'Touchez Plein ecran pour zoomer et deplacer le diagramme.'}
      </Text>
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

export function normalizeMermaidCode(code: string) {
  return code
    .trim()
    .replace(/\r\n/g, '\n')
    .replace(/(\][ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, ']\n$2')
    .replace(/(\)[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, ')\n$2')
    .replace(/(\}[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, '}\n$2')
    .split('\n')
    .map((line) =>
      line.replace(/\b([A-Za-z][A-Za-z0-9_]*)\[(?!["`])([^\]\n]+)\]/g, (_match, nodeId: string, label: string) => {
        if (!/[():]/.test(label)) {
          return `${nodeId}[${label}]`;
        }

        const escapedLabel = label.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        return `${nodeId}["${escapedLabel}"]`;
      }),
    )
    .join('\n');
}

function buildMermaidHtml(code: string, options?: { fullscreen?: boolean }) {
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
        background: #f6fbff;
        color: #111111;
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
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid #c8ddea;
      }
      #toolbarLeft {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      #zoomValue {
        color: #244761;
        font-size: 12px;
        font-weight: 700;
      }
      .toolButton {
        border: 1px solid #b7cfe2;
        border-radius: 999px;
        background: #ffffff;
        color: #244761;
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
        background: #f6fbff;
        border: 1px solid #d9e6f0;
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
        color: #7a1f1f;
        background: #fdecec;
        border: 1px solid #efc2c2;
        border-radius: 10px;
        padding: 10px;
        white-space: pre-wrap;
        font-size: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        margin-top: 8px;
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
        const themeVariables = {
          fontFamily: "system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",
          fontSize: '13px',
          background: '#ffffff',
          primaryColor: '#dbeafe',
          primaryTextColor: '#1a1a1a',
          primaryBorderColor: '#0066b8',
          lineColor: '#0066b8',
          secondaryColor: '#ffedd5',
          tertiaryColor: '#ede9fe',
          mainBkg: '#dbeafe',
          nodeBorder: '#0066b8',
          clusterBkg: '#f0f4ff',
          clusterBorder: '#d97706',
          titleColor: '#7c3aed',
          edgeLabelBackground: '#ffffff',
          textColor: '#1a1a1a',
          secondaryTextColor: '#1a1a1a',
          tertiaryTextColor: '#1a1a1a',
          clusterTextColor: '#1a1a1a'
        };

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

        function showError(message) {
          finishLoading();
          if (errorElement) {
            errorElement.textContent = message;
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
            showError('Erreur Mermaid\\nImpossible de charger Mermaid depuis les CDNs autorises.');
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

            renderDiagram(window.mermaid).catch(function(error) {
              showError('Erreur Mermaid\\n' + (error && error.message ? error.message : String(error)));
            });
          };
          script.onerror = function() {
            loadScriptSources(sources, index + 1);
          };
          document.head.appendChild(script);
        }

        window.setTimeout(function() {
          if (loading && loading.isConnected) {
            showError('Erreur Mermaid\\nLe chargement du diagramme a expire.');
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
  cardLight: {
    backgroundColor: '#eef6fb',
    borderColor: '#c8ddea',
  },
  cardDark: {
    backgroundColor: '#15191f',
    borderColor: '#2c3a47',
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
  titleLight: {
    color: '#244761',
  },
  titleDark: {
    color: '#e8f0f8',
  },
  link: {
    color: '#2a5f95',
    fontWeight: '700',
  },
  webview: {
    width: '100%',
    backgroundColor: '#f6fbff',
  },
  caption: {
    fontSize: 12,
    lineHeight: 18,
  },
  captionLight: {
    color: '#49657f',
  },
  captionDark: {
    color: '#a9bdd0',
  },
});