#!/usr/bin/env python3
"""Score /api/parse against a fixed set of meals with reference calorie ranges.

The model has a known tendency to under-count: "2 rotis" comes back around
140 kcal, rice with two eggs around 245-320 kcal. One-off observations like that
are anecdotes. This harness turns them into a number by running the same cases
every time and comparing each one with a range drawn from standard food
composition data.

    python evals/run_parse_eval.py                 # run every case, write results
    python evals/run_parse_eval.py --only one-banana
    python evals/run_parse_eval.py --repeat 3      # measure run-to-run spread
    python evals/run_parse_eval.py --check-fixtures

It writes evals/results.md (the readable table) and evals/results.json (the raw
record, including every item the model returned). Both are meant to be
committed: the numbers are a snapshot tied to a model and a date, and the
caveats at the bottom of results.md say so.
"""

import argparse
import json
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from store import number  # noqa: E402 - the path insert above has to come first

CASES_FILE = EVAL_DIR / "cases" / "parse_cases.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8100"
PARSE_PATH = "/api/parse"


# --------------------------------------------------------------- fixtures

def load_cases(path=CASES_FILE):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def fixture_problems(fixture):
    """Everything wrong with the case file, as a list of readable strings."""
    problems = []
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["cases must be a non-empty list"]

    seen = set()
    for index, case in enumerate(cases, 1):
        where = f"case {index} ({case.get('id', 'no id')})"
        if not isinstance(case, dict):
            problems.append(f"{where}: not an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            problems.append(f"{where}: needs an id")
        elif case_id in seen:
            problems.append(f"{where}: duplicate id")
        else:
            seen.add(case_id)
        if not isinstance(case.get("text"), str) or not case["text"].strip():
            problems.append(f"{where}: needs text to send")
        if not isinstance(case.get("basis"), str) or not case["basis"].strip():
            problems.append(f"{where}: needs a basis for its reference values")

        items = case.get("items")
        if case.get("refusal"):
            if items not in ([], None):
                problems.append(f"{where}: a refusal case should not carry reference items")
            continue
        if not isinstance(items, list) or not items:
            problems.append(f"{where}: needs at least one reference item")
            continue
        for item in items:
            label = item.get("label", "unnamed item") if isinstance(item, dict) else "not an object"
            if not isinstance(item, dict):
                problems.append(f"{where}/{label}: not an object")
                continue
            if not isinstance(item.get("label"), str) or not item["label"].strip():
                problems.append(f"{where}: an item has no label")
            match = item.get("match")
            if not isinstance(match, list) or not match or not all(isinstance(t, str) for t in match):
                problems.append(f"{where}/{label}: match must be a non-empty list of strings")
            kcal = item.get("kcal")
            if (not isinstance(kcal, list) or len(kcal) != 2
                    or not all(isinstance(v, (int, float)) for v in kcal)):
                problems.append(f"{where}/{label}: kcal must be [low, high]")
            elif kcal[0] > kcal[1]:
                problems.append(f"{where}/{label}: kcal low is above high")
            elif kcal[0] < 0:
                problems.append(f"{where}/{label}: kcal cannot be negative")
    return problems


def reference_range(case):
    """The case's total range, summed from its item ranges."""
    low = sum(item["kcal"][0] for item in case["items"])
    high = sum(item["kcal"][1] for item in case["items"])
    return float(low), float(high)


# --------------------------------------------------------------- running

def call_parse(base_url, text, timeout):
    body = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        base_url + PARSE_PATH,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, json.loads(raw)
        except json.JSONDecodeError:
            return error.code, {"error": raw}


def score(case, status, payload):
    """Compare one response with the case's reference ranges."""
    record = {
        "id": case["id"],
        "text": case["text"],
        "status": status,
        "error": None,
        "kcal": None,
        "reference": None,
        "delta": None,
        "delta_pct": None,
        "within_range": None,
        "expected_items": len(case["items"]),
        "found_items": 0,
        "items": [],
        "matches": [],
        "meta": None,
    }

    if case.get("refusal"):
        record["refused"] = status != 200
        record["error"] = (payload or {}).get("error") if status != 200 else None
        return record

    if status != 200:
        record["error"] = (payload or {}).get("error") or f"HTTP {status}"
        return record

    items = payload.get("items") or []
    totals = payload.get("totals") or {}
    kcal = number(totals.get("calories"))
    low, high = reference_range(case)
    midpoint = (low + high) / 2

    record["items"] = [
        {"name": item.get("name"), "portion": item.get("portion"), "kcal": number(item.get("calories"))}
        for item in items if isinstance(item, dict)
    ]
    record["kcal"] = kcal
    record["reference"] = [low, high]
    record["delta"] = kcal - midpoint
    record["delta_pct"] = 100 * (kcal - midpoint) / midpoint if midpoint else None
    record["within_range"] = low <= kcal <= high
    record["meta"] = payload.get("meta")

    for reference_item in case["items"]:
        tokens = [token.lower() for token in reference_item["match"]]
        hits = [item for item in record["items"]
                if any(token in str(item["name"] or "").lower() for token in tokens)]
        found = sum(item["kcal"] for item in hits) if hits else None
        item_low, item_high = reference_item["kcal"]
        record["matches"].append({
            "label": reference_item["label"],
            "tokens": reference_item["match"],
            "kcal": found,
            "reference": [float(item_low), float(item_high)],
            "within_range": bool(hits) and item_low <= found <= item_high,
            "names": [item["name"] for item in hits],
        })

    record["found_items"] = sum(1 for match in record["matches"] if match["kcal"] is not None)
    return record


def aggregate(records):
    """Headline numbers, keeping refusals and errors out of the calorie maths."""
    scored = [r for r in records if r["within_range"] is not None]
    refusals = [r for r in records if r.get("refused") is not None]
    errored = [r for r in records if (r["within_range"] is None and not r.get("refused"))]

    def mean(values):
        return sum(values) / len(values) if values else None

    deltas = [r["delta"] for r in scored]
    percentages = [abs(r["delta_pct"]) for r in scored if r["delta_pct"] is not None]
    signed_percentages = [r["delta_pct"] for r in scored if r["delta_pct"] is not None]
    latencies = [number((r["meta"] or {}).get("elapsed_ms")) for r in scored if r["meta"]]
    prompt_tokens = [number((r["meta"] or {}).get("prompt_tokens")) for r in scored if (r["meta"] or {}).get("prompt_tokens")]
    completion_tokens = [number((r["meta"] or {}).get("completion_tokens")) for r in scored if (r["meta"] or {}).get("completion_tokens")]

    expected_items = sum(r["expected_items"] for r in scored)
    found_items = sum(r["found_items"] for r in scored)
    in_range_items = sum(1 for r in scored for match in r["matches"] if match["within_range"])

    return {
        "cases": len(records),
        "scored": len(scored),
        "within_range": sum(1 for r in scored if r["within_range"]),
        "within_range_rate": mean([1.0 if r["within_range"] else 0.0 for r in scored]),
        "mean_signed_error_kcal": mean(deltas),
        "mean_absolute_error_kcal": mean([abs(d) for d in deltas]),
        "mean_signed_error_pct": mean(signed_percentages),
        "mean_absolute_pct_error": mean(percentages),
        "median_absolute_pct_error": statistics.median(percentages) if percentages else None,
        "items_expected": expected_items,
        "items_found": found_items,
        "items_in_range": in_range_items,
        "mean_latency_ms": mean(latencies),
        "prompt_tokens": sum(prompt_tokens) if prompt_tokens else None,
        "completion_tokens": sum(completion_tokens) if completion_tokens else None,
        "refusal_cases": len(refusals),
        "refusals_ok": sum(1 for r in refusals if r["refused"]),
        "errored": len(errored),
    }


# --------------------------------------------------------------- reporting

def percent(value, digits=1):
    return "n/a" if value is None else f"{value:+.{digits}f}%"


def percent_abs(value, digits=1):
    return "n/a" if value is None else f"{value:.{digits}f}%"


def number_text(value, digits=0):
    return "n/a" if value is None else f"{value:,.{digits}f}"


def case_row(record):
    if record.get("refused"):
        verdict = "refused" if record["refused"] else "should have refused"
        return (f"| `{record['id']}` | {record['text']} | — | — | — | — | — | {verdict} |")
    if record["within_range"] is None:
        return (f"| `{record['id']}` | {record['text']} | — | — | — | — | — | "
                f"error: {record['error']} |")
    low, high = record["reference"]
    return (
        f"| `{record['id']}` | {record['text']} | {record['found_items']}/{record['expected_items']} "
        f"| {number_text(record['kcal'])} | {number_text(low)}–{number_text(high)} "
        f"| {number_text(record['delta'], 0)} | {percent(record['delta_pct'])} "
        f"| {'yes' if record['within_range'] else '**no**'} |"
    )


def item_rows(records):
    rows = []
    for record in records:
        for match in record.get("matches", []):
            low, high = match["reference"]
            if match["kcal"] is None:
                verdict = "**missing**"
                found = "—"
            else:
                found = number_text(match["kcal"])
                verdict = "yes" if match["within_range"] else "**no**"
            rows.append(f"| `{record['id']}` | {match['label']} | {found} | "
                        f"{number_text(low)}–{number_text(high)} | {verdict} |")
    return rows


def drift_lines(records):
    """The misses, biggest absolute calorie gap first.

    Sorted by kcal rather than by percentage: a 20 kcal miss on a 35 kcal coffee
    is a big percentage and a small problem, while 275 kcal on a pizza is not.
    """
    misses = []
    for record in records:
        for match in record.get("matches", []):
            low, high = match["reference"]
            if match["kcal"] is None:
                misses.append((float("inf"), f"`{record['id']}` — {match['label']}: no returned item "
                                             f"matched {', '.join(match['tokens'])}"))
                continue
            if match["within_range"]:
                continue
            midpoint = (low + high) / 2
            gap = match["kcal"] - midpoint
            share = abs(gap) / midpoint * 100 if midpoint else 0.0
            direction = "low" if gap < 0 else "high"
            misses.append((abs(gap), f"`{record['id']}` — {match['label']}: {number_text(match['kcal'])} kcal "
                                     f"vs {number_text(low)}–{number_text(high)}, {number_text(abs(gap))} kcal "
                                     f"{direction} ({share:.0f}% off the midpoint)"))
    misses.sort(key=lambda pair: pair[0], reverse=True)
    return [line for _, line in misses]


def render_markdown(records, summary, run):
    total = summary["scored"]
    lines = [
        "# Meal-parse evaluation",
        "",
        "`/api/parse` scored against fixed meals with reference calorie ranges from standard",
        "food-composition data. Generated by `evals/run_parse_eval.py`; edit the cases rather",
        "than the tables.",
        "",
        "| | |",
        "| --- | --- |",
        f"| Run at | {run['started_at']} |",
        f"| Endpoint | `{run['base_url']}{PARSE_PATH}` |",
        f"| Provider / model | {run['provider']} / {run['model']} |",
        f"| Cases | {summary['cases']} ({summary['scored']} scored, "
        f"{summary['refusal_cases']} refusal check) |",
        f"| Repeats per case | {run['repeat']} |",
        "",
        "## Headline",
        "",
        f"- **Within the reference range: {summary['within_range']}/{total}** "
        f"({(summary['within_range_rate'] or 0) * 100:.0f}% of scored cases)",
        f"- **Mean signed error: {percent(summary['mean_signed_error_pct'])} "
        f"({number_text(summary['mean_signed_error_kcal'])} kcal)** — negative means the model "
        "under-counts",
        f"- Mean absolute error: {number_text(summary['mean_absolute_error_kcal'])} kcal",
        f"- Mean absolute percentage error: {percent_abs(summary['mean_absolute_pct_error'])} "
        f"(median {percent_abs(summary['median_absolute_pct_error'])})",
        f"- Items located: {summary['items_found']}/{summary['items_expected']}, "
        f"of which {summary['items_in_range']} landed in range",
        f"- Refusals: {summary['refusals_ok']}/{summary['refusal_cases']} non-food inputs refused",
        f"- Latency: mean {number_text((summary['mean_latency_ms'] or 0) / 1000, 1)} s per call"
        + (f" · tokens: {number_text(summary['prompt_tokens'])} prompt, "
           f"{number_text(summary['completion_tokens'])} completion"
           if summary["prompt_tokens"] else ""),
        "",
        "## Per case",
        "",
        "| Case | Input | Items found | Model kcal | Reference kcal | Signed error | Error % | In range |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [case_row(record) for record in records]

    lines += [
        "",
        "## Per item",
        "",
        "Where the model split an item into several rows, the rows are summed before the",
        "comparison, so a correct split is not punished.",
        "",
        "| Case | Reference item | Model kcal | Reference kcal | In range |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += item_rows(records) or ["| — | no items were scored | — | — | — |"]

    drift = drift_lines(records)
    lines += [
        "",
        "## Where it drifts",
        "",
    ]
    lines += [f"- {line}" for line in drift] if drift else ["- Every item landed inside its range."]

    if summary["errored"]:
        lines += [
            "",
            f"**{summary['errored']} case(s) returned an error instead of a parse.** See",
            "`results.json` for the message; the endpoint was reachable, so this is a",
            "model or validation failure rather than a missing server.",
        ]

    lines += [
        "",
        "## Caveats",
        "",
        "- The reference ranges are assembled from published composition data (USDA FoodData",
        "  Central, IFCT 2017) and labelled brand values, and are deliberately wide, because a",
        "  free-text portion is not a measurement. Each case carries its own `basis`.",
        "- This is a **snapshot**, not a regression suite: the numbers belong to the model and",
        "  the date in the table above. Re-run it after changing the prompt or the model.",
        "- Generation is not perfectly reproducible even at temperature 0, so treat differences",
        "  of a few percent between runs as noise and the sign of the bias as the finding.",
        "- Percentage error explodes on near-zero items: the black coffee case is ~35 kcal, so a",
        "  10 kcal miss reads as 30%. The median is reported beside the mean for that reason.",
        "- Only calories are scored. The same per-item reference work would be needed to score",
        "  protein, carbs and fat honestly, and macros are not where the drift showed up.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------- entry point

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="server to score")
    parser.add_argument("--only", action="append", default=[], metavar="CASE_ID",
                        help="run just this case (repeatable)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case")
    parser.add_argument("--timeout", type=float, default=120, help="seconds per request")
    parser.add_argument("--out-dir", default=str(EVAL_DIR), help="where to write results")
    parser.add_argument("--check-fixtures", action="store_true",
                        help="validate the case file and exit without calling the model")
    args = parser.parse_args()

    fixture = load_cases()
    problems = fixture_problems(fixture)
    if args.check_fixtures:
        for problem in problems:
            print(f"FAIL  {problem}")
        if problems:
            return 1
        print(f"OK    {len(fixture['cases'])} cases in {CASES_FILE.relative_to(REPO_ROOT)}")
        return 0
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1

    cases = fixture["cases"]
    if args.only:
        wanted = set(args.only)
        cases = [case for case in cases if case["id"] in wanted]
        missing = wanted - {case["id"] for case in cases}
        if missing:
            print(f"No such case: {', '.join(sorted(missing))}")
            return 1
    if args.repeat < 1:
        print("--repeat must be at least 1")
        return 1

    started_at = datetime.now().isoformat(timespec="seconds")
    records = []
    for case in cases:
        for attempt in range(1, args.repeat + 1):
            label = case["id"] if args.repeat == 1 else f"{case['id']}#{attempt}"
            print(f"  {label} ...", end="", flush=True)
            try:
                status, payload = call_parse(args.base_url, case["text"], args.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                print(f" cannot reach {args.base_url} ({error})")
                print("\nStart the server first:  python server.py")
                return 2
            record = score(case, status, payload)
            record["id"] = label
            records.append(record)
            if record.get("refused") is not None:
                print(" refused" if record["refused"] else " INVENTED FOOD")
            elif record["within_range"] is None:
                print(f" error: {record['error']}")
            else:
                mark = "in range" if record["within_range"] else f"{number_text(record['delta'], 0)} kcal off"
                print(f" {number_text(record['kcal'])} kcal ({mark})")

    summary = aggregate(records)
    provider = next((str((r["meta"] or {}).get("provider")) for r in records
                     if (r["meta"] or {}).get("provider")), "unknown")
    model = next((str((r["meta"] or {}).get("model")) for r in records
                  if (r["meta"] or {}).get("model")), "unknown")
    run = {
        "started_at": started_at,
        "base_url": args.base_url,
        "provider": provider,
        "model": model,
        "repeat": args.repeat,
        "cases_file": str(CASES_FILE.relative_to(REPO_ROOT)),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.md").write_text(render_markdown(records, summary, run), encoding="utf-8")
    (out_dir / "results.json").write_text(
        json.dumps({"run": run, "summary": summary, "records": records}, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"within range      {summary['within_range']}/{summary['scored']}")
    print(f"mean signed error {percent(summary['mean_signed_error_pct'])} "
          f"({number_text(summary['mean_signed_error_kcal'])} kcal)")
    print(f"mean abs error    {number_text(summary['mean_absolute_error_kcal'])} kcal "
          f"({percent_abs(summary['mean_absolute_pct_error'])})")
    print(f"written           {out_dir / 'results.md'}")
    print(f"                  {out_dir / 'results.json'}")
    return 1 if summary["errored"] else 0


if __name__ == "__main__":
    sys.exit(main())
