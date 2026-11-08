
import json
import random
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)

OUTPUT = DATA / "control_validation.json"
BOOTSTRAP = DATA / "bootstrap.json"

API = "https://fantasy.premierleague.com/api"

SEED = 20261109
SAMPLE_SIZE = 500
DELAY = 0.5


def fetch(entry_id):
    url = f"{API}/entry/{entry_id}/"

    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json"
                }
            )

            with urllib.request.urlopen(
                request, timeout=20
            ) as response:
                return json.load(response), "ok"

        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None, "404"

            if error.code in (403, 429):
                return None, f"http_{error.code}"

        except (
            urllib.error.URLError,
            TimeoutError
        ):
            pass

        time.sleep(2 * (attempt + 1))

    return None, "error"


def save(data):
    temporary = OUTPUT.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temporary.replace(OUTPUT)


def main():
    bootstrap = json.loads(
        BOOTSTRAP.read_text(
            encoding="utf-8"
        )
    )

    total = int(bootstrap["total_players"])

    if OUTPUT.exists():
        state = json.loads(
            OUTPUT.read_text(
                encoding="utf-8"
            )
        )
    else:
        rng = random.Random(SEED)

        ids = rng.sample(
            range(1, total + 1),
            SAMPLE_SIZE
        )

        state = {
            "seed": SEED,
            "id_upper_bound": total,
            "sample_ids": ids,
            "results": {},
            "limitations": [
                "Total players is not verified "
                "as maximum entry ID",
                "Random IDs are not yet proven "
                "representative of all entries",
                "This is a validation sample"
            ]
        }

    results = state["results"]

    for index, entry_id in enumerate(
        state["sample_ids"], 1
    ):
        key = str(entry_id)

        if key in results:
            continue

        entry, status = fetch(entry_id)

        if status in ("http_403", "http_429"):
            print("API restriction detected")
            break

        if status == "error":
            print("Temporary request failure")
            break

        record = {"status": status}

        if status == "ok":
            record.update({
                "rank": entry.get(
                    "summary_overall_rank"
                ),
                "points": entry.get(
                    "summary_overall_points"
                ),
                "started_event": entry.get(
                    "started_event"
                )
            })

        results[key] = record

        if index % 25 == 0:
            save(state)
            print(f"Processed {index}/500")

        time.sleep(DELAY)

    save(state)

    valid = [
        value
        for value in results.values()
        if value["status"] == "ok"
    ]

    ranks = Counter()

    for entry in valid:
        rank = entry.get("rank")

        if rank is None:
            ranks["unranked"] += 1
            continue

        group = min(
            5,
            max(
                1,
                (rank - 1) * 5 // total + 1
            )
        )

        ranks[str(group)] += 1

    summary = {
        "tested": len(results),
        "valid": len(valid),
        "valid_fraction": round(
            len(valid) / max(len(results), 1),
            4
        ),
        "rank_quintiles": dict(ranks),
        "status_counts": dict(
            Counter(
                value["status"]
                for value in results.values()
            )
        )
    }

    state["summary"] = summary
    save(state)

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
