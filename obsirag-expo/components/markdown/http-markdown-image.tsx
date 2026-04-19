import { useEffect, useMemo, useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { buildAppTheme, useAppTheme } from '../../theme/app-theme';

type HttpMarkdownImageProps = {
  alt: string;
  src: string;
  tone?: 'light' | 'dark';
};

const FALLBACK_ASPECT_RATIO = 16 / 9;

export function HttpMarkdownImage({ alt, src, tone = 'light' }: HttpMarkdownImageProps) {
  const activeTheme = useAppTheme();
  const theme = activeTheme.resolvedMode === tone ? activeTheme : buildAppTheme(tone === 'dark' ? 'dark' : 'light');
  const [aspectRatio, setAspectRatio] = useState(FALLBACK_ASPECT_RATIO);
  const [hasError, setHasError] = useState(false);
  const hostname = useMemo(() => {
    try {
      return new URL(src).hostname.replace(/^www\./, '');
    } catch {
      return src;
    }
  }, [src]);

  useEffect(() => {
    let active = true;
    setHasError(false);
    setAspectRatio(FALLBACK_ASPECT_RATIO);

    Image.getSize(
      src,
      (width, height) => {
        if (!active || width <= 0 || height <= 0) {
          return;
        }
        setAspectRatio(width / height);
      },
      () => {
        if (active) {
          setHasError(true);
        }
      },
    );

    return () => {
      active = false;
    };
  }, [src]);

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.mediaSurface, borderColor: theme.colors.border }]}>
      <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(src); }} style={styles.pressable}>
        {hasError ? (
          <View style={[styles.fallback, { backgroundColor: theme.colors.surfaceMuted }]}>
            <Text style={[styles.fallbackTitle, { color: theme.colors.text }]}>
              Image distante indisponible
            </Text>
            <Text style={[styles.fallbackMeta, { color: theme.colors.textMuted }]}>
              {hostname}
            </Text>
          </View>
        ) : (
          <Image
            source={{ uri: src }}
            resizeMode="contain"
            style={[styles.image, { backgroundColor: theme.colors.mediaCanvas }]}
            testID="markdown-http-image"
            onError={() => setHasError(true)}
            {...(aspectRatio > 0 ? { aspectRatio } : null)}
          />
        )}
      </Pressable>
      <View style={styles.metaRow}>
        <Text style={[styles.caption, { color: theme.colors.text }]}>
          {alt.trim() || hostname}
        </Text>
        <Text style={[styles.source, { color: theme.colors.textMuted }]}>Source: {hostname}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
  },
  pressable: {
    width: '100%',
  },
  image: {
    width: '100%',
    minHeight: 220,
    maxHeight: 520,
    backgroundColor: '#ffffff',
  },
  fallback: {
    minHeight: 180,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
    paddingVertical: 24,
    gap: 6,
  },
  fallbackTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  fallbackMeta: {
    fontSize: 13,
  },
  metaRow: {
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  caption: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
  },
  source: {
    fontSize: 12,
  },
});