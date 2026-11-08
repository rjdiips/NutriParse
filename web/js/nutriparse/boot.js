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

  // The journal does not depend on the model settings, so it renders at once;
  // the request timeouts arrive a moment later from the server.
  state.configReady = Config.load().then((config) => {
    state.config = config;
    if (config.source === 'fallback') {
      el.configNoticeMsg.textContent = Config.describeFallback(config);
      el.configNotice.hidden = false;
    }
  });

  await loadJournal();
  renderJournal();
  await state.configReady;
}

boot();
