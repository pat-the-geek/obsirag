import { useMemo } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

type MermaidDiagramProps = {
  code: string;
};

export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const trimmedCode = code.trim();
  const height = useMemo(() => estimateMermaidHeight(trimmedCode), [trimmedCode]);
  const html = useMemo(() => buildMermaidHtml(trimmedCode), [trimmedCode]);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Diagramme Mermaid</Text>
        <Pressable onPress={() => { void Linking.openURL(buildMermaidLiveUrl(trimmedCode)); }}>
          <Text style={styles.link}>Ouvrir</Text>
        </Pressable>
      </View>
      {Platform.OS === 'web' ? (
        <iframe
          srcDoc={html}
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
      <Text style={styles.caption}>
        {Platform.OS === 'web' ? 'Zoom et interactions disponibles directement dans le diagramme.' : 'Touchez Ouvrir pour une vue plus large si necessaire.'}
      </Text>
    </View>
  );
}

function estimateMermaidHeight(code: string) {
  const lines = code.split('\n').filter(Boolean).length;
  return Math.max(220, Math.min(560, 140 + lines * 22));
}

function buildMermaidHtml(code: string) {
  const codeJson = JSON.stringify(code);
  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <style>
      * { box-sizing: border-box; }
      html, body {
        margin: 0;
        padding: 0;
        background: #f6fbff;
        color: #111111;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      #wrap {
        padding: 8px;
      }
      #out {
        display: flex;
        justify-content: center;
        overflow: auto;
      }
      #out svg {
        max-width: 100%;
        height: auto;
      }
      #err {
        color: #7a1f1f;
        background: #fdecec;
        border: 1px solid #efc2c2;
        border-radius: 10px;
        padding: 10px;
        white-space: pre-wrap;
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <div id="wrap">
      <div id="out"></div>
      <div id="err"></div>
    </div>
    <script>
      (async function () {
        const code = ${codeJson};
        try {
          mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'loose',
            theme: 'base',
            themeVariables: {
              background: '#f6fbff',
              primaryColor: '#dcedf8',
              primaryTextColor: '#111111',
              primaryBorderColor: '#2a5f95',
              lineColor: '#2a5f95',
              clusterBkg: '#eef6fb',
              clusterBorder: '#6788a5',
              edgeLabelBackground: '#ffffff',
              tertiaryColor: '#fff5e6',
              secondaryColor: '#f4efe7'
            }
          });
          const result = await mermaid.render('obsirag_mermaid', code);
          document.getElementById('out').innerHTML = result.svg;
        } catch (error) {
          document.getElementById('err').textContent = 'Erreur Mermaid\n' + (error && error.message ? error.message : String(error));
        }
      })();
    </script>
  </body>
</html>`;
}

function buildMermaidLiveUrl(code: string) {
  return `https://mermaid.live/edit#pako:${encodeURIComponent(code)}`;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    backgroundColor: '#eef6fb',
    borderWidth: 1,
    borderColor: '#c8ddea',
    padding: 12,
    gap: 8,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    color: '#244761',
    fontWeight: '700',
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
    color: '#49657f',
    fontSize: 12,
    lineHeight: 18,
  },
});