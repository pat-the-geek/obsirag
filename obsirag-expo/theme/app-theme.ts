import { useColorScheme } from 'react-native';

import { useAppStore } from '../store/app-store';

export type ThemeMode = 'system' | 'light' | 'dark' | 'quiet' | 'abyss';
export type ResolvedThemeMode = 'light' | 'dark';
export type FontSizeMode = 'compact' | 'normal' | 'large';

export type AppThemeColors = {
  background: string;
  backgroundAlt: string;
  surface: string;
  surfaceMuted: string;
  border: string;
  selection: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  link: string;
  primary: string;
  primaryMuted: string;
  primaryText: string;
  secondaryButton: string;
  secondaryButtonText: string;
  warningSurface: string;
  warningText: string;
  successSurface: string;
  successText: string;
  danger: string;
  dangerSurface: string;
  dangerPillText: string;
  neutralSurface: string;
  neutralText: string;
  quoteBorder: string;
  quoteSurface: string;
  tableBorder: string;
  tableSurface: string;
  tableHeaderSurface: string;
  codeSurface: string;
  codeText: string;
  tagSurface: string;
  tagText: string;
  mediaSurface: string;
  mediaCanvas: string;
  entityPersonSurface: string;
  entityPersonText: string;
  entityOrganizationSurface: string;
  entityOrganizationText: string;
  entityLocationSurface: string;
  entityLocationText: string;
  entityTemporalSurface: string;
  entityTemporalText: string;
  entityConceptSurface: string;
  entityConceptText: string;
  shadow: string;
};

export type AppTheme = {
  mode: ThemeMode;
  resolvedMode: ResolvedThemeMode;
  isDark: boolean;
  colors: AppThemeColors;
};

const lightColors: AppThemeColors = {
  background: '#f6f2ea',
  backgroundAlt: '#efe6d7',
  surface: '#fffdf9',
  surfaceMuted: '#f3ede2',
  border: '#d7cbb8',
  selection: '#e8d8bf',
  text: '#1f160c',
  textMuted: '#5b4b37',
  textSubtle: '#7a6b59',
  link: '#1f5da0',
  primary: '#a55233',
  primaryMuted: '#8a3f25',
  primaryText: '#fff8ef',
  secondaryButton: '#f1eadf',
  secondaryButtonText: '#2c2218',
  warningSurface: '#fff0dc',
  warningText: '#8b4d00',
  successSurface: '#eaf7ef',
  successText: '#1f6a3a',
  danger: '#b3261e',
  dangerSurface: '#fdecea',
  dangerPillText: '#761915',
  neutralSurface: '#eee8dd',
  neutralText: '#4e4334',
  quoteBorder: '#d5b58a',
  quoteSurface: '#f9f1e6',
  tableBorder: '#d7c7b2',
  tableSurface: '#fffaf2',
  tableHeaderSurface: '#f1e6d7',
  codeSurface: '#f3ede2',
  codeText: '#2d2219',
  tagSurface: '#efe5d6',
  tagText: '#5a4024',
  mediaSurface: '#f7f1e7',
  mediaCanvas: '#fffaf3',
  entityPersonSurface: '#e7f0ff',
  entityPersonText: '#1e4f9e',
  entityOrganizationSurface: '#ece8ff',
  entityOrganizationText: '#4d3f9a',
  entityLocationSurface: '#e3f7f3',
  entityLocationText: '#1e7368',
  entityTemporalSurface: '#fff1de',
  entityTemporalText: '#8a4e18',
  entityConceptSurface: '#f3ebff',
  entityConceptText: '#5e3d94',
  shadow: 'rgba(28, 18, 8, 0.12)',
};

const darkColors: AppThemeColors = {
  background: '#0f141c',
  backgroundAlt: '#161d28',
  surface: '#1a2230',
  surfaceMuted: '#212b3b',
  border: '#2f3d51',
  selection: '#26344a',
  text: '#e7edf7',
  textMuted: '#b7c3d6',
  textSubtle: '#8f9db4',
  link: '#8ac3ff',
  primary: '#5fa3ff',
  primaryMuted: '#2f5f99',
  primaryText: '#091525',
  secondaryButton: '#2a3648',
  secondaryButtonText: '#dce7f7',
  warningSurface: '#3b2a14',
  warningText: '#ffc27a',
  successSurface: '#153427',
  successText: '#86d7ad',
  danger: '#ff7c7c',
  dangerSurface: '#3a1d24',
  dangerPillText: '#ffd6d6',
  neutralSurface: '#2a3342',
  neutralText: '#c6d3e6',
  quoteBorder: '#4d5f79',
  quoteSurface: '#1a2738',
  tableBorder: '#37475e',
  tableSurface: '#162132',
  tableHeaderSurface: '#203047',
  codeSurface: '#101a28',
  codeText: '#d8e5f8',
  tagSurface: '#283447',
  tagText: '#c7d9f5',
  mediaSurface: '#182232',
  mediaCanvas: '#0f1826',
  entityPersonSurface: '#1f3a5d',
  entityPersonText: '#afd4ff',
  entityOrganizationSurface: '#392e5c',
  entityOrganizationText: '#d2c2ff',
  entityLocationSurface: '#1f4d49',
  entityLocationText: '#a7ece2',
  entityTemporalSurface: '#4b3821',
  entityTemporalText: '#ffd8a3',
  entityConceptSurface: '#3a2f4f',
  entityConceptText: '#d8c2ff',
  shadow: 'rgba(0, 0, 0, 0.35)',
};

const quietColors: AppThemeColors = {
  ...lightColors,
  background: '#f5f5f3',
  backgroundAlt: '#ebebe7',
  surface: '#ffffff',
  surfaceMuted: '#f1f1ed',
  selection: '#e4e6dc',
  primary: '#3f5f8a',
  primaryMuted: '#2f4768',
  primaryText: '#f5f8ff',
  link: '#355d8f',
};

const abyssColors: AppThemeColors = {
  ...darkColors,
  background: '#09111d',
  backgroundAlt: '#0d1726',
  surface: '#102036',
  surfaceMuted: '#17304f',
  selection: '#1d3d61',
  primary: '#38a3ff',
  primaryMuted: '#1f4f80',
  primaryText: '#03101d',
  link: '#8fd2ff',
};

export function buildAppTheme(mode: ThemeMode): AppTheme {
  const normalizedMode: ThemeMode = mode ?? 'system';
  const resolvedMode: ResolvedThemeMode = normalizedMode === 'dark' || normalizedMode === 'abyss' ? 'dark' : 'light';

  const colors =
    normalizedMode === 'quiet'
      ? quietColors
      : normalizedMode === 'abyss'
        ? abyssColors
        : resolvedMode === 'dark'
          ? darkColors
          : lightColors;

  return {
    mode: normalizedMode,
    resolvedMode,
    isDark: resolvedMode === 'dark',
    colors,
  };
}

export function useAppTheme(): AppTheme {
  const mode = useAppStore((state) => state.themeMode) as ThemeMode;
  const systemScheme = useColorScheme();

  if (mode === 'system' || !mode) {
    return buildAppTheme(systemScheme === 'dark' ? 'dark' : 'light');
  }

  return buildAppTheme(mode);
}

export function formatThemeModeLabel(mode: ThemeMode): string {
  if (mode === 'system') return 'Automatique';
  if (mode === 'light') return 'Light+';
  if (mode === 'dark') return 'Dark+';
  if (mode === 'quiet') return 'Atelier';
  return 'Noctis';
}

const FONT_SCALE: Record<FontSizeMode, number> = {
  compact: 0.92,
  normal: 1,
  large: 1.12,
};

export function formatFontSizeModeLabel(mode: FontSizeMode): string {
  if (mode === 'compact') return 'Compacte';
  if (mode === 'large') return 'Confort';
  return 'Normale';
}

export function useAppFontScale(): {
  mode: FontSizeMode;
  scale: number;
  canIncrease: boolean;
  canDecrease: boolean;
} {
  const rawMode = useAppStore((state) => {
    const candidate = (state as unknown as { fontSizeMode?: FontSizeMode }).fontSizeMode;
    return candidate;
  });

  const mode: FontSizeMode = rawMode === 'compact' || rawMode === 'large' || rawMode === 'normal' ? rawMode : 'normal';
  return {
    mode,
    scale: FONT_SCALE[mode],
    canIncrease: mode !== 'large',
    canDecrease: mode !== 'compact',
  };
}

export function scaleFontSize(size: number, factor = 1): number {
  return Math.round(size * factor * 100) / 100;
}

export function scaleLineHeight(height: number, factor = 1): number {
  return Math.round(height * factor * 100) / 100;
}
