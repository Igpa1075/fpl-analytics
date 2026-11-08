
import json
import time
import urllib.request
from pathlib import Path

DATA = Path("data")
CACHE = DATA / "elite100_cache.json"
SUMMARY = DATA / "elite100_history_summary.json"
API = "https://fantasy.premierleague.com/api"

def fetch(path):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                API + path,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 2:
                print(f"Failed: {path}: {e}")
                return None
            time.sleep(2 * (attempt + 1))

def save(data):
    CACHE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def main():
    if not CACHE.exists():
        raise RuntimeError("Elite 100 cache missing")

    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    managers = list(cache.keys())

    if len(managers) < 100:
        raise RuntimeError("Need at least 100 managers")

    # Backfill historical published squads
    for entry in managers:
        history = cache[entry]

        for gw in range(1, 10):
            if str(gw) in history:
                continue

            result = fetch(
                f"/entry/{entry}/event/{gw}/picks/"
            )

            if not result:
                continue

            picks = result.get("picks", [])

            if len(picks) != 15:
                continue

            history[str(gw)] = {
                "players": [
                    p["element"] for p in picks
                ],
                "captain": next(
                    (p["element"] for p in picks
                     if p.get("is_captain")),
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

        # Persist completed managers
        save(cache)

    coverage = {}
    for gw in range(1, 10):
        coverage[str(gw)] = sum(
            str(gw) in cache[entry]
            for entry in managers
        )

    SUMMARY.write_text(
        json.dumps({
            "cohort": "current_top100",
            "managers": len(managers),
            "coverage": coverage,
            "note": (
                "Historical squads of current leaders, "
                "not historical top-100 rankings."
            )
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(coverage, indent=2))

if __name__ == "__main__":
    main()
