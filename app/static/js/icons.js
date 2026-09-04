/**
 * Shared icon library — inline SVG strings, zero external dependency.
 * Deliberately not a CDN icon font: we already hit a real production bug
 * from a blocked CDN (Chart.js) earlier in this project, and icons that
 * silently fail to render are worse than a chart that fails to render,
 * since they'd degrade every button and card across the whole app at once.
 *
 * Usage: icon('dumbbell', 18) -> returns an <svg> string, safe to drop
 * directly into innerHTML or a template literal.
 */
const ICONS = {
  // Muscle group / split category icons
  legs: '<path d="M6 3v6l-2 12h4l2-9 2 9h4L14 9V3"/><path d="M6 3h8"/>',
  push: '<path d="M4 12h4M16 12h4M8 8v8M16 8v8"/><rect x="8" y="10" width="8" height="4" rx="1"/>',
  pull: '<path d="M12 3v6M8 9l4-6 4 6"/><path d="M6 13c0 4 3 7 6 7s6-3 6-7"/>',
  core: '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>',
  cardio: '<path d="M3 12h4l2-7 4 14 2-7h6"/>',
  warmup: '<circle cx="12" cy="6" r="2"/><path d="M12 8v6l-3 6M12 14l4 6M9 11l-4 2M15 11l4 2"/>',
  stretch: '<circle cx="12" cy="5" r="2"/><path d="M12 7v5M8 8l4 4 4-4M6 19l6-7 6 7"/>',
  dumbbell: '<path d="M6 8v8M4 10v4M2 11v2M18 8v8M20 10v4M22 11v2M6 12h12"/>',

  // Action / UI icons
  check: '<path d="M20 6L9 17l-5-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0l-1 14a2 2 0 01-2 2H7a2 2 0 01-2-2L4 6"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  logout: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
  chart: '<path d="M3 3v18h18M7 16l4-6 4 3 5-7"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a8 8 0 0116 0v1"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  arrowLeft: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  arrowRight: '<path d="M5 12h14M12 5l7 7-7 7"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0114.7-3.4L23 10M1 14l4.8 4.4A9 9 0 0020.5 15"/>',
  flame: '<path d="M12 2c-1.5 4-5 6-5 10a5 5 0 0010 0c0-1.5-1-2.5-1-4 1.5 1 3 3 3 5.5A6.5 6.5 0 0112 20a6.5 6.5 0 01-6.5-6.5C5.5 9 8 6 12 2z"/>',
};

/**
 * Returns an inline <svg> string for the given icon name. Falls back to a
 * generic dot if the name is unrecognized, so a typo never breaks layout —
 * just shows an obviously-wrong placeholder instead of a blank gap.
 */
function icon(name, size = 18, strokeWidth = 2) {
  const path = ICONS[name] || '<circle cx="12" cy="12" r="3"/>';
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;flex:none;">${path}</svg>`;
}

// Maps an exercise's split_category / section to the icon that represents it
// throughout the app (exercise cards, plan previews, dashboard).
function iconForCategory(splitCategory, section) {
  if (section === 'Warmup') return 'warmup';
  if (section === 'Stretch') return 'stretch';
  const map = { push: 'push', pull: 'pull', legs: 'legs', core: 'core' };
  return map[splitCategory] || 'dumbbell';
}

// Applied once per page on load — maps the handful of nav links, logout
// buttons, and back-links that appear (in some subset) on every page to a
// consistent icon, without needing each template to hand-wire its own markup.
function applyStandardIcons(){
  const NAV_ICON_MAP = [
    { match: a => a.getAttribute('href') === '/' && /back/i.test(a.textContent), name: 'arrowLeft' },
    { match: a => a.getAttribute('href') === '/dashboard', name: 'chart' },
    { match: a => a.getAttribute('href') === '/logs', name: 'list' },
    { match: a => a.getAttribute('href') === '/plans', name: 'calendar' },
    { match: a => a.getAttribute('href') === '/profile', name: 'user' },
    { match: a => a.getAttribute('href') === '/signup', name: 'mail' },
    { match: a => a.getAttribute('href') === '/reset-password', name: 'lock' },
    { match: a => /back/i.test(a.textContent) || /←/.test(a.textContent), name: 'arrowLeft' },
  ];

  document.querySelectorAll('a.nav-link, a.back-link').forEach(a => {
    if (a.dataset.iconApplied) return;
    const rule = NAV_ICON_MAP.find(r => r.match(a));
    if (rule) {
      a.innerHTML = `${icon(rule.name, 14)} <span>${a.innerHTML}</span>`;
      a.style.display = 'inline-flex';
      a.style.alignItems = 'center';
      a.style.gap = '5px';
      a.dataset.iconApplied = 'true';
    }
  });

  document.querySelectorAll('.logout-btn').forEach(btn => {
    if (btn.dataset.iconApplied) return;
    btn.innerHTML = `${icon('logout', 12)} <span>${btn.innerHTML}</span>`;
    btn.style.display = 'inline-flex';
    btn.style.alignItems = 'center';
    btn.style.gap = '4px';
    btn.dataset.iconApplied = 'true';
  });

  // Icon-only round buttons in the app-shell top bar (profile/admin) — no
  // text label, just the icon, sized larger than inline nav-link icons.
  const ICON_BTN_MAP = { '/profile': 'user', '/admin': 'lock', '/': 'dumbbell', '/dashboard': 'chart', '/logs': 'list', '/plans': 'calendar' };
  document.querySelectorAll('.app-icon-btn').forEach(a => {
    if (a.dataset.iconApplied) return;
    const name = ICON_BTN_MAP[a.getAttribute('href')] || 'user';
    a.innerHTML = icon(name, 18);
    a.dataset.iconApplied = 'true';
  });

  // Bottom tab bar entries — icon above a short label, matching native
  // mobile tab-bar conventions. Reads the same href map as the icon buttons.
  document.querySelectorAll('.app-tab').forEach(a => {
    if (a.dataset.iconApplied) return;
    const name = ICON_BTN_MAP[a.getAttribute('href')] || 'dumbbell';
    const label = a.textContent.trim();
    a.innerHTML = `${icon(name, 20)}<span>${label}</span>`;
    a.dataset.iconApplied = 'true';
  });
}

document.addEventListener('DOMContentLoaded', applyStandardIcons);
// Also run immediately in case DOMContentLoaded already fired (script is
// loaded in <head>, but some pages call this after dynamic content renders).
if (document.readyState !== 'loading') applyStandardIcons();
