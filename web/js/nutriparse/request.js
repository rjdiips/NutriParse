/* ---------- request ---------- */

function setBusy(busy, mode = state.mode) {
  state.busy = busy;
  el.parse.disabled = busy;
  el.parse.textContent = busy ? COPY[mode].busy : COPY[state.mode].cta;
  el.parse.setAttribute('aria-busy', busy ? 'true' : 'false');
  /** @type {NodeListOf<HTMLButtonElement>} */ (document.querySelectorAll('.mode')).forEach((button) => {
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

  // A very early click must use the server's values, not the safety net.
  if (state.configReady) await state.configReady;

  const controller = new AbortController();
  const kind = mode === 'cook' ? 'cook' : 'parse';
  const timeout = requestTiming(kind).waitMs;
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
      renderRecipes(
        payload.recipes,
        timeoutMeta(payload.meta || {}, 'cook', true),
        payload,
      );
      announce(`${payload.recipes.length} recipes ready.`);
      payload.recipes.forEach((recipe, index) => loadRecipeImage(recipe, index));
    } else {
      if (!payload || !Array.isArray(payload.items)) {
        throw Object.assign(new Error('The service returned an unexpected response.'), { status: 502 });
      }
      state.isSample = false;
      state.estimateReady = true;
      renderItems(
        payload.items,
        timeoutMeta(payload.meta || {}, 'parse'),
        payload,
      );
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

