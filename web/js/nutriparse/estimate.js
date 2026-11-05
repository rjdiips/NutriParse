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

