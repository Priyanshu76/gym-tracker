/**
 * Shared theme engine — light/dark mode + accent color choice, persisted to
 * localStorage (a purely cosmetic preference, deliberately not synced to
 * the backend — no server round-trip needed just to toggle how the app looks).
 *
 * Applied via data-theme/data-accent attributes on <html>, which every
 * template's CSS reads via custom properties. Call applyTheme() as early as
 * possible in <head> (before the stylesheet paints) to avoid a flash of the
 * wrong theme on load.
 */
const ACCENT_COLORS = [
  { id: 'teal',   label: 'Teal',   hex: '#16e0c5' },
  { id: 'blue',   label: 'Blue',   hex: '#4a9eff' },
  { id: 'purple', label: 'Purple', hex: '#a78bfa' },
  { id: 'pink',   label: 'Pink',   hex: '#f472b6' },
  { id: 'orange', label: 'Orange', hex: '#fb923c' },
  { id: 'coral',  label: 'Coral',  hex: '#f87171' },
  { id: 'green',  label: 'Green',  hex: '#4ade80' },
  { id: 'yellow', label: 'Yellow', hex: '#fbbf24' },
];

function getTheme(){
  return localStorage.getItem('gym-theme') || 'dark';
}
function getAccent(){
  return localStorage.getItem('gym-accent') || 'teal';
}

function applyTheme(){
  document.documentElement.setAttribute('data-theme', getTheme());
  document.documentElement.setAttribute('data-accent', getAccent());
}

function setTheme(theme){
  localStorage.setItem('gym-theme', theme);
  applyTheme();
}
function setAccent(accent){
  localStorage.setItem('gym-accent', accent);
  applyTheme();
}

// Real computed hex values, not CSS var() references — Chart.js draws to a
// canvas and needs actual color strings, it can't resolve CSS custom
// properties itself. Kept here, next to the source of truth for what
// data-theme/data-accent currently are, rather than duplicated per page.
const THEME_COLORS = {
  dark:  { bg: '#17181a', surface: '#1f2022', surfaceAlt: '#26282a', line: '#35373a', text: '#f2efe7', muted: '#9aa0a6', rust: '#b0472f', green: '#6f9c6a', blue: '#6a94b0' },
  light: { bg: '#f7f6f2', surface: '#ffffff', surfaceAlt: '#eeece6', line: '#ddd9d0', text: '#1f2022', muted: '#6b6f76', rust: '#c0392b', green: '#3d7a4a', blue: '#3d6199' },
};
function getResolvedThemeColors(){
  const theme = THEME_COLORS[getTheme()] || THEME_COLORS.dark;
  const accent = ACCENT_COLORS.find(a => a.id === getAccent()) || ACCENT_COLORS[0];
  return { ...theme, accent: accent.hex };
}

function hexToRgba(hex, alpha){
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0,2), 16);
  const g = parseInt(clean.substring(2,4), 16);
  const b = parseInt(clean.substring(4,6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

applyTheme();
