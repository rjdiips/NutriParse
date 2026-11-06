# NutriParse

The language of the browser-facing nutrition app and the journal it reads and writes.

## Language

**Web app**:
The browser-facing NutriParse application served by the local backend. It consists of Compose and the Food Journal.
_Avoid_: CLI, front end, UI

**Compose**:
The prompt-first surface that turns meal text into editable nutrition rows or ingredient lists into recipes.
_Avoid_: Home, main page

**Estimate**:
The Compose intent that turns a meal description into one editable row per food.
_Avoid_: Parse, suggest

**Cook**:
The Compose intent that turns an ingredient list into three recipe ideas with per-serving macros.
_Avoid_: Recipe generator, leftovers

**Journal store**:
The single persisted document containing the calorie goal and every saved entry.
_Avoid_: Database, data file

**Journal**:
The read side of the journal store inside Compose, showing today's totals and history by day.
_Avoid_: Journal view, diary, history page

**Food Journal**:
The standalone browser page that reads and writes the same journal store as Compose.
_Avoid_: Second app, separate journal

**Entry**:
One saved food row with a name, portion, calories, macros, meal, and date.
_Avoid_: Item, record
