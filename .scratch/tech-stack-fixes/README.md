# Tech stack fixes — ticket index

Source: `.scratch/tech-stack-issues.md` (the remaining-fixes list, items 2–6).
Tracker: local Markdown, because no issue tracker is configured and `gh` is unavailable.

Run one ticket at a time, in numeric order. Do not start a ticket until its blockers are done.

| # | Ticket | Blocked by | Status |
| --- | --- | --- | --- |
| 01 | Typed settings with live reload | None | done |
| 02 | Server-driven AI timeouts | 01 | done |
| 03 | Non-blocking AI and image transport | 01 | done |
| 04 | Cacheable recipe images | 03 | done |
| 05 | JavaScript type-checking prefactor | None | done |
| 06 | Compose page as ES modules | 02, 04, 05 | done |
| 07 | Food Journal as ES modules; retire the classic dependency | 06 | ready-for-agent |

Frontier: 04 and 05 can start now. After 02, 04, and 05: 06. After 06: 07.

Definition of done for every ticket: full unittest suite green, `ruff check --select F` clean, new tests for the ticket's behavior, a manual smoke check where the change is user-visible, and affected docs updated.

## Not in this batch

- Choosing the surviving frontend (frontend consolidation)
- Cross-field plausibility checks and generated client types
- Full CI, Python lint/type-check configuration, and committed browser tests beyond the JavaScript checker
- Deterministic nutrition grounding
- Localhost security and operations hardening
- Optional SQLite migration and document versioning
