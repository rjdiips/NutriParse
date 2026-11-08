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

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), requestTiming('image').waitMs);
  try {
    const response = await fetch(IMAGE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: recipe.title, description: recipe.description }),
      signal: controller.signal,
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
    const note = err.name === 'AbortError' ? 'Image timed out'
      : err.status === 503 ? 'Images off' : 'No image';
    media.replaceChildren(mediaNote(note));
  } finally {
    clearTimeout(timer);
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
  // This panel reports the Cook call that produced the recipe, not an
  // Estimate call, so its timeout rows do not belong here.
  const recipeMeta = { ...(meta || {}) };
  ['timeout_ms', 'wait_ms', 'image_timeout_ms', 'image_wait_ms']
    .forEach((key) => { delete recipeMeta[key]; });
  paintInspector(estimateParts, recipeMeta, { recipe });
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

