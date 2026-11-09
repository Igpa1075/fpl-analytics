"""Incrementally collect FPL player match histories for GW1-10.

Usage:
  python fpl_historical_players.py --limit 40
  python fpl_historical_players.py --limit 100
Each run resumes from data/historical_players_gw1_10.json.
Match 'value' is a fixture-time value, NOT verified pre-deadline price.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
API = "https://fantasy.premierleague.com/api"
OUTPUT = DATA / "historical_players_gw1_10.json"


def fetch(path):
    req = urllib.request.Request(API + path, headers={
        "User-Agent": "FPL-historical-backtest/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def save(state):
    DATA.mkdir(exist_ok=True)
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temp.replace(OUTPUT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--delay", type=float, default=0.35)
    args = parser.parse_args()
    if args.limit < 1 or args.delay < 0:
        parser.error("limit must be positive and delay nonnegative")

    boot_path = DATA / "bootstrap.json"
    if boot_path.exists():
        bootstrap = json.loads(boot_path.read_text(encoding="utf-8"))
    else:
        bootstrap = fetch("/bootstrap-static/")
    ids = sorted(int(p["id"]) for p in bootstrap["elements"])
    if OUTPUT.exists():
        state = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        state = {"season": "2026/27", "gws": list(range(1, 11)),
                 "price_semantics": "fixture-time value; not deadline purchase price",
                 "players": {}, "errors": {}}

    completed = 0
    for pid in ids:
        key = str(pid)
        if key in state["players"]:
            continue
        try:
            summary = fetch(f"/element-summary/{pid}/")
            matches = []
            for row in summary.get("history", []):
                gw = row.get("round")
                if isinstance(gw, int) and 1 <= gw <= 10:
                    matches.append({
                        "fixture": row.get("fixture"),
                        "gw": gw,
                        "kickoff_time": row.get("kickoff_time"),
                        "minutes": row.get("minutes"),
                        "total_points": row.get("total_points"),
                        "value_at_fixture": row.get("value"),
                        "was_home": row.get("was_home"),
                        "opponent_team": row.get("opponent_team"),
                        "selected": row.get("selected"),
                        "transfers_in": row.get("transfers_in"),
                        "transfers_out": row.get("transfers_out"),
                    })
            state["players"][key] = matches
            state["errors"].pop(key, None)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            state["errors"][key] = str(exc)
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                save(state)
                raise RuntimeError("FPL rate limit; progress saved") from exc
        completed += 1
        if completed % 10 == 0:
            save(state)
        if completed >= args.limit:
            break
        time.sleep(args.delay)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["completed_players"] = len(state["players"])
    state["total_players"] = len(ids)
    save(state)
    print(json.dumps({"completed_players": len(state["players"]),
                      "total_players": len(ids),
                      "errors": len(state["errors"]),
                      "new_attempts": completed}, indent=2))


if __name__ == "__main__":
    main()
