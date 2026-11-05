/* NutriParse — the browser side of the shared journal store.
   Both the Compose page and the Food Journal load this file, so neither of
   them keeps its own copy of the journal. The server owns data.json; every
   call here returns the whole document the server just saved. */

(function (global) {
  const ENDPOINT = '/api/journal';
  const LEGACY_KEY = 'ct_data';
  const LEGACY_MEALS = ['breakfast', 'lunch', 'dinner', 'snack'];
  const MAX_BATCH = 50;
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

  const value = (n) => Math.max(0, Number(n) || 0);

  async function request(method, path, body) {
    const options = {
      method,
      headers: body === undefined
        ? { Accept: 'application/json' }
        : { 'Content-Type': 'application/json', Accept: 'application/json' },
    };
    if (body !== undefined) options.body = JSON.stringify(body);

    const response = await fetch(path, options);
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
    return payload;
  }

  function normalize(document) {
    return {
      calorie_goal: value(document && document.calorie_goal) || 2000,
      entries: document && Array.isArray(document.entries) ? document.entries : [],
    };
  }

  const read = async () => normalize(await request('GET', ENDPOINT));

  const addEntries = async (entries) =>
    normalize(await request('POST', `${ENDPOINT}/entries`, { entries }));

  const updateEntries = async (id, entries) =>
    normalize(await request('PUT', `${ENDPOINT}/entries/${encodeURIComponent(id)}`, { entries }));

  const removeEntry = async (id) =>
    normalize(await request('DELETE', `${ENDPOINT}/entries/${encodeURIComponent(id)}`));

  const setGoal = async (goal) =>
    normalize(await request('POST', `${ENDPOINT}/goal`, { calorie_goal: goal }));

  function readLegacy() {
    try {
      return JSON.parse(localStorage.getItem(LEGACY_KEY));
    } catch {
      return null;
    }
  }

  function forgetLegacy() {
    try {
      localStorage.removeItem(LEGACY_KEY);
    } catch {
      // Storage can be switched off entirely; then there is nothing to move.
    }
  }

  function writeLegacy(document) {
    try {
      localStorage.setItem(LEGACY_KEY, JSON.stringify(document));
    } catch {
      // The entries that did move are already on the server, so this is only tidying up.
    }
  }

  const isMovable = (entry) => Boolean(entry)
    && LEGACY_MEALS.includes(entry.meal)
    && ISO_DATE.test(String(entry.date || ''));

  const asRow = (entry) => ({
    name: String(entry.name || '').trim() || 'Untitled',
    portion: String(entry.portion || '').trim(),
    calories: value(entry.calories),
    protein: value(entry.protein),
    carbs: value(entry.carbs),
    fat: value(entry.fat),
    meal: entry.meal,
    date: entry.date,
  });

  /* Entries saved before the server owned the store live in localStorage.
     Carry them up once so the change does not cost anyone their journal.
     Anything the server would reject stays in the browser rather than being
     dropped, and anything already moved is taken out of the browser copy so a
     second visit cannot migrate the same entry twice. */
  async function claimBrowserEntries(current) {
    const legacy = readLegacy();
    if (!legacy || !Array.isArray(legacy.entries) || legacy.entries.length === 0) {
      forgetLegacy();
      return { moved: 0, skipped: 0, document: null };
    }

    const movable = legacy.entries.filter(isMovable);
    const left = legacy.entries.filter((entry) => !isMovable(entry));
    if (movable.length === 0) {
      return { moved: 0, skipped: left.length, document: null };
    }

    let document = null;
    for (let start = 0; start < movable.length; start += MAX_BATCH) {
      document = await addEntries(movable.slice(start, start + MAX_BATCH).map(asRow));
    }

    const goal = Number(legacy.calorie_goal);
    if (current && current.entries.length === 0 && Number.isFinite(goal) && goal >= 1) {
      try {
        document = await setGoal(Math.round(goal));
      } catch {
        // A goal the server will not accept is worth losing; the entries are not.
      }
    }

    if (left.length) {
      writeLegacy({ calorie_goal: legacy.calorie_goal, entries: left });
    } else {
      forgetLegacy();
    }
    return { moved: movable.length, skipped: left.length, document };
  }

  global.JournalStore = { read, addEntries, updateEntries, removeEntry, setGoal, claimBrowserEntries };
})(window);
