# Parse evaluation

A small, committed harness that scores `/api/parse` against fixed meals with
reference calorie ranges. It exists because "the model under-counts" is an
anecdote until it is measured, and because a prompt change should have something
to compare against.

```
python evals/run_parse_eval.py                  # score every case, write results
python evals/run_parse_eval.py --only one-banana
python evals/run_parse_eval.py --repeat 3       # see run-to-run spread
python evals/run_parse_eval.py --check-fixtures # validate the cases, no network
```

The server has to be running (`python server.py`) and the model provider has to
be reachable, because this calls the real endpoint. `--check-fixtures` is the
exception: it only reads the case file, so it works offline and in CI.

The run writes two files next to this one:

- `results.md` — the readable tables and the headline numbers.
- `results.json` — every case, every item the model returned, every match. This
  is the raw record the tables are built from.

Both are committed on purpose. They are a snapshot of one model on one date, and
the report says so at the top.

## What it measures

Twelve food cases plus one refusal check. For each case it reports:

| Measure | What it means |
| --- | --- |
| Model kcal | `totals.calories` from the response, which the server recomputes from the item rows |
| Reference range | The sum of the case's per-item ranges |
| Signed error | Model minus the midpoint of the reference range; negative means under-counting |
| In range | Whether the model total falls inside the reference range |
| Items found | How many of the case's expected items appear in the returned rows |
| Items in range | Per-item comparison, after summing rows that belong to the same item |

Per-item scoring exists because a meal total can land in range while the items
inside it are wrong in opposite directions. The committed run shows exactly that:
`2 rotis, dal, and a glass of lassi` scores 470 kcal against a 420–650 range, but
the roti row alone is 140 kcal against 180–260.

Rows are matched by lowercased substring against the returned item names, and
matched rows are summed. That way a model that splits "2 rotis" into two rows, or
answers a cheese omelette as `Egg` + `Cheese`, is credited for the split instead
of being marked missing.

`aggregate()` keeps refusals and errors out of the calorie arithmetic, so a
failed call cannot masquerade as a good estimate.

## Why ranges instead of exact values

A free-text portion is not a measurement: "a glass of lassi" is anywhere from 150
to 300 ml, and "a plate of biryani" is not a defined quantity. A single reference
number would look precise and be wrong. Each case carries a `basis` field naming
the components and the composition data they came from (USDA FoodData Central,
IFCT 2017, or a label value where brands differ), and the ranges are wide enough
to cover ordinary variation in portion and preparation.

Where a description leaves cooking fat ambiguous, the range assumes a plain
preparation and the basis says so. That is a limitation, not a hidden
assumption.

## Measuring the bias honestly

The headline numbers from the committed run are easy to over-read, so the report
carries the caveats with them:

- Mean signed error is the bias; mean absolute percentage error is the typical
  size of a miss. Both are reported, plus the median, because percentage error
  explodes near zero — a 20 kcal miss on a 35 kcal coffee reads as 60%.
- Latency and token counts come from the endpoint's `meta` block, so they
  describe the same calls the calories came from.
- Generation is not perfectly reproducible even at `temperature=0`. Differences
  of a few percent between runs are noise; the sign of the bias across items is
  the finding.
- Only calories are scored. Scoring protein, carbs and fat honestly would need
  the same per-item reference work, and the drift showed up in calories first.

## Adding a case

Edit `evals/cases/parse_cases.json` and run `--check-fixtures`. A case is:

```json
{
  "id": "rice-and-two-eggs",
  "text": "leftover rice with two eggs",
  "basis": "One cup of cooked white rice is ~205 kcal; two large eggs are ~143 kcal.",
  "items": [
    { "label": "Cooked rice, 1 cup", "match": ["rice"], "kcal": [180, 260] },
    { "label": "Eggs, 2 large", "match": ["egg"], "kcal": [130, 170] }
  ]
}
```

- `id` must be unique; `--only` takes it.
- `text` is sent to the endpoint verbatim.
- `basis` is required: every number has to be defensible on its own.
- `match` lists the name fragments that identify the item. Add spelling
  variants ("omelette"/"omelet") and the component names a model might use if it
  splits the item.
- `kcal` is `[low, high]` for the portion in `text`, not per 100 g.

A refusal case has `"refusal": true` and no items; it passes when the endpoint
rejects the input instead of inventing a food.

The fixture check catches the mistakes that quietly corrupt results: duplicate
ids, missing text or basis, inverted or negative ranges, and empty `match` lists.
It does not check whether the reference numbers are right — that is a judgement
call, which is why the basis is required.

## When the numbers change

Re-run after changing the parse prompt, the item schema, or the model, and commit
the new `results.md` and `results.json` together with the change. The report's
header records the model and timestamp, so an old table cannot be mistaken for a
current one.

The runner exits `0` when a run completes, even when the model lands outside the
reference range: this measures the model, it does not gate a build. It exits `1`
for a broken fixture or a case that errored, and `2` when the server is not
reachable.
