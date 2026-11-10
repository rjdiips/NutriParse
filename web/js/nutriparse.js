/* NutriParse — Compose and Journal
   Two intents, one surface: Estimate turns a meal into editable rows, Cook
   turns ingredients into recipe cards. Both expose the same call detail.
   Journal is the read side: what has been saved, against the daily goal.

   This file is the shared core of the Compose page's module graph: DOM refs,
   state, copy, formatting, and the mode/view switches. boot.js is the entry
   point; the picker modules import these names explicitly. */

import { Config } from './config-module.js';

export const PARSE_ENDPOINT = '/api/parse';
export const COOK_ENDPOINT = '/api/leftover-alchemist';
export const IMAGE_ENDPOINT = '/api/recipe-image';

export const el = {
  text: /** @type {HTMLTextAreaElement} */ (document.getElementById('mealText')),
  count: document.getElementById('charCount'),
  parse: /** @type {HTMLButtonElement} */ (document.getElementById('parseBtn')),
  hintVerb: document.getElementById('hintVerb'),
  label: document.getElementById('composeLabel'),
  sub: document.getElementById('composeSub'),
  useSoonWrap: document.getElementById('useSoonWrap'),
  useSoon: /** @type {HTMLInputElement} */ (document.getElementById('useSoon')),
  status: document.getElementById('status'),
  configNotice: document.getElementById('configNotice'),
  configNoticeMsg: document.getElementById('configNoticeMsg'),
  error: document.getElementById('error'),
  errorTitle: document.getElementById('errorTitle'),
  errorMsg: document.getElementById('errorMsg'),
  retry: document.getElementById('retryBtn'),
  sample: document.getElementById('sampleBtn'),
  result: document.getElementById('result'),
  resultTitle: document.getElementById('resultTitle'),
  resultSub: document.getElementById('resultSub'),
  rows: document.getElementById('rows'),
  meal: /** @type {HTMLSelectElement} */ (document.getElementById('mealSelect')),
  save: /** @type {HTMLButtonElement} */ (document.getElementById('saveBtn')),
  totalsNote: document.getElementById('totalsNote'),
  totalCalories: document.getElementById('totalCalories'),
  totalProtein: document.getElementById('totalProtein'),
  totalCarbs: document.getElementById('totalCarbs'),
  totalFat: document.getElementById('totalFat'),
  macrobar: document.getElementById('macrobar'),
  inspector: /** @type {HTMLDetailsElement} */ (document.getElementById('inspector')),
  empty: document.getElementById('empty'),
  emptyLabel: document.getElementById('emptyLabel'),
  emptyText: document.getElementById('emptyText'),
  cookResult: document.getElementById('cookResult'),
  cookTitle: document.getElementById('cookTitle'),
  cookSub: document.getElementById('cookSub'),
  cookNote: document.getElementById('cookNote'),
  cookInspector: /** @type {HTMLDetailsElement} */ (document.getElementById('cookInspector')),
  recipeGrid: document.getElementById('recipeGrid'),

  viewCompose: document.getElementById('view-compose'),
  viewJournal: document.getElementById('view-journal'),
  manual: document.getElementById('manualBtn'),
  inspectorSummary: document.getElementById('inspectorSummary'),
  inspectorRawLabel: document.getElementById('inspectorRawLabel'),

  journalTitle: document.getElementById('journalTitle'),
  journalSub: document.getElementById('journalSub'),
  journalAdd: document.getElementById('journalAddBtn'),
  todayCalories: document.getElementById('todayCalories'),
  todayGoal: document.getElementById('todayGoal'),
  todayBar: document.getElementById('todayBar'),
  todayBarWrap: document.getElementById('todayBarWrap'),
  todayPct: document.getElementById('todayPct'),
  todayRemaining: document.getElementById('todayRemaining'),
  todayProtein: document.getElementById('todayProtein'),
  todayCarbs: document.getElementById('todayCarbs'),
  todayFat: document.getElementById('todayFat'),
  todayCount: document.getElementById('todayCount'),
  goalInput: /** @type {HTMLInputElement} */ (document.getElementById('goalInput')),
  goalStatus: document.getElementById('goalStatus'),
  saveGoal: document.getElementById('saveGoalBtn'),
  journalSearch: /** @type {HTMLInputElement} */ (document.getElementById('journalSearch')),
  journalDays: document.getElementById('journalDays'),
  journalEmpty: document.getElementById('journalEmpty'),
  journalEmptyLabel: document.getElementById('journalEmptyLabel'),
  journalEmptyText: document.getElementById('journalEmptyText'),
};

export const estimateParts = {
  inspector: el.inspector,
  chips: document.getElementById('inspectorChips'),
  grid: document.getElementById('inspectorGrid'),
  raw: document.getElementById('rawJson'),
  copy: document.getElementById('copyBtn'),
};

export const cookParts = {
  inspector: el.cookInspector,
  chips: document.getElementById('cookChips'),
  grid: document.getElementById('cookGrid'),
  raw: document.getElementById('cookRaw'),
  copy: document.getElementById('cookCopyBtn'),
};

export const state = {
  view: 'compose',
  mode: 'estimate',
  items: [],
  estimateReady: false,
  cookReady: false,
  cookRecipes: [],
  isSample: false,
  manual: false,
  saved: false,
  busy: false,
  ticker: null,
  // The safety net applies until boot has loaded the server's real values.
  config: Config.fallback(new Error('The server timeouts have not loaded yet.')),
  configReady: null,
};

export function requestTiming(kind) {
  return Config.channelFor(state.config, kind);
}

export function timeoutMeta(meta, kind, includeImage = false) {
  const timing = requestTiming(kind);
  const enriched = { ...meta, timeout_ms: timing.serverMs, wait_ms: timing.waitMs };
  if (includeImage) {
    const image = requestTiming('image');
    enriched.image_timeout_ms = image.serverMs;
    enriched.image_wait_ms = image.waitMs;
  }
  return enriched;
}

export const COPY = {
  estimate: {
    label: 'Describe what you ate',
    sub: 'One line is enough. The model splits it into items, and every number stays editable.',
    placeholder: '2 rotis, dal, and a glass of lassi',
    cta: 'Parse meal',
    verb: 'parse',
    busy: 'Parsing…',
    emptyLabel: 'No meal parsed yet',
    emptyText: 'Type a meal above and the service returns one row per food, each with calories and macros, plus the exact call detail behind them. Nothing is saved until you choose to save it.',
  },
  cook: {
    label: 'What have you got?',
    sub: 'List the ingredients you want to use up. You get three ideas with per-serving nutrition, and the same call detail.',
    placeholder: 'cooked rice, 2 eggs, half a bell pepper, spinach',
    cta: 'Conjure recipes',
    verb: 'conjure',
    busy: 'Cooking…',
    emptyLabel: 'No recipes yet',
    emptyText: 'List a few ingredients above and the service returns three recipe ideas with steps and per-serving macros. Add any of them to the journal as a single serving once you have eaten it.',
  },
};

export const fmt0 = (n) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number(n) || 0);
export const fmt1 = (n) => {
  const v = Math.round((Number(n) || 0) * 10) / 10;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(v);
};
export const num = (n) => Math.max(0, Number(n) || 0);
export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');

export function localDateISO(date = new Date()) {
  const pad = (v) => String(v).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function isoToDate(iso) {
  return new Date(`${iso}T12:00:00`);
}

function addDaysISO(offset) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return localDateISO(d);
}

export function longDate(iso) {
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(isoToDate(iso));
}

export function shortDate(iso) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(isoToDate(iso));
}

export function dayLabel(iso) {
  if (iso === localDateISO()) return 'Today';
  if (iso === addDaysISO(-1)) return 'Yesterday';
  return new Intl.DateTimeFormat(undefined, { weekday: 'long' }).format(isoToDate(iso));
}

/* Only move the page when the target is actually out of view, so loading a
   sample or a short result does not scroll the header away. */
export function reveal(node) {
  const rect = node.getBoundingClientRect();
  if (rect.top < 0 || rect.top > window.innerHeight - 120) {
    node.scrollIntoView({ block: 'start' });
  }
}

export function announce(message) {
  el.status.textContent = message;
}

/* ---------- mode ---------- */

export function setMode(mode) {
  state.mode = mode;
  const copy = COPY[mode];

  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.mode')).forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('[data-examples]')).forEach((group) => {
    group.hidden = group.dataset.examples !== mode;
  });

  el.label.textContent = copy.label;
  el.sub.textContent = copy.sub;
  el.text.placeholder = copy.placeholder;
  el.hintVerb.textContent = copy.verb;
  el.emptyLabel.textContent = copy.emptyLabel;
  el.emptyText.textContent = copy.emptyText;
  if (!state.busy) el.parse.textContent = copy.cta;

  el.useSoonWrap.hidden = mode !== 'cook';
  syncPanels();
}

export function syncPanels() {
  const showEstimate = state.mode === 'estimate' && state.estimateReady;
  const showCook = state.mode === 'cook' && state.cookReady;
  el.result.hidden = !showEstimate;
  el.cookResult.hidden = !showCook;
  el.empty.hidden = showEstimate || showCook;
}

/** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.mode')).forEach((button) => {
  button.addEventListener('click', () => {
    if (state.busy) return;
    setMode(button.dataset.mode);
    el.text.focus();
  });
});

/* ---------- views ---------- */

const VIEW_TITLES = { compose: 'NutriParse — Compose', journal: 'NutriParse — Journal' };

/* The Journal view lives in its own module, so it registers the renderer here
   rather than the core importing it back (which would make a cycle). */
let journalRenderer = () => {};
/** @param {() => void} render */
export function registerJournalRenderer(render) {
  journalRenderer = render;
}

export function setView(view) {
  state.view = view;
  /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.viewtab')).forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  el.viewCompose.hidden = view !== 'compose';
  el.viewJournal.hidden = view !== 'journal';
  document.title = VIEW_TITLES[view] || 'NutriParse';
  if (view === 'journal') journalRenderer();
}

/** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.viewtab')).forEach((button) => {
  button.addEventListener('click', () => {
    if (state.view === button.dataset.view) return;
    setView(button.dataset.view);
    if (state.view === 'journal') el.journalTitle.focus({ preventScroll: true });
  });
});

/* ---------- composer ---------- */

export function updateCount() {
  el.count.textContent = String(el.text.value.length);
}

el.text.addEventListener('input', () => {
  updateCount();
  if (!el.error.hidden) hideError();
});

/** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('.chip--example')).forEach((chip) => {
  chip.addEventListener('click', () => {
    el.text.value = chip.dataset.example || chip.textContent.trim();
    updateCount();
    el.text.focus();
  });
});

/* ---------- errors ---------- */

export function showError(title, message, offerSample) {
  el.errorTitle.textContent = title;
  el.errorMsg.textContent = message;
  el.sample.hidden = !offerSample;
  el.error.hidden = false;
  el.error.scrollIntoView({ block: 'nearest' });
}

export function hideError() {
  el.error.hidden = true;
}
