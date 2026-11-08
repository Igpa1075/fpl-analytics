"""Incremental random-ID FPL control cohort; descriptive, not a causal sample."""
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)
OUTPUT = DATA / "control_cohort.json"
BOOTSTRAP = DATA / "bootstrap.json"
API = "https://fantasy.premierleague.com/api"
SEED = 20261108
TARGET = 5000
PER_RUN = 200


def write(data):
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT)


def fetch(entry_id):
    req = urllib.request.Request(
        f"{API}/entry/{entry_id}/",
        headers={"User-Agent": "FPL-research/1.0", "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.load(response), "ok"
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None, "404"
            if exc.code in (403, 429):
                return None, f"http_{exc.code}"
            print(f"HTTP {exc.code} on {entry_id}")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Temporary error on {entry_id}: {exc}")
        time.sleep(2 * (attempt + 1))
    return None, "retry"


def main():
    if OUTPUT.exists():
        state = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if state.get("seed") != SEED or len(state.get("sample_ids", [])) != TARGET:
            raise RuntimeError("Existing cohort parameters differ")
    else:
        boot = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
        upper = int(boot["total_players"])
        if upper < TARGET:
            raise RuntimeError("Unexpected total_players")
        state = {
            "design": "uniform_random_entry_ids",
            "seed": SEED,
            "id_upper_bound_at_creation": upper,
            "sample_ids": random.Random(SEED).sample(range(1, upper + 1), TARGET),
            "results": {},
            "limitations": [
                "Entry IDs are not proven uniformly representative of managers.",
                "ID upper bound is bootstrap total_players, not verified maximum ID.",
                "Registration timing and inactive teams may affect comparisons.",
                "Ranks are measured at collection time, not at a fixed historical cutoff.",
                "Do not infer causality from observational comparisons.",
            ],
        }
        write(state)

    results = state["results"]
    completed = 0
    for entry_id in state["sample_ids"]:
        key = str(entry_id)
        if key in results:
            continue
        if completed >= PER_RUN:
            break
        entry, status = fetch(entry_id)
        if status in ("http_403", "http_429", "retry"):
            print(f"Stopping safely after {status}; will retry next run")
            break
        record = {"status": status}
        if status == "ok":
            record.update({
                "rank": entry.get("summary_overall_rank"),
                "points": entry.get("summary_overall_points"),
                "started_event": entry.get("started_event"),
            })
        results[key] = record
        completed += 1
        if completed % 25 == 0:
            write(state)
        time.sleep(0.4)

    state["summary"] = {
        "target": TARGET,
        "processed": len(results),
        "valid": sum(x["status"] == "ok" for x in results.values()),
        "remaining": TARGET - len(results),
        "complete": len(results) == TARGET,
    }
    write(state)
    print(json.dumps(state["summary"], indent=2))


if __name__ == "__main__":
    main()
