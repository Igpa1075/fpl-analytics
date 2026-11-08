
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)

CACHE = DATA / "elite100_cache.json"
COHORT = DATA / "elite100_cohort.json"
SUMMARY = DATA / "elite100_history_summary.json"

API = "https://fantasy.premierleague.com/api"


def fetch(path):
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                API + path,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json"
                }
            )

            with urllib.request.urlopen(
                request, timeout=25
            ) as response:
                return json.load(response)

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError
        ) as error:
            print(
                f"Attempt {attempt + 1}: "
                f"{path}: {error}"
            )

            if attempt < 2:
                time.sleep(2 * (attempt + 1))

    return None


def save_json(path, data):
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def load_cohort():
    if COHORT.exists():
        data = json.loads(
            COHORT.read_text(encoding="utf-8")
        )

        managers = [
            str(entry)
            for entry in data["manager_ids"]
        ]

        if (
            len(managers) != 100
            or len(set(managers)) != 100
        ):
            raise RuntimeError(
                "Saved cohort must contain "
                "100 unique managers"
            )

        return managers

    managers = []

    for page in (1, 2):
        result = fetch(
            "/leagues-classic/314/standings/"
            f"?page_standings={page}"
        )

        if not result:
            raise RuntimeError(
                "Cannot load overall standings"
            )

        managers.extend(
            str(manager["entry"])
            for manager in result["standings"]["results"]
        )

    managers = list(
        dict.fromkeys(managers)
    )[:100]

    if len(managers) != 100:
        raise RuntimeError(
            f"Expected 100 managers, "
            f"received {len(managers)}"
        )

    save_json(
        COHORT,
        {
            "cohort": "fixed_overall_top100",
            "manager_ids": managers
        }
    )

    return managers


def main():
    if not CACHE.exists():
        raise RuntimeError(
            "elite100_cache.json not found"
        )

    cache = json.loads(
        CACHE.read_text(encoding="utf-8")
    )

    managers = load_cohort()

    print(
        f"Tracking {len(managers)} "
        "fixed elite managers"
    )

    # Backfill historical squads GW1-GW9
    for index, entry in enumerate(managers, 1):
        history = cache.setdefault(entry, {})

        for gw in range(1, 10):
            key = str(gw)

            if key in history:
                continue

            result = fetch(
                f"/entry/{entry}/event/{gw}/picks/"
            )

            if not result:
                continue

            picks = result.get("picks", [])

            if len(picks) != 15:
                continue

            history[key] = {
                "players": [
                    player["element"]
                    for player in picks
                ],
                "captain": next(
                    (
                        player["element"]
                        for player in picks
                        if player.get("is_captain")
                    ),
                    None
                ),
                "chip": result.get(
                    "active_chip"
                ),
                "transfers": result.get(
                    "entry_history", {}
                ).get("event_transfers", 0),
                "transfer_cost": result.get(
                    "entry_history", {}
                ).get("event_transfers_cost", 0)
            }

        # Preserve progress
        save_json(CACHE, cache)

        if index % 10 == 0:
            print(
                f"Processed {index}/100 managers"
            )

    coverage = {}

    for gw in range(1, 10):
        coverage[str(gw)] = sum(
            str(gw) in cache.get(entry, {})
            for entry in managers
        )

    summary = {
        "cohort": "fixed_overall_top100",
        "managers": len(managers),
        "gameweeks": list(range(1, 10)),
        "coverage": coverage,
        "complete": all(
            count == 100
            for count in coverage.values()
        ),
        "limitations": [
            "Current top-100 cohort fixed at first run",
            "Not historical top-100 per gameweek",
            "Squads are published FPL picks",
            "Transfers inferred from squad changes"
        ]
    }

    save_json(SUMMARY, summary)

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
