
import csv
import json
import time
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)

BASE = "https://fantasy.premierleague.com/api"

def fetch(path):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                BASE + path,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(
                req, timeout=20
            ) as response:
                return json.load(response)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError
        ):
            if attempt == 2:
                return None
            time.sleep(attempt + 1)

def save(name, data):
    with (DATA / name).open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(
            data, f,
            ensure_ascii=False,
            indent=2
        )

def main():
    boot = json.loads(
        (DATA / "bootstrap.json").read_text(
            encoding="utf-8"
        )
    )

    finished = sorted(
        e["id"] for e in boot["events"]
        if e.get("finished")
    )

    if not finished:
        raise RuntimeError("No completed GWs")

    # Current overall top 100
    managers = []
    for page in (1, 2):
        result = fetch(
            "/leagues-classic/314/standings/"
            f"?page_standings={page}"
        )
        if not result:
            raise RuntimeError(
                "Overall standings unavailable"
            )
        managers.extend(
            result["standings"]["results"]
        )

    managers = managers[:100]

    if len(managers) != 100:
        raise RuntimeError(
            f"Found {len(managers)} managers"
        )

    cache_file = DATA / "elite100_cache.json"

    if cache_file.exists():
        cache = json.loads(
            cache_file.read_text(encoding="utf-8")
        )
    else:
        cache = {}

    # Include GW9 and GW10 when GW10 finishes.
    # Also retain previous collected history.
    weeks = finished[-3:]

    for manager in managers:
        entry = manager["entry"]
        key = str(entry)
        cache.setdefault(key, {})

        for gw in weeks:
            if str(gw) in cache[key]:
                continue

            result = fetch(
                f"/entry/{entry}/event/{gw}/picks/"
            )

            if not result:
                continue

            picks = result.get("picks", [])

            if len(picks) != 15:
                continue

            cache[key][str(gw)] = {
                "players": [
                    p["element"] for p in picks
                ],
                "captain": next(
                    (
                        p["element"]
                        for p in picks
                        if p.get("is_captain")
                    ),
                    None
                ),
                "chip": result.get("active_chip"),
                "transfers": result.get(
                    "entry_history", {}
                ).get("event_transfers", 0),
                "transfer_cost": result.get(
                    "entry_history", {}
                ).get("event_transfers_cost", 0)
            }

        # Save progressively
        save("elite100_cache.json", cache)

    names = {
        p["id"]: p["web_name"]
        for p in boot["elements"]
    }

    rows = []
    summary = {}

    for gw in weeks:
        ownership = Counter()
        purchases = Counter()
        sales = Counter()
        captains = Counter()

        observed = 0
        compared = 0

        for manager in managers:
            history = cache.get(
                str(manager["entry"]), {}
            )

            current = history.get(str(gw))
            previous = history.get(str(gw - 1))

            if not current:
                continue

            observed += 1

            current_ids = set(
                current["players"]
            )

            ownership.update(current_ids)

            if current["captain"]:
                captains[
                    current["captain"]
                ] += 1

            if previous:
                compared += 1
                previous_ids = set(
                    previous["players"]
                )

                # Exclude chip-driven changes from
                # ordinary transfer statistics.
                if current.get("chip") not in (
                    "wildcard", "freehit"
                ):
                    purchases.update(
                        current_ids - previous_ids
                    )
                    sales.update(
                        previous_ids - current_ids
                    )

        summary[str(gw)] = {
            "managers_observed": observed,
            "managers_compared": compared
        }

        all_ids = (
            set(ownership)
            | set(purchases)
            | set(sales)
            | set(captains)
        )

        for pid in all_ids:
            rows.append({
                "gw": gw,
                "player_id": pid,
                "player": names.get(
                    pid, str(pid)
                ),
                "owned": ownership[pid],
                "bought": purchases[pid],
                "sold": sales[pid],
                "captained": captains[pid]
            })

    rows.sort(
        key=lambda x: (
            x["gw"],
            -x["bought"],
            -x["owned"]
        )
    )

    fields = [
        "gw", "player_id", "player",
        "owned", "bought",
        "sold", "captained"
    ]

    with (
        DATA / "elite100_trends.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)

    save("elite100_summary.json", {
        "cohort": "current_overall_top100",
        "weeks": weeks,
        "coverage": summary,
        "limitations": [
            "Current top 100, not historical top 100",
            "Transfers inferred from published squads",
            "Wildcard and Free Hit excluded",
            "Same-GW reversed transfers invisible"
        ]
    })

    print(json.dumps(
        summary, indent=2
    ))

if __name__ == "__main__":
    main()
