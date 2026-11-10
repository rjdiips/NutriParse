# 06: Compose page as ES modules

**What to build:** The Compose page loads one explicit module graph instead of nine ordered classic scripts. The shared journal client exposes an ES-module interface that Compose imports, so load order and implicit globals no longer decide whether the page works. Food Journal keeps working through the existing classic client during this expand step.

**Blocked by:** 02 — Server-driven AI timeouts; 04 — Cacheable recipe images; 05 — JavaScript type-checking prefactor

**Status:** done

**Decisions locked:**
- Use native ES modules; no bundler.
- Give the shared journal client a named ES-module export.
- Keep Food Journal on the classic client for this ticket.
- Load the Compose entry point as a module.
- Do not change visible behavior.

- [x] Compose loads through one module entry graph; there is no ordered chain of classic scripts.
- [x] Compose imports the shared journal client rather than reading a browser global.
- [x] Estimate, Cook, save, journal, search, goal editing, and sample views still work.
- [x] Food Journal still works unchanged on the classic client.
- [x] `npm run check:js` passes.
- [x] A manual browser smoke check of the Compose flows is recorded.

Smoke check recorded in the README's JavaScript type-check section: a headless
Edge/CDP run against a temporary journal covered the sample Estimate and Cook
views, manual-row save, Journal view, search hits and misses, goal editing,
entry deletion, and a clean browser console. No human pass was recorded.
