/* ---------- journal store ---------- */

import {
  el, state, num, fmt0, fmt1, cap, localDateISO, longDate, shortDate, dayLabel,
  announce, showError, registerJournalRenderer,
} from '../nutriparse.js';
import {
  read, addEntries, removeEntry, setGoal, claimBrowserEntries,
} from '../journal-store.js';

/* The journal lives in the server's data.json rather than in this browser, so
   the Compose page's Journal view and the Food Journal read one document.
   journal-store.js holds the calls; every one of them answers with the whole
   store, so the copy below is always whatever the server last saved. */

let journal = { calorie_goal: 2000, entries: [] };
let journalLoaded = false;
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

export async function loadJournal() {
  try {
    applyDoc(await read());
    journalError = '';
  } catch (error) {
    journalLoaded = false;
    journalError = error.message || 'The journal is unavailable.';
    return;
  }
  if (migrated) return;
  migrated = true;
  try {
    const claim = await claimBrowserEntries(journal);
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
    const input = /** @type {HTMLElement | undefined} */ (el.rows.querySelectorAll('.row__name')[blank]);
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
    applyDoc(await addEntries(entries));
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
    applyDoc(await removeEntry(entry.id));
  } catch (error) {
    showError('Could not delete', error.message || 'The journal is unavailable.', false);
    return;
  }
  renderJournal();
  announce(`Deleted ${entry.name}.`);
}

export function renderJournal() {
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
    applyDoc(await setGoal(Math.round(value)));
  } catch (error) {
    el.goalStatus.textContent = `Could not save the goal: ${error.message}`;
    return;
  }
  el.goalStatus.textContent = `Goal set to ${fmt0(journal.calorie_goal)} calories a day.`;
  renderJournal();
  announce(`Daily goal set to ${fmt0(journal.calorie_goal)} calories.`);
}

registerJournalRenderer(renderJournal);
el.journalSearch.addEventListener('input', renderJournal);
el.saveGoal.addEventListener('click', saveGoal);
el.goalInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    saveGoal();
  }
});
/** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('[data-goal-preset]')).forEach((button) => {
  button.addEventListener('click', () => {
    el.goalInput.value = button.dataset.goalPreset;
    el.goalInput.focus();
  });
});
