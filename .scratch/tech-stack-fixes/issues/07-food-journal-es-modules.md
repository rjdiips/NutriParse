# 07: Food Journal as ES modules; retire the classic dependency

**What to build:** Food Journal loads as an ES module and imports the same journal client as Compose. Neither current page depends on the classic browser global. The legacy journal-client URL remains available as a documented compatibility shim for older pages, but the current app no longer loads or relies on it.

**Blocked by:** 06 — Compose page as ES modules

**Status:** done

**Decisions locked:**
- Convert Food Journal to a module and import the shared journal client.
- Remove all current-page use of the classic journal global.
- Keep the legacy journal-client URL working as a compatibility-only shim and document that status.
- Keep the no-bundler workflow.

- [x] Food Journal loads as a module and imports the shared journal client.
- [x] Neither current page reads or writes the classic journal global.
- [x] The legacy journal-client URL still serves classic consumers and is documented as compatibility-only.
- [x] Food Journal flows still work: load, browser-data migration, add, delete, goal editing, search, and day history.
- [x] `npm run check:js` passes without the shared-globals declaration, apart from standard browser globals.
- [x] A manual browser smoke check of Food Journal is recorded.

Smoke check recorded in the README's JavaScript type-check section: a headless
Edge/CDP run against a temporary journal loaded the page through one module
script, confirmed `window.JournalStore` was absent, migrated a browser entry and
its goal, saved a manual row, edited the goal, grouped day history, searched with
a hit and a miss, deleted an entry, and loaded `/journal-client.js` separately to
confirm its forwarding still works. The browser console stayed clean. No human
pass was recorded.
