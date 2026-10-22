/* NutriParse — Compose and Journal
   Two intents, one surface: Estimate turns a meal into editable rows, Cook
   turns ingredients into recipe cards. Both expose the same call detail.
   Journal is the read side: what has been saved, against the daily goal. */

const PARSE_ENDPOINT = '/api/parse';
const COOK_ENDPOINT = '/api/leftover-alchemist';
const IMAGE_ENDPOINT = '/api/recipe-image';
const PARSE_TIMEOUT_MS = 45000;
const COOK_TIMEOUT_MS = 180000;

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
};

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

/* ---------- request ---------- */

function setBusy(busy, mode = state.mode) {
  state.busy = busy;
  el.parse.disabled = busy;
  el.parse.textContent = busy ? COPY[mode].busy : COPY[state.mode].cta;
  el.parse.setAttribute('aria-busy', busy ? 'true' : 'false');
  document.querySelectorAll('.mode').forEach((button) => {
    button.disabled = busy;
  });
}

function stopTicker() {
  if (state.ticker) {
    clearInterval(state.ticker);
    state.ticker = null;
  }
}

async function submit() {
  if (state.busy) return;
  const mode = state.mode;
  const text = el.text.value.trim();
  if (!text) {
    showError(mode === 'cook' ? 'Nothing to cook with' : 'Nothing to parse',
      mode === 'cook' ? 'List at least one ingredient first.' : 'Describe at least one food first.', false);
    el.text.focus();
    return;
  }

  hideError();
  setBusy(true, mode);
  const started = Date.now();

  if (mode === 'cook') {
    el.cookResult.hidden = false;
    el.empty.hidden = true;
    el.cookSub.textContent = 'Consulting the leftovers…';
    el.cookNote.textContent = '';
    el.cookInspector.open = false;
    clearCallDetail(cookParts);
    el.recipeGrid.replaceChildren(skeletonCards(3));
    startTicker(() => {
      el.cookSub.textContent = `Generating three ideas… ${Math.round((Date.now() - started) / 1000)}s`;
    });
  } else {
    state.estimateReady = false;
    el.result.hidden = false;
    el.empty.hidden = true;
    el.resultSub.textContent = 'Parsing your description…';
    el.inspector.open = false;
    showSkeleton();
  }

  const controller = new AbortController();
  const timeout = mode === 'cook' ? COOK_TIMEOUT_MS : PARSE_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const body = mode === 'cook'
      ? { ingredients: text, use_soon: el.useSoon.value.trim() }
      : { text };

    const response = await fetch(mode === 'cook' ? COOK_ENDPOINT : PARSE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      throw Object.assign(new Error((payload && payload.error) || `HTTP ${response.status}`), {
        status: response.status,
      });
    }

    if (mode === 'cook') {
      if (!payload || !Array.isArray(payload.recipes)) {
        throw Object.assign(new Error('The service returned an unexpected response.'), { status: 502 });
      }
      state.cookRecipes = payload.recipes;
      state.isSample = false;
      state.cookReady = true;
      renderRecipes(payload.recipes, payload.meta || {}, payload);
      announce(`${payload.recipes.length} recipes ready.`);
      payload.recipes.forEach((recipe, index) => loadRecipeImage(recipe, index));
    } else {
      if (!payload || !Array.isArray(payload.items)) {
        throw Object.assign(new Error('The service returned an unexpected response.'), { status: 502 });
      }
      state.isSample = false;
      state.estimateReady = true;
      renderItems(payload.items, payload.meta || {}, payload);
      announce(`Parsed ${payload.items.length} item${payload.items.length === 1 ? '' : 's'}.`);
    }
    syncPanels();
  } catch (err) {
    const aborted = err.name === 'AbortError';
    const status = aborted ? 0 : err.status || 0;
    const message = aborted
      ? `No response after ${Math.round(timeout / 1000)} seconds. The provider may be slow or unreachable.`
      : err.message;

    if (mode === 'cook') {
      state.cookReady = false;
      el.cookResult.hidden = true;
      el.recipeGrid.replaceChildren();
    } else {
      state.estimateReady = false;
      el.result.hidden = true;
      state.items = [];
      el.rows.replaceChildren();
      resetTotals();
    }
    syncPanels();

    showError(
      status === 502 ? 'The model call failed'
        : status === 503 ? 'Service unavailable'
          : status ? `Request rejected (${status})`
            : 'Could not reach the service',
      message,
      true,
    );
    announce('Request failed.');
  } finally {
    clearTimeout(timer);
    stopTicker();
    setBusy(false, mode);
  }
}

function startTicker(update) {
  stopTicker();
  update();
  state.ticker = setInterval(update, 1000);
}

/* ---------- errors ---------- */

function showError(title, message, offerSample) {
  el.errorTitle.textContent = title;
  el.errorMsg.textContent = message;
  el.sample.hidden = !offerSample;
  el.error.hidden = false;
  el.error.scrollIntoView({ block: 'nearest' });
}

function hideError() {
  el.error.hidden = true;
}

/* ---------- estimate rows ---------- */

function showSkeleton() {
  el.rows.replaceChildren();
  const skeleton = document.createElement('div');
  skeleton.className = 'skeleton';
  for (let i = 0; i < 3; i += 1) {
    const row = document.createElement('div');
    row.className = 'skeleton__row';
    [62, 80, 48, 40, 40, 40, 18].forEach((width) => {
      const bar = document.createElement('div');
      bar.className = 'skeleton__bar';
      bar.style.width = `${width}%`;
      row.appendChild(bar);
    });
    skeleton.appendChild(row);
  }
  el.rows.replaceChildren(skeleton);
  el.save.disabled = true;
  el.save.textContent = 'Save to journal';
  // The previous parse's totals, macro split, and call detail are not part of
  // the request in flight, so leaving them visible would read as the new result.
  resetTotals();
  clearCallDetail(estimateParts);
  el.inspectorSummary.textContent = 'Request details';
  el.inspectorRawLabel.textContent = 'Response JSON';
}

function resetTotals() {
  [el.totalCalories, el.totalProtein, el.totalCarbs, el.totalFat]
    .forEach((node) => { node.textContent = '—'; });
  el.totalsNote.textContent = '';
  el.macrobar.querySelectorAll('.macrobar__seg')
    .forEach((seg) => { seg.style.width = '0%'; });
  el.macrobar.removeAttribute('aria-label');
}

function renderItems(items, meta, payload, opts = {}) {
  state.items = items.map((item) => ({ ...item }));
  state.saved = false;
  state.isSample = Boolean(meta && meta.sample);
  state.manual = Boolean(opts.manual);
  el.save.disabled = state.isSample;
  el.save.textContent = 'Save to journal';
  el.save.title = state.isSample ? 'Sample data is not saved to your journal' : '';

  el.result.hidden = false;
  el.empty.hidden = true;
  el.resultSub.textContent = opts.sub || (state.isSample
    ? `Sample result · ${state.items.length} item${state.items.length === 1 ? '' : 's'} · not a live model call`
    : `${state.items.length} item${state.items.length === 1 ? '' : 's'} · edit any number before saving`);

  el.inspectorSummary.textContent = opts.summary || 'Request details';
  el.inspectorRawLabel.textContent = opts.rawLabel || 'Response JSON';

  paintRows();
  paintInspector(estimateParts, meta || {}, payload);
  el.resultTitle.focus({ preventScroll: true });
  reveal(el.result);
}

function paintRows() {
  const host = document.createDocumentFragment();
  state.items.forEach((item, index) => host.appendChild(buildRow(item, index)));
  el.rows.replaceChildren(host);
  recompute();
}

function buildRow(item, index) {
  const row = document.createElement('div');
  row.className = 'row';
  row.setAttribute('role', 'row');

  const nameCell = document.createElement('div');
  nameCell.className = 'row__nameCell';
  nameCell.setAttribute('role', 'cell');

  const name = document.createElement('input');
  name.type = 'text';
  name.className = 'row__name';
  name.value = item.name || '';
  name.maxLength = 120;
  name.placeholder = 'Item name';
  name.setAttribute('aria-label', `Item name${item.name ? `: ${item.name}` : ''}`);
  name.addEventListener('input', () => {
    item.name = name.value;
    markDirty();
  });
  nameCell.appendChild(name);

  const portion = document.createElement('input');
  portion.type = 'text';
  portion.className = 'row__portion';
  portion.value = item.portion || '';
  portion.maxLength = 120;
  portion.setAttribute('aria-label', `Portion for ${item.name}`);

  row.append(nameCell, portion);

  [
    ['calories', 'kcal', 'Calories for'],
    ['protein', 'protein', 'Protein grams for'],
    ['carbs', 'carbs', 'Carbs grams for'],
    ['fat', 'fat', 'Fat grams for'],
  ].forEach(([key, short, label]) => {
    const wrap = document.createElement('label');
    wrap.className = 'macro';

    const caption = document.createElement('span');
    caption.setAttribute('aria-hidden', 'true');
    caption.textContent = short;

    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0';
    input.step = '0.1';
    input.value = String(item[key]);
    input.setAttribute('aria-label', `${label} ${item.name}`);
    input.addEventListener('input', () => {
      item[key] = num(input.value);
      markDirty();
      recompute();
    });

    wrap.append(caption, input);
    row.appendChild(wrap);
  });

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'row__remove';
  remove.innerHTML = '&times;';
  remove.setAttribute('aria-label', `Remove ${item.name}`);
  remove.addEventListener('click', () => {
    state.items.splice(index, 1);
    if (state.items.length === 0) {
      state.estimateReady = false;
      syncPanels();
      return;
    }
    paintRows();
    markDirty();
  });
  row.appendChild(remove);

  return row;
}

function recompute() {
  const totals = state.items.reduce((acc, item) => {
    acc.calories += num(item.calories);
    acc.protein += num(item.protein);
    acc.carbs += num(item.carbs);
    acc.fat += num(item.fat);
    return acc;
  }, { calories: 0, protein: 0, carbs: 0, fat: 0 });

  el.totalCalories.textContent = fmt0(totals.calories);
  el.totalProtein.textContent = fmt1(totals.protein);
  el.totalCarbs.textContent = fmt1(totals.carbs);
  el.totalFat.textContent = fmt1(totals.fat);
  el.totalsNote.textContent = `${state.items.length} item${state.items.length === 1 ? '' : 's'}`;

  const energy = totals.protein * 4 + totals.carbs * 4 + totals.fat * 9;
  const share = (grams, kcalPerGram) => (energy > 0 ? (grams * kcalPerGram) / energy : 0);
  const p = share(totals.protein, 4);
  const c = share(totals.carbs, 4);
  const f = share(totals.fat, 9);
  el.macrobar.querySelector('[data-macro="p"]').style.width = `${(p * 100).toFixed(1)}%`;
  el.macrobar.querySelector('[data-macro="c"]').style.width = `${(c * 100).toFixed(1)}%`;
  el.macrobar.querySelector('[data-macro="f"]').style.width = `${(f * 100).toFixed(1)}%`;
  el.macrobar.setAttribute(
    'aria-label',
    `Macro energy split: protein ${Math.round(p * 100)}%, carbs ${Math.round(c * 100)}%, fat ${Math.round(f * 100)}%`,
  );

  // A hand-typed row has no model call to inspect, so the raw panel previews
  // the payload that Save will actually write instead.
  if (state.manual) {
    estimateParts.raw.textContent = JSON.stringify({ items: state.items }, null, 2);
  }
}

function markDirty() {
  if (state.saved) {
    state.saved = false;
    el.save.textContent = 'Save to journal';
  }
}

/* ---------- recipes ---------- */

function skeletonCards(count) {
  const cards = document.createDocumentFragment();
  for (let i = 0; i < count; i += 1) {
    const card = document.createElement('div');
    card.className = 'recipe';
    const media = document.createElement('div');
    media.className = 'recipe__media';
    media.dataset.state = 'loading';
    const body = document.createElement('div');
    body.className = 'recipe__body';
    [70, 90, 55].forEach((width) => {
      const bar = document.createElement('div');
      bar.className = 'skeleton__bar';
      bar.style.width = `${width}%`;
      body.appendChild(bar);
    });
    card.append(media, body);
    cards.appendChild(card);
  }
  return cards;
}

function renderRecipes(recipes, meta, payload) {
  state.isSample = Boolean(meta && meta.sample);
  el.cookResult.hidden = false;
  el.empty.hidden = true;
  el.cookSub.textContent = state.isSample
    ? `Sample result · ${recipes.length} ideas · not a live model call`
    : `${recipes.length} ideas · per serving, approximate`;
  el.cookNote.textContent = typeof meta.elapsed_ms === 'number' && !state.isSample
    ? `${(meta.elapsed_ms / 1000).toFixed(1)}s`
    : '';

  const cards = recipes.map((recipe, index) => buildRecipeCard(recipe, index, meta));
  el.recipeGrid.replaceChildren(...cards);
  paintInspector(cookParts, meta || {}, payload);
  el.cookTitle.focus({ preventScroll: true });
  reveal(el.cookResult);
}

function buildRecipeCard(recipe, index, meta) {
  const card = document.createElement('article');
  card.className = 'recipe';
  card.dataset.recipeIndex = String(index);

  // Skip the media frame entirely when images are switched off, so cards do not
  // carry an empty "NO IMAGE" strip.
  if (!recipe.image_unavailable) {
    const media = document.createElement('div');
    media.className = 'recipe__media';
    if (recipe.image) {
      const img = document.createElement('img');
      img.src = recipe.image;
      img.alt = recipe.title;
      media.dataset.state = 'ready';
      media.appendChild(img);
    } else if (recipe.image_pending) {
      media.dataset.state = 'loading';
    } else {
      media.dataset.state = 'unavailable';
      media.appendChild(mediaNote('No image'));
    }
    card.appendChild(media);
  }

  const body = document.createElement('div');
  body.className = 'recipe__body';

  const head = document.createElement('div');
  head.className = 'recipe__head';

  const title = document.createElement('h3');
  title.className = 'recipe__title';
  title.textContent = recipe.title;

  const servings = document.createElement('span');
  servings.className = 'recipe__servings';
  servings.textContent = `Serves ${recipe.servings}`;

  head.append(title, servings);

  const desc = document.createElement('p');
  desc.className = 'recipe__desc';
  desc.textContent = recipe.description;

  const nutrition = recipe.nutrition || {};
  const facts = document.createElement('div');
  facts.className = 'recipe__facts';
  [
    [fmt0(nutrition.calories), 'kcal'],
    [fmt1(nutrition.protein), 'P'],
    [fmt1(nutrition.carbs), 'C'],
    [fmt1(nutrition.fat), 'F'],
  ].forEach(([value, unit]) => {
    const fact = document.createElement('span');
    const strong = document.createElement('b');
    strong.textContent = value;
    fact.append(strong, ` ${unit}`);
    facts.appendChild(fact);
  });

  body.append(head, desc, facts);

  const uses = factLine('Uses', recipe.ingredients_used);
  if (uses) body.appendChild(uses);
  const extras = factLine('Extras', recipe.pantry_extras);
  if (extras) body.appendChild(extras);

  if (Array.isArray(recipe.steps) && recipe.steps.length) {
    const wrap = document.createElement('div');
    wrap.className = 'recipe__stepsWrap';
    const steps = document.createElement('ol');
    steps.className = 'recipe__steps';
    steps.tabIndex = 0;
    steps.setAttribute('aria-label', 'Cooking steps');
    recipe.steps.forEach((step) => {
      const li = document.createElement('li');
      li.textContent = step;
      steps.appendChild(li);
    });
    steps.addEventListener('scroll', () => paintStepsOverflow(steps), { passive: true });
    wrap.appendChild(steps);
    body.appendChild(wrap);
    // The steps list is height-capped, so flag whether it is scrolled to the
    // end; the fade that hints at more content is driven by this attribute.
    requestAnimationFrame(() => paintStepsOverflow(steps));
  }

  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'btn recipe__add';
  add.textContent = 'Add to tracker';
  add.disabled = Boolean(meta && meta.sample);
  add.title = add.disabled ? 'Sample data is not added to your journal' : '';
  add.addEventListener('click', () => seedFromRecipe(recipe, meta));
  body.appendChild(add);

  card.appendChild(body);
  return card;
}

function factLine(label, values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const line = document.createElement('p');
  line.className = 'recipe__uses';
  const strong = document.createElement('b');
  strong.textContent = label;
  line.append(strong, values.join(', '));
  return line;
}

function mediaNote(text) {
  const note = document.createElement('span');
  note.className = 'recipe__mediaNote';
  note.textContent = text;
  return note;
}

function paintStepsOverflow(steps) {
  const wrap = steps.parentElement;
  if (!wrap) return;
  const more = steps.scrollHeight - steps.clientHeight - steps.scrollTop > 4;
  wrap.dataset.overflow = more ? 'more' : 'end';
}

function repaintStepsOverflow() {
  el.recipeGrid.querySelectorAll('.recipe__steps').forEach(paintStepsOverflow);
}

async function loadRecipeImage(recipe, index) {
  const media = el.recipeGrid.querySelector(`[data-recipe-index="${index}"] .recipe__media`);
  if (!media) return;

  if (recipe.image_unavailable || !recipe.image_pending) {
    media.dataset.state = 'unavailable';
    media.replaceChildren(mediaNote('No image'));
    return;
  }

  try {
    const response = await fetch(IMAGE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: recipe.title, description: recipe.description }),
    });
    let body = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (!response.ok || !body || !body.image) {
      throw Object.assign(new Error('image failed'), { status: response.status });
    }
    media.dataset.state = 'ready';
    const img = document.createElement('img');
    img.src = body.image;
    img.alt = recipe.title;
    media.replaceChildren(img);
  } catch (err) {
    media.dataset.state = 'unavailable';
    media.replaceChildren(mediaNote(err.status === 503 ? 'Images off' : 'No image'));
  }
}

function seedFromRecipe(recipe, meta) {
  const nutrition = recipe.nutrition || {};
  state.items = [{
    name: recipe.title,
    portion: '1 serving',
    calories: num(nutrition.calories),
    protein: num(nutrition.protein),
    carbs: num(nutrition.carbs),
    fat: num(nutrition.fat),
  }];
  state.estimateReady = true;
  state.isSample = false;
  state.manual = false;
  state.saved = false;
  el.save.disabled = false;
  el.save.textContent = 'Save to journal';
  el.inspectorSummary.textContent = 'Request details';
  el.inspectorRawLabel.textContent = 'Recipe JSON';

  setMode('estimate');
  el.resultSub.textContent = `Seeded from “${recipe.title}” · 1 serving · review before saving`;
  paintRows();
  paintInspector(estimateParts, meta || {}, { recipe });
  el.resultTitle.focus({ preventScroll: true });
  reveal(el.result);
  announce(`Added ${recipe.title} to the estimate table for review.`);
}

/* A hand-typed row. No model call, so the table itself is the input, and the
   path stays open when the provider is unreachable. */
function startManualRow() {
  if (state.busy) return;
  hideError();
  setView('compose');
  renderItems(
    [{ name: '', portion: '', calories: 0, protein: 0, carbs: 0, fat: 0 }],
    { manual: true },
    { items: [{ name: '', portion: '', calories: 0, protein: 0, carbs: 0, fat: 0 }] },
    {
      manual: true,
      sub: 'Manual entry · nothing was sent to the model · review before saving',
      summary: 'Pending save',
      rawLabel: 'Will be saved',
    },
  );
  const first = el.rows.querySelector('.row__name');
  if (first) first.focus({ preventScroll: true });
  announce('Blank row added. Type a name and the numbers, then save.');
}

/* ---------- inspector ---------- */

/* A request in flight has no call detail yet. Clear the last one so a panel
   reopened during the wait cannot present stale numbers as the new result. */
function clearCallDetail(parts) {
  parts.chips.replaceChildren();
  parts.grid.replaceChildren();
  parts.raw.textContent = 'Waiting for the model…';
  parts.copy.textContent = 'Copy';
}

function paintInspector(parts, meta, payload) {
  const chips = [];
  const chip = (label, modifier) => {
    const span = document.createElement('span');
    span.className = `metachip${modifier ? ` metachip--${modifier}` : ''}`;
    span.textContent = label;
    chips.push(span);
  };

  if (meta.sample) chip('sample', 'sample');
  if (meta.model) chip(meta.model);
  if (typeof meta.elapsed_ms === 'number' && !meta.sample) chip(`${fmt0(meta.elapsed_ms)} ms`);
  parts.chips.replaceChildren(...chips);

  const count = Array.isArray(payload && payload.items) ? payload.items.length
    : Array.isArray(payload && payload.recipes) ? payload.recipes.length : null;

  // A hand-typed row has no provider, latency, or token counts to report, so
  // listing them as em dashes would imply a call that never happened.
  const fields = meta.manual
    ? [['items to save', count]]
    : [
      ['provider', meta.provider],
      ['model', meta.model],
      ['latency', typeof meta.elapsed_ms === 'number' ? `${fmt0(meta.elapsed_ms)} ms` : null],
      ['prompt tokens', meta.prompt_tokens],
      ['completion tokens', meta.completion_tokens],
      ['items returned', count],
    ];

  const grid = document.createDocumentFragment();
  fields.forEach(([label, value]) => {
    const wrap = document.createElement('div');
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = label;
    dd.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
    wrap.append(dt, dd);
    grid.appendChild(wrap);
  });
  parts.grid.replaceChildren(grid);
  parts.raw.textContent = JSON.stringify(payload, null, 2);
  parts.copy.textContent = 'Copy';
}

function wireCopy(parts) {
  parts.copy.addEventListener('click', async () => {
    const text = parts.raw.textContent || '';
    try {
      await navigator.clipboard.writeText(text);
      parts.copy.textContent = 'Copied';
    } catch {
      parts.copy.textContent = 'Copy failed';
    }
    setTimeout(() => { parts.copy.textContent = 'Copy'; }, 1600);
  });
}

wireCopy(estimateParts);
wireCopy(cookParts);

/* ---------- journal store ---------- */

/* The journal lives in the server's data.json rather than in this browser, so
   the Journal view, the legacy journal, and the CLI all read one document.
   journal-client.js holds the calls; every one of them answers with the whole
   store, so the copy below is always whatever the server last saved. */

let journal = { calorie_goal: 2000, entries: [] };let journalLoaded = false;
let journalError = '';
let migrated = false;
let saving = false;

function applyDoc(doc) {
  journal = {
    calorie_goal: num(doc && doc.calorie_goal) || 2000,
    entries: Array.isArray(doc && doc.entries) ? doc.entries : [],
  };
  journalLoaded = true;
  return journal;
}

async function loadJournal() {
  try {
    applyDoc(await JournalStore.read());
    journalError = '';
  } catch (error) {
    journalLoaded = false;
    journalError = error.message || 'The journal is unavailable.';
    return;
  }
  if (migrated) return;
  migrated = true;
  try {
    const claim = await JournalStore.claimBrowserEntries(journal);
    if (claim.document) applyDoc(claim.document);
    if (claim.moved) {
      announce(`Moved ${claim.moved} ${claim.moved === 1 ? 'entry' : 'entries'} from this browser to the server.`);
    }
    if (claim.skipped) {
      announce(`${claim.skipped} ${claim.skipped === 1 ? 'entry' : 'entries'} saved by the earlier version `
        + 'of this page could not be read, so they were left in this browser.');
    }
  } catch (error) {
    announce(`Entries saved in this browser could not be moved to the server: ${error.message}`);
  }
}

el.save.addEventListener('click', async () => {
  if (saving || state.saved || state.isSample || state.items.length === 0) return;

  const blank = state.items.findIndex((item) => !String(item.name || '').trim());
  if (blank !== -1) {
    showError('Name every row', `Row ${blank + 1} needs a food name before it can be saved.`, false);
    const input = el.rows.querySelectorAll('.row__name')[blank];
    if (input) input.focus();
    return;
  }

  const date = localDateISO();
  const meal = el.meal.value;
  const entries = state.items.map((item) => ({
    name: String(item.name).trim(),
    calories: num(item.calories),
    protein: num(item.protein),
    carbs: num(item.carbs),
    fat: num(item.fat),
    meal,
    date,
  }));

  saving = true;
  el.save.disabled = true;
  el.save.textContent = 'Saving…';
  try {
    applyDoc(await JournalStore.addEntries(entries));
  } catch (error) {
    saving = false;
    el.save.disabled = false;
    el.save.textContent = 'Save to journal';
    showError('Could not save', `${error.message} The rows are still here, so nothing was lost.`, false);
    return;
  }
  saving = false;
  state.saved = true;
  el.save.textContent = `Saved ${state.items.length} to journal`;
  announce(`Saved ${state.items.length} items to ${meal} on ${date}.`);
  renderJournal();
});

/* ---------- journal ---------- */

function groupEntries(entries, query) {
  const q = String(query || '').trim().toLowerCase();
  const days = new Map();
  entries
    .filter((entry) => {
      if (!q) return true;
      return String(entry.name || '').toLowerCase().includes(q)
        || String(entry.meal || '').toLowerCase().includes(q);
    })
    .forEach((entry) => {
      const date = entry.date || 'undated';
      if (!days.has(date)) days.set(date, []);
      days.get(date).push(entry);
    });
  return Array.from(days.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, list]) => ({
      date,
      entries: list,
      calories: list.reduce((total, entry) => total + num(entry.calories), 0),
    }));
}

function buildEntryRow(entry) {
  const row = document.createElement('div');
  row.className = 'entryrow';

  const meal = document.createElement('span');
  meal.className = 'entryrow__meal';
  meal.textContent = cap(entry.meal || '');

  const main = document.createElement('div');
  main.className = 'entryrow__main';

  const name = document.createElement('span');
  name.className = 'entryrow__name';
  name.textContent = entry.name || 'Untitled';

  const macros = document.createElement('span');
  macros.className = 'entryrow__macros';
  macros.textContent = `P ${fmt1(entry.protein)} · C ${fmt1(entry.carbs)} · F ${fmt1(entry.fat)}`;

  main.append(name, macros);

  const calories = document.createElement('span');
  calories.className = 'entryrow__cal';
  calories.appendChild(document.createTextNode(fmt0(entry.calories)));
  const unit = document.createElement('small');
  unit.textContent = 'kcal';
  calories.appendChild(unit);

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'entryrow__remove';
  remove.innerHTML = '&times;';
  remove.setAttribute('aria-label', `Delete ${entry.name} from ${entry.date}`);
  remove.addEventListener('click', () => deleteEntry(entry));

  row.append(meal, main, calories, remove);
  return row;
}

function buildDay(group) {
  const day = document.createElement('section');
  day.className = 'day';

  const head = document.createElement('header');
  head.className = 'day__head';

  const date = document.createElement('span');
  date.className = 'day__date';
  date.textContent = group.date === 'undated'
    ? 'Undated'
    : `${dayLabel(group.date)} · ${shortDate(group.date)}`;

  const count = group.entries.length;
  const total = document.createElement('span');
  total.className = 'day__total';
  total.textContent = `${count} ${count === 1 ? 'entry' : 'entries'} · ${fmt0(group.calories)} kcal`;

  head.append(date, total);
  day.appendChild(head);
  group.entries.forEach((entry) => day.appendChild(buildEntryRow(entry)));
  return day;
}

async function deleteEntry(entry) {
  if (!window.confirm(`Delete "${entry.name}" (${entry.date})? This cannot be undone.`)) return;
  try {
    applyDoc(await JournalStore.removeEntry(entry.id));
  } catch (error) {
    showError('Could not delete', error.message || 'The journal is unavailable.', false);
    return;
  }
  renderJournal();
  announce(`Deleted ${entry.name}.`);
}

function renderJournal() {
  const goal = num(journal.calorie_goal) || 2000;
  const today = localDateISO();
  const todayEntries = journal.entries.filter((entry) => entry.date === today);
  const totals = todayEntries.reduce((acc, entry) => {
    acc.calories += num(entry.calories);
    acc.protein += num(entry.protein);
    acc.carbs += num(entry.carbs);
    acc.fat += num(entry.fat);
    return acc;
  }, { calories: 0, protein: 0, carbs: 0, fat: 0 });

  const percent = goal > 0 ? Math.min(100, (totals.calories / goal) * 100) : 0;
  const remaining = goal - totals.calories;
  const saved = journal.entries.length;

  el.journalSub.textContent = journalLoaded
    ? `${saved} ${saved === 1 ? 'entry' : 'entries'} saved · ${longDate(today)}`
    : 'Loading the journal…';
  el.todayCalories.textContent = fmt0(totals.calories);
  el.todayGoal.textContent = fmt0(goal);
  el.todayBar.style.width = `${percent.toFixed(1)}%`;
  el.todayBarWrap.setAttribute('aria-valuenow', String(Math.round(percent)));
  el.todayPct.textContent = `${Math.round(percent)}% of goal`;
  el.todayRemaining.textContent = remaining >= 0 ? `${fmt0(remaining)} left` : `${fmt0(-remaining)} over`;
  el.todayProtein.textContent = `${fmt1(totals.protein)} g`;
  el.todayCarbs.textContent = `${fmt1(totals.carbs)} g`;
  el.todayFat.textContent = `${fmt1(totals.fat)} g`;
  el.todayCount.textContent = String(todayEntries.length);

  if (document.activeElement !== el.goalInput) el.goalInput.value = String(goal);

  const groups = journalLoaded ? groupEntries(journal.entries, el.journalSearch.value) : [];
  el.journalDays.replaceChildren(...groups.map(buildDay));

  const searching = Boolean(el.journalSearch.value.trim());
  el.journalEmpty.hidden = groups.length > 0;

  if (!journalLoaded) {
    el.journalEmptyLabel.textContent = 'Loading the journal…';
    el.journalEmptyText.textContent = 'Reading your saved entries from the server.';
  } else if (journalError) {
    el.journalEmptyLabel.textContent = 'The journal is out of reach';
    el.journalEmptyText.textContent = journalError;
  } else if (searching) {
    el.journalEmptyLabel.textContent = 'No entries match that search';
    el.journalEmptyText.textContent = 'Try a different food name or meal.';
  } else {
    el.journalEmptyLabel.textContent = 'Nothing saved yet';
    el.journalEmptyText.textContent = 'Compose a meal or a recipe and save it, and it lands here. You can also add a row by hand.';
  }
}

async function saveGoal() {
  const value = Number(el.goalInput.value);
  if (!Number.isFinite(value) || value < 1) {
    el.goalStatus.textContent = 'Enter a goal of at least 1 calorie.';
    el.goalInput.focus();
    return;
  }
  el.goalStatus.textContent = 'Saving…';
  try {
    applyDoc(await JournalStore.setGoal(Math.round(value)));
  } catch (error) {
    el.goalStatus.textContent = `Could not save the goal: ${error.message}`;
    return;
  }
  el.goalStatus.textContent = `Goal set to ${fmt0(journal.calorie_goal)} calories a day.`;
  renderJournal();
  announce(`Daily goal set to ${fmt0(journal.calorie_goal)} calories.`);
}

el.journalSearch.addEventListener('input', renderJournal);
el.saveGoal.addEventListener('click', saveGoal);
el.goalInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    saveGoal();
  }
});
document.querySelectorAll('[data-goal-preset]').forEach((button) => {
  button.addEventListener('click', () => {
    el.goalInput.value = button.dataset.goalPreset;
    el.goalInput.focus();
  });
});

/* ---------- samples ---------- */

const SAMPLE_MEAL = {
  items: [
    { name: 'Roti (whole wheat)', portion: '2 medium', calories: 224, protein: 7.4, carbs: 43.2, fat: 3.6 },
    { name: 'Dal (toor)', portion: '1 bowl (200 ml)', calories: 180, protein: 9.5, carbs: 26, fat: 4.2 },
    { name: 'Lassi (sweet)', portion: '1 glass (250 ml)', calories: 165, protein: 6.8, carbs: 21.5, fat: 5.9 },
  ],
  totals: { calories: 569, protein: 23.7, carbs: 90.7, fat: 13.7 },
  meta: { provider: 'sample', model: 'sample/fixture', elapsed_ms: 0, prompt_tokens: null, completion_tokens: null, sample: true },
};

const SAMPLE_RECIPES = {
  recipes: [
    {
      title: 'Rice & Egg Skillet of Questionable Confidence',
      description: 'A weekday rescue mission that tastes like you planned it.',
      ingredients_used: ['cooked rice', '2 eggs', 'half a bell pepper'],
      pantry_extras: ['oil', 'salt', 'soy sauce'],
      steps: [
        'Heat a wide pan with a little oil until it shimmers.',
        'Fry the pepper for two minutes, then add the rice and press it flat.',
        'Push everything aside, scramble the eggs in the gap, then fold together.',
        'Season, taste, and resist eating from the pan.',
      ],
      servings: 2,
      nutrition: { calories: 412, protein: 16.4, carbs: 48.2, fat: 15.1 },
      image_pending: false,
      image_unavailable: true,
    },
    {
      title: 'Spinach That Finally Gets Eaten',
      description: 'A green-heavy bowl for the spinach you bought with good intentions.',
      ingredients_used: ['spinach', 'cooked rice', '2 eggs'],
      pantry_extras: ['garlic', 'chilli flakes', 'lemon'],
      steps: [
        'Wilt the spinach in a hot pan with garlic.',
        'Fold through the rice and warm it back up.',
        'Top with a soft-boiled or fried egg.',
        'Finish with lemon and chilli flakes.',
      ],
      servings: 2,
      nutrition: { calories: 365, protein: 18.2, carbs: 39.8, fat: 13.4 },
      image_pending: false,
      image_unavailable: true,
    },
    {
      title: 'Bell Pepper Confetti Bowl',
      description: 'Crunchy, bright, and forgiving of whatever else is in the fridge.',
      ingredients_used: ['half a bell pepper', 'cooked rice', '2 eggs'],
      pantry_extras: ['yogurt', 'cumin', 'salt'],
      steps: [
        'Dice the pepper small enough that it disappears into the rice.',
        'Toast cumin in oil, add the pepper, and cook until soft.',
        'Stir in the rice, then fold in a spoon of yogurt off the heat.',
        'Top with a jammy egg and season aggressively.',
      ],
      servings: 2,
      nutrition: { calories: 388, protein: 17.1, carbs: 44.6, fat: 14.8 },
      image_pending: false,
      image_unavailable: true,
    },
  ],
  meta: { provider: 'sample', model: 'sample/fixture', elapsed_ms: 0, prompt_tokens: null, completion_tokens: null, sample: true },
};

function showSample(mode) {
  hideError();
  if (mode === 'cook') {
    state.cookReady = true;
    state.cookRecipes = SAMPLE_RECIPES.recipes;
    el.text.value = 'cooked rice, 2 eggs, half a bell pepper';
    renderRecipes(SAMPLE_RECIPES.recipes, SAMPLE_RECIPES.meta, SAMPLE_RECIPES);
    announce('Sample recipes loaded. Nothing was sent to the model.');
  } else {
    state.estimateReady = true;
    el.text.value = '2 rotis, dal, and a glass of lassi';
    renderItems(SAMPLE_MEAL.items, SAMPLE_MEAL.meta, SAMPLE_MEAL);
    announce('Sample result loaded. Nothing was sent to the model.');
  }
  updateCount();
  syncPanels();
}

/* ---------- boot ---------- */

el.resultTitle.tabIndex = -1;
el.cookTitle.tabIndex = -1;

// Card widths change with the grid, which changes how far the step lists
// scroll, so recheck the overflow fade whenever the layout reflows.
let stepsReflowFrame = 0;
window.addEventListener('resize', () => {
  if (stepsReflowFrame) return;
  stepsReflowFrame = requestAnimationFrame(() => {
    stepsReflowFrame = 0;
    repaintStepsOverflow();
  });
});

async function boot() {
  const params = new URLSearchParams(location.search);
  const initialMode = params.get('sample') === 'cook'
    ? 'cook'
    : (COPY[params.get('mode')] ? params.get('mode') : 'estimate');
  setMode(initialMode);
  if (params.has('sample')) {
    showSample(params.get('sample') === 'cook' ? 'cook' : 'estimate');
  }
  setView(params.get('view') === 'journal' ? 'journal' : 'compose');
  updateCount();

  await loadJournal();
  renderJournal();
}

boot();
