import { useEffect, useMemo, useRef, useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { findValidationError, normalizeMermaidCode } from './mermaid-code';
import { buildAppTheme, useAppTheme } from '../../theme/app-theme';

type MermaidDiagramProps = {
  code: string;
  tone?: 'light' | 'dark';
  fullscreen?: boolean;
};

type MermaidRuntime = {
  initialize: (config: Record<string, unknown>) => void;
  render: (id: string, code: string, container?: Element) => Promise<{ svg: string }>;
};

let mermaidScriptPromise: Promise<MermaidRuntime> | null = null;

export function MermaidDiagram({ code, tone = 'light', fullscreen = false }: MermaidDiagramProps) {
  const activeTheme = useAppTheme();
  const theme = useMemo(
    () => (activeTheme.resolvedMode === tone ? activeTheme : buildAppTheme(tone === 'dark' ? 'dark' : 'light')),
    [activeTheme.mode, activeTheme.resolvedMode, tone],
  );
  const themeVariables = useMemo(() => buildThemeVariables(theme), [theme]);
  const { height: viewportHeight } = useWindowDimensions();
  const [isCodeOpen, setIsCodeOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [renderedSvg, setRenderedSvg] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const renderSequenceRef = useRef(0);
  const sourceCode = useMemo(() => code.trim().replace(/\r\n/g, '\n'), [code]);
  const trimmedCode = useMemo(() => normalizeMermaidCode(sourceCode), [sourceCode]);
  const codeLineCount = useMemo(() => trimmedCode.split('\n').filter(Boolean).length, [trimmedCode]);
  const height = useMemo(() => estimateMermaidHeight(trimmedCode, fullscreen ? viewportHeight : undefined), [fullscreen, trimmedCode, viewportHeight]);

  useEffect(() => {
    const renderSequence = renderSequenceRef.current + 1;
    renderSequenceRef.current = renderSequence;
    let cancelled = false;

    async function renderDiagram() {
      setRenderError(null);

      const validationError = findValidationError(trimmedCode);
      if (validationError) {
        setRenderedSvg(null);
        setRenderError(validationError + '. Consultez la rubrique Code Mermaid ci-dessous.');
        return;
      }

      try {
        const mermaid = await loadMermaidRuntime();
        if (cancelled) {
          return;
        }

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'loose',
          theme: 'base',
          themeVariables,
        });

        const renderId = `obsirag-mermaid-${Math.random().toString(36).slice(2, 10)}`;
        const result = await mermaid.render(renderId, trimmedCode);
        if (!cancelled && renderSequenceRef.current === renderSequence) {
          setRenderedSvg(result.svg);
          setRenderError(null);
        }
      } catch (_error) {
        if (!cancelled && renderSequenceRef.current === renderSequence) {
          setRenderedSvg(null);
          setRenderError('Le diagramme Mermaid n\'a pas pu etre affiche. Consultez la rubrique Code Mermaid ci-dessous.');
        }
      }
    }

    void renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [themeVariables, trimmedCode]);

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
      <View style={[styles.viewport, { height, backgroundColor: theme.colors.mediaCanvas, borderColor: theme.colors.border }]}> 
        <View style={styles.toolbar}>
          <View style={styles.toolbarLeft}>
            <Pressable onPress={() => setZoom((current) => Math.max(0.4, Number((current - 0.2).toFixed(2))))} style={[styles.toolButton, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
              <Text style={[styles.toolButtonText, { color: theme.colors.text }]}>-</Text>
            </Pressable>
            <Pressable onPress={() => setZoom((current) => Math.min(3, Number((current + 0.2).toFixed(2))))} style={[styles.toolButton, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
              <Text style={[styles.toolButtonText, { color: theme.colors.text }]}>+</Text>
            </Pressable>
            <Pressable onPress={() => setZoom(1)} style={[styles.toolButton, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
              <Text style={[styles.toolButtonText, { color: theme.colors.text }]}>Reset</Text>
            </Pressable>
            <Text style={[styles.zoomValue, { color: theme.colors.text }]}>{Math.round(zoom * 100)}%</Text>
          </View>
          <Text style={[styles.zoomHint, { color: theme.colors.textMuted }]}>Defilement et zoom</Text>
        </View>
        <div
          data-testid="markdown-mermaid-diagram"
          style={{
            overflow: 'auto',
            flex: 1,
            minHeight: fullscreen ? 420 : 220,
            borderRadius: 10,
            border: `1px solid ${theme.colors.border}`,
            backgroundColor: theme.colors.mediaCanvas,
            padding: 18,
          }}
        >
          {renderError ? (
            <div
              style={{
                color: theme.colors.text,
                backgroundColor: theme.colors.surface,
                border: `1px solid ${theme.colors.border}`,
                borderRadius: 10,
                padding: 10,
                whiteSpace: 'pre-wrap',
                fontSize: 12,
                lineHeight: '18px',
              }}
            >
              {renderError}
            </div>
          ) : renderedSvg ? (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                minWidth: '100%',
                minHeight: '100%',
                transform: `scale(${zoom})`,
                transformOrigin: 'top left',
            }}
              dangerouslySetInnerHTML={{ __html: renderedSvg }}
            />
          ) : (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: 120,
                color: theme.colors.textMuted,
                fontSize: 12,
              }}
            >
              Rendu Mermaid en cours...
            </div>
          )}
        </div>
      </View>
      <Text style={[styles.caption, { color: theme.colors.textMuted }]}>
        {fullscreen
          ? 'Utilisez les boutons de zoom et le defilement pour inspecter le diagramme.'
          : Platform.OS === 'web'
            ? 'Un mode plein ecran permet de zoomer et d\'inspecter le diagramme.'
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

function resolveMermaidLibrary(moduleValue: unknown): MermaidRuntime {
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

function loadMermaidRuntime(): Promise<MermaidRuntime> {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.reject(new Error('Browser runtime unavailable.'));
  }

  if (mermaidScriptPromise) {
    return mermaidScriptPromise;
  }

  const existing = (window as Window & { mermaid?: unknown }).mermaid;
  if (existing) {
    mermaidScriptPromise = Promise.resolve(resolveMermaidLibrary(existing));
    return mermaidScriptPromise;
  }

  mermaidScriptPromise = new Promise<MermaidRuntime>((resolve, reject) => {
    const sources = [
      'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js',
      'https://unpkg.com/mermaid@10/dist/mermaid.min.js',
    ];

    const tryLoad = (index: number) => {
      if (index >= sources.length) {
        mermaidScriptPromise = null;
        reject(new Error('Mermaid runtime unavailable.'));
        return;
      }

      const source = sources[index]!;
      const script = document.createElement('script');
      script.src = source;
      script.async = true;
      script.onload = () => {
        try {
          const loaded = resolveMermaidLibrary((window as Window & { mermaid?: unknown }).mermaid);
          resolve(loaded);
        } catch (_error) {
          script.remove();
          tryLoad(index + 1);
        }
      };
      script.onerror = () => {
        script.remove();
        tryLoad(index + 1);
      };
      document.head.appendChild(script);
    };

    tryLoad(0);
  });

  return mermaidScriptPromise;
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

function buildMermaidLiveUrl(_code: string) {
  return 'https://mermaid.live/';
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
  viewport: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 10,
    gap: 8,
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  toolbarLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  toolButton: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  toolButtonText: {
    fontSize: 12,
    fontWeight: '700',
  },
  zoomValue: {
    fontSize: 12,
    fontWeight: '700',
  },
  zoomHint: {
    fontSize: 12,
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
  caption: {
    fontSize: 12,
    lineHeight: 18,
  },
});