/* NutriParse — Compose and Journal
   Two intents, one surface: Estimate turns a meal into editable rows, Cook
   turns ingredients into recipe cards. Both expose the same call detail.
   Journal is the read side: what has been saved, against the daily goal. */

const PARSE_ENDPOINT = '/api/parse';
const COOK_ENDPOINT = '/api/leftover-alchemist';
const IMAGE_ENDPOINT = '/api/recipe-image';

const el = {
  text: document.getElementById('mealText'),
  count: document.getElementById('charCount'),
  parse: document.getElementById('parseBtn'),
  hintVerb: document.getElementById('hintVerb'),
  label: document.getElementById('composeLabel'),
  sub: document.getElementById('composeSub'),
  useSoonWrap: document.getElementById('useSoonWrap'),
  useSoon: document.getElementById('useSoon'),
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
  meal: document.getElementById('mealSelect'),
  save: document.getElementById('saveBtn'),
  totalsNote: document.getElementById('totalsNote'),
  totalCalories: document.getElementById('totalCalories'),
  totalProtein: document.getElementById('totalProtein'),
  totalCarbs: document.getElementById('totalCarbs'),
  totalFat: document.getElementById('totalFat'),
  macrobar: document.getElementById('macrobar'),
  inspector: document.getElementById('inspector'),
  empty: document.getElementById('empty'),
  emptyLabel: document.getElementById('emptyLabel'),
  emptyText: document.getElementById('emptyText'),
  cookResult: document.getElementById('cookResult'),
  cookTitle: document.getElementById('cookTitle'),
  cookSub: document.getElementById('cookSub'),
  cookNote: document.getElementById('cookNote'),
  cookInspector: document.getElementById('cookInspector'),
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
  goalInput: document.getElementById('goalInput'),
  goalStatus: document.getElementById('goalStatus'),
  saveGoal: document.getElementById('saveGoalBtn'),
  journalSearch: document.getElementById('journalSearch'),
  journalDays: document.getElementById('journalDays'),
  journalEmpty: document.getElementById('journalEmpty'),
  journalEmptyLabel: document.getElementById('journalEmptyLabel'),
  journalEmptyText: document.getElementById('journalEmptyText'),
};

const estimateParts = {
  inspector: el.inspector,
  chips: document.getElementById('inspectorChips'),
  grid: document.getElementById('inspectorGrid'),
  raw: document.getElementById('rawJson'),
  copy: document.getElementById('copyBtn'),
};

const cookParts = {
  inspector: el.cookInspector,
  chips: document.getElementById('cookChips'),
  grid: document.getElementById('cookGrid'),
  raw: document.getElementById('cookRaw'),
  copy: document.getElementById('cookCopyBtn'),
};

const state = {
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

function requestTiming(kind) {
  return Config.channelFor(state.config, kind);
}

function timeoutMeta(meta, kind, includeImage = false) {
  const timing = requestTiming(kind);
  const enriched = { ...meta, timeout_ms: timing.serverMs, wait_ms: timing.waitMs };
  if (includeImage) {
    const image = requestTiming('image');
    enriched.image_timeout_ms = image.serverMs;
    enriched.image_wait_ms = image.waitMs;
  }
  return enriched;
}

const COPY = {
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

const fmt0 = (n) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number(n) || 0);
const fmt1 = (n) => {
  const v = Math.round((Number(n) || 0) * 10) / 10;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(v);
};
const num = (n) => Math.max(0, Number(n) || 0);
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');

function localDateISO(date = new Date()) {
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

function longDate(iso) {
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(isoToDate(iso));
}

function shortDate(iso) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(isoToDate(iso));
}

function dayLabel(iso) {
  if (iso === localDateISO()) return 'Today';
  if (iso === addDaysISO(-1)) return 'Yesterday';
  return new Intl.DateTimeFormat(undefined, { weekday: 'long' }).format(isoToDate(iso));
}

/* Only move the page when the target is actually out of view, so loading a
   sample or a short result does not scroll the header away. */
function reveal(node) {
  const rect = node.getBoundingClientRect();
  if (rect.top < 0 || rect.top > window.innerHeight - 120) {
    node.scrollIntoView({ block: 'start' });
  }
}

function announce(message) {
  el.status.textContent = message;
}

/* ---------- mode ---------- */

function setMode(mode) {
  state.mode = mode;
  const copy = COPY[mode];

  document.querySelectorAll('.mode').forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  document.querySelectorAll('[data-examples]').forEach((group) => {
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

function syncPanels() {
  const showEstimate = state.mode === 'estimate' && state.estimateReady;
  const showCook = state.mode === 'cook' && state.cookReady;
  el.result.hidden = !showEstimate;
  el.cookResult.hidden = !showCook;
  el.empty.hidden = showEstimate || showCook;
}

document.querySelectorAll('.mode').forEach((button) => {
  button.addEventListener('click', () => {
    if (state.busy) return;
    setMode(button.dataset.mode);
    el.text.focus();
  });
});

/* ---------- views ---------- */

const VIEW_TITLES = { compose: 'NutriParse — Compose', journal: 'NutriParse — Journal' };

function setView(view) {
  state.view = view;
  document.querySelectorAll('.viewtab').forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  el.viewCompose.hidden = view !== 'compose';
  el.viewJournal.hidden = view !== 'journal';
  document.title = VIEW_TITLES[view] || 'NutriParse';
  if (view === 'journal') renderJournal();
}

document.querySelectorAll('.viewtab').forEach((button) => {
  button.addEventListener('click', () => {
    if (state.view === button.dataset.view) return;
    setView(button.dataset.view);
    if (state.view === 'journal') el.journalTitle.focus({ preventScroll: true });
  });
});

el.manual.addEventListener('click', startManualRow);
el.journalAdd.addEventListener('click', startManualRow);

/* ---------- composer ---------- */

function updateCount() {
  el.count.textContent = String(el.text.value.length);
}

el.text.addEventListener('input', () => {
  updateCount();
  if (!el.error.hidden) hideError();
});

document.querySelectorAll('.chip--example').forEach((chip) => {
  chip.addEventListener('click', () => {
    el.text.value = chip.dataset.example || chip.textContent.trim();
    updateCount();
    el.text.focus();
  });
});

el.text.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    submit();
  }
});

el.parse.addEventListener('click', submit);
el.retry.addEventListener('click', submit);
el.sample.addEventListener('click', () => showSample(state.mode));

