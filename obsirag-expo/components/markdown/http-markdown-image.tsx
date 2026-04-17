import { useEffect, useMemo, useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

type HttpMarkdownImageProps = {
  alt: string;
  src: string;
  tone?: 'light' | 'dark';
};

const FALLBACK_ASPECT_RATIO = 16 / 9;

export function HttpMarkdownImage({ alt, src, tone = 'light' }: HttpMarkdownImageProps) {
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
    <View style={[styles.card, tone === 'dark' ? styles.cardDark : styles.cardLight]}>
      <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(src); }} style={styles.pressable}>
        {hasError ? (
          <View style={[styles.fallback, tone === 'dark' ? styles.fallbackDark : styles.fallbackLight]}>
            <Text style={[styles.fallbackTitle, tone === 'dark' ? styles.fallbackTitleDark : styles.fallbackTitleLight]}>
              Image distante indisponible
            </Text>
            <Text style={[styles.fallbackMeta, tone === 'dark' ? styles.fallbackMetaDark : styles.fallbackMetaLight]}>
              {hostname}
            </Text>
          </View>
        ) : (
          <Image
            source={{ uri: src }}
            resizeMode="contain"
            style={styles.image}
            testID="markdown-http-image"
            onError={() => setHasError(true)}
            {...(aspectRatio > 0 ? { aspectRatio } : null)}
          />
        )}
      </Pressable>
      <View style={styles.metaRow}>
        <Text style={[styles.caption, tone === 'dark' ? styles.captionDark : styles.captionLight]}>
          {alt.trim() || hostname}
        </Text>
        <Text style={[styles.source, tone === 'dark' ? styles.sourceDark : styles.sourceLight]}>Source: {hostname}</Text>
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
  cardLight: {
    backgroundColor: '#f7f2ea',
    borderColor: '#dbcdb8',
  },
  cardDark: {
    backgroundColor: '#171717',
    borderColor: '#313131',
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
  fallbackLight: {
    backgroundColor: '#fbf7f0',
  },
  fallbackDark: {
    backgroundColor: '#1f1f1f',
  },
  fallbackTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  fallbackTitleLight: {
    color: '#3f3123',
  },
  fallbackTitleDark: {
    color: '#f1f1f1',
  },
  fallbackMeta: {
    fontSize: 13,
  },
  fallbackMetaLight: {
    color: '#756452',
  },
  fallbackMetaDark: {
    color: '#b5b5b5',
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
  captionLight: {
    color: '#35281d',
  },
  captionDark: {
    color: '#f1f1f1',
  },
  source: {
    fontSize: 12,
  },
  sourceLight: {
    color: '#7a6957',
  },
  sourceDark: {
    color: '#aaaaaa',
  },
});