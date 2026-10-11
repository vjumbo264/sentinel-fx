/**
 * SENTINEL-FX · Persistent Per-Page UI State (F3)
 * Keeps each page's local UI state (active chips, filters, toggles,
 * scroll offsets, form drafts, selections) alive across store poll ticks
 * and route changes. In-memory only; never persisted to localStorage.
 */

const _pageState = new Map();

/** Get (or lazily create) the state object for a page. */
export function getPageState(page, defaults = {}) {
  if (!_pageState.has(page)) _pageState.set(page, { ...defaults });
  return _pageState.get(page);
}

/** Merge a patch into a page's state. */
export function setPageState(page, patch) {
  const cur = _pageState.get(page) || {};
  _pageState.set(page, { ...cur, ...patch });
  return _pageState.get(page);
}
