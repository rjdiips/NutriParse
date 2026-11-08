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

  const timeoutText = (serverMs, waitMs) => (typeof serverMs === 'number'
    ? `${fmt0(serverMs)} ms`
    : `${fmt0(waitMs)} ms (fallback)`);

  if (!meta.manual && typeof meta.wait_ms === 'number') {
    fields.push(['timeout', timeoutText(meta.timeout_ms, meta.wait_ms)]);
    fields.push(['client wait', `${fmt0(meta.wait_ms)} ms`]);
  }
  if (!meta.manual && typeof meta.image_wait_ms === 'number') {
    fields.push(['image timeout', timeoutText(meta.image_timeout_ms, meta.image_wait_ms)]);
  }

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

