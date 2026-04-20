import { ColorSchemeName, useColorScheme } from 'react-native';

import { useAppStore } from '../store/app-store';

export type ThemeMode = 'system' | 'light' | 'dark' | 'quiet' | 'abyss';
export type ResolvedThemeMode = 'light' | 'dark';
export type FontSizeMode = 'small' | 'medium' | 'large';

type ThemePalette = {
  background: string;
  backgroundAlt: string;
  surface: string;
  surfaceMuted: string;
  border: string;
  shadow: string;
  text: string;
  textMuted: string;
  textSubtle: string;
  primary: string;
  primaryMuted: string;
  primaryText: string;
  secondaryButton: string;
  secondaryButtonText: string;
  danger: string;
  dangerText: string;
  successSurface: string;
  successText: string;
  warningSurface: string;
  warningText: string;
  neutralSurface: string;
  neutralText: string;
  dangerSurface: string;
  dangerPillText: string;
  selection: string;
  link: string;
  codeSurface: string;
  codeText: string;
  quoteSurface: string;
  quoteBorder: string;
  tagSurface: string;
  tagText: string;
  tableSurface: string;
  tableHeaderSurface: string;
  tableBorder: string;
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
};

export type AppTheme = {
  mode: ThemeMode;
  resolvedMode: ResolvedThemeMode;
  isDark: boolean;
  label: 'Automatique' | 'Light+' | 'Dark+' | 'Atelier' | 'Noctis';
  colors: ThemePalette;
};

const FONT_SCALE_BY_MODE: Record<FontSizeMode, number> = {
  small: 0.92,
  medium: 1,
  large: 1.12,
};

const FONT_SIZE_ORDER: FontSizeMode[] = ['small', 'medium', 'large'];

const LIGHT_PLUS: ThemePalette = {
  background: '#f6f8fc',
  backgroundAlt: '#eef2f8',
  surface: '#ffffff',
  surfaceMuted: '#f3f6fb',
  border: '#d7deea',
  shadow: '#8aa0c04d',
  text: '#1f2328',
  textMuted: '#5f6b7a',
  textSubtle: '#7a8594',
  primary: '#0b63c9',
  primaryMuted: '#e8f1fb',
  primaryText: '#f7fbff',
  secondaryButton: '#e8edf5',
  secondaryButtonText: '#213247',
  danger: '#c74e39',
  dangerText: '#fff7f5',
  successSurface: '#dcefd9',
  successText: '#255b28',
  warningSurface: '#f5e5c8',
  warningText: '#7a4f00',
  neutralSurface: '#e6ebf2',
  neutralText: '#4b5a6d',
  dangerSurface: '#f4d5d1',
  dangerPillText: '#7b1e1e',
  selection: '#dce8f8',
  link: '#0b63c9',
  codeSurface: '#1f2328',
  codeText: '#eef2f6',
  quoteSurface: '#eef2f8',
  quoteBorder: '#c2cfdf',
  tagSurface: '#dce8f8',
  tagText: '#17324a',
  tableSurface: '#fbfcfe',
  tableHeaderSurface: '#eaf0f8',
  tableBorder: '#d7deea',
  mediaSurface: '#f3f6fb',
  mediaCanvas: '#ffffff',
  entityPersonSurface: '#cfe8ff',
  entityPersonText: '#163a56',
  entityOrganizationSurface: '#ffe4b8',
  entityOrganizationText: '#5c3900',
  entityLocationSurface: '#d5f1cf',
  entityLocationText: '#18472a',
  entityTemporalSurface: '#ffd7c4',
  entityTemporalText: '#5a2d16',
  entityConceptSurface: '#e8dafb',
  entityConceptText: '#3c245d',
};

const DARK_PLUS: ThemePalette = {
  background: '#111827',
  backgroundAlt: '#0d1117',
  surface: '#161b22',
  surfaceMuted: '#1f2937',
  border: '#30363d',
  shadow: '#00000066',
  text: '#e6edf3',
  textMuted: '#9da7b3',
  textSubtle: '#7f8894',
  primary: '#58a6ff',
  primaryMuted: '#1f3a5f',
  primaryText: '#eef6ff',
  secondaryButton: '#253142',
  secondaryButtonText: '#d7e3f0',
  danger: '#b84d43',
  dangerText: '#fff1ee',
  successSurface: '#173824',
  successText: '#8ddf9a',
  warningSurface: '#45331a',
  warningText: '#f0c674',
  neutralSurface: '#273142',
  neutralText: '#c3d0df',
  dangerSurface: '#472425',
  dangerPillText: '#ffb9b4',
  selection: '#1e3a5f',
  link: '#8ec7ff',
  codeSurface: '#0d1117',
  codeText: '#eef4fb',
  quoteSurface: '#1f2937',
  quoteBorder: '#4a647f',
  tagSurface: '#27425c',
  tagText: '#e7f2ff',
  tableSurface: '#161b22',
  tableHeaderSurface: '#202937',
  tableBorder: '#30363d',
  mediaSurface: '#1f2937',
  mediaCanvas: '#0d1117',
  entityPersonSurface: '#315a7c',
  entityPersonText: '#f2f8ff',
  entityOrganizationSurface: '#7a5626',
  entityOrganizationText: '#fff6e9',
  entityLocationSurface: '#38684a',
  entityLocationText: '#eefbe8',
  entityTemporalSurface: '#7d4a34',
  entityTemporalText: '#fff1ea',
  entityConceptSurface: '#624784',
  entityConceptText: '#f6efff',
};

const QUIET_LIGHT: ThemePalette = {
  background: '#f3f5f7',
  backgroundAlt: '#ebeff3',
  surface: '#fcfcfc',
  surfaceMuted: '#f0f3f6',
  border: '#d4dbe3',
  shadow: '#98a7b533',
  text: '#2a2f36',
  textMuted: '#65707c',
  textSubtle: '#818b96',
  primary: '#2f6f9f',
  primaryMuted: '#ddebf6',
  primaryText: '#f6fbff',
  secondaryButton: '#e2e8ef',
  secondaryButtonText: '#314253',
  danger: '#b85c4a',
  dangerText: '#fff6f4',
  successSurface: '#dce8da',
  successText: '#365d38',
  warningSurface: '#efe1c5',
  warningText: '#7b5a1e',
  neutralSurface: '#e4e8ed',
  neutralText: '#526171',
  dangerSurface: '#f0d7d2',
  dangerPillText: '#7d2f28',
  selection: '#d7e6f3',
  link: '#2f6f9f',
  codeSurface: '#26313d',
  codeText: '#edf2f6',
  quoteSurface: '#ebeff3',
  quoteBorder: '#c5d1dc',
  tagSurface: '#d7e6f3',
  tagText: '#244761',
  tableSurface: '#f8fafc',
  tableHeaderSurface: '#e7edf3',
  tableBorder: '#d4dbe3',
  mediaSurface: '#f0f3f6',
  mediaCanvas: '#ffffff',
  entityPersonSurface: '#cfe2f0',
  entityPersonText: '#234866',
  entityOrganizationSurface: '#f1dfbc',
  entityOrganizationText: '#6f4a13',
  entityLocationSurface: '#d9ead8',
  entityLocationText: '#30553a',
  entityTemporalSurface: '#f4dbd0',
  entityTemporalText: '#6b3b2c',
  entityConceptSurface: '#e6def5',
  entityConceptText: '#4a3667',
};

const ABYSS: ThemePalette = {
  background: '#000c18',
  backgroundAlt: '#00111f',
  surface: '#061a2b',
  surfaceMuted: '#0b2235',
  border: '#163956',
  shadow: '#00000080',
  text: '#d8e6f4',
  textMuted: '#8aa1b5',
  textSubtle: '#6c8297',
  primary: '#4aa3ff',
  primaryMuted: '#083b63',
  primaryText: '#edf7ff',
  secondaryButton: '#11314a',
  secondaryButtonText: '#cde0f2',
  danger: '#a94d4f',
  dangerText: '#fff2f2',
  successSurface: '#0d3b33',
  successText: '#83ddc6',
  warningSurface: '#483514',
  warningText: '#f1c56b',
  neutralSurface: '#14314a',
  neutralText: '#b9d0e3',
  dangerSurface: '#46242e',
  dangerPillText: '#ffb2bf',
  selection: '#0d4a78',
  link: '#7fc4ff',
  codeSurface: '#041220',
  codeText: '#e9f5ff',
  quoteSurface: '#0b2235',
  quoteBorder: '#2a5a82',
  tagSurface: '#0d4a78',
  tagText: '#edf7ff',
  tableSurface: '#061a2b',
  tableHeaderSurface: '#0b2235',
  tableBorder: '#163956',
  mediaSurface: '#0b2235',
  mediaCanvas: '#03101d',
  entityPersonSurface: '#0d4a78',
  entityPersonText: '#edf7ff',
  entityOrganizationSurface: '#6e4a11',
  entityOrganizationText: '#fff0c8',
  entityLocationSurface: '#0d5145',
  entityLocationText: '#d9fff1',
  entityTemporalSurface: '#6d3746',
  entityTemporalText: '#ffe7ed',
  entityConceptSurface: '#4c3d86',
  entityConceptText: '#f1ebff',
};

export function resolveThemeMode(mode: ThemeMode, systemScheme?: ColorSchemeName): ResolvedThemeMode {
  if (mode === 'light' || mode === 'quiet') {
    return 'light';
  }

  if (mode === 'dark' || mode === 'abyss') {
    return 'dark';
  }

  return systemScheme === 'dark' ? 'dark' : 'light';
}

export function buildAppTheme(mode: ThemeMode, systemScheme?: ColorSchemeName): AppTheme {
  const resolvedMode = resolveThemeMode(mode, systemScheme);
  const colors = mode === 'quiet' ? QUIET_LIGHT : mode === 'abyss' ? ABYSS : resolvedMode === 'dark' ? DARK_PLUS : LIGHT_PLUS;

  return {
    mode,
    resolvedMode,
    isDark: resolvedMode === 'dark',
    label:
      mode === 'system'
        ? 'Automatique'
        : mode === 'light'
          ? 'Light+'
          : mode === 'dark'
            ? 'Dark+'
            : mode === 'quiet'
              ? 'Atelier'
              : 'Noctis',
    colors,
  };
}

export function useAppTheme(): AppTheme {
  const themeMode = useAppStore((state) => state.themeMode);
  const systemScheme = useColorScheme();

  return buildAppTheme(themeMode, systemScheme);
}

export function getFontScale(mode: FontSizeMode): number {
  return FONT_SCALE_BY_MODE[mode];
}

export function formatFontSizeModeLabel(mode: FontSizeMode): 'Petite' | 'Standard' | 'Grande' {
  return mode === 'small' ? 'Petite' : mode === 'large' ? 'Grande' : 'Standard';
}

export function getNextFontSizeMode(mode: FontSizeMode, direction: 'decrease' | 'increase'): FontSizeMode {
  const currentIndex = FONT_SIZE_ORDER.indexOf(mode);
  const nextIndex = direction === 'increase'
    ? Math.min(currentIndex + 1, FONT_SIZE_ORDER.length - 1)
    : Math.max(currentIndex - 1, 0);
  return FONT_SIZE_ORDER[nextIndex] ?? 'medium';
}

export function scaleFontSize(size: number, scale: number): number {
  return Math.round(size * scale * 10) / 10;
}

export function scaleLineHeight(lineHeight: number, scale: number): number {
  return Math.round(lineHeight * scale * 10) / 10;
}

export function useAppFontScale() {
  const fontSizeMode = useAppStore((state) => state.fontSizeMode);
  const scale = getFontScale(fontSizeMode);
  return {
    mode: fontSizeMode,
    scale,
    label: formatFontSizeModeLabel(fontSizeMode),
    canDecrease: fontSizeMode !== 'small',
    canIncrease: fontSizeMode !== 'large',
  };
}

export function formatThemeModeLabel(mode: ThemeMode): 'Automatique' | 'Light+' | 'Dark+' | 'Atelier' | 'Noctis' {
  return mode === 'system'
    ? 'Automatique'
    : mode === 'light'
      ? 'Light+'
      : mode === 'dark'
        ? 'Dark+'
        : mode === 'quiet'
          ? 'Atelier'
          : 'Noctis';
}