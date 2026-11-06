"""Archive mini-league standings and squads by completed gameweek.

Run after fpl_league.py:
    python fpl_league_history.py

Only uses files already collected by fpl_league.py.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ARCHIVE = DATA / "league_history.json"

def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))

def main():
    standings = read("league_standings.json")
    rivals = read("league_rivals.json")
    gw = standings.get("last_finished_gw")
    if gw is None or rivals.get("gw") != gw:
        raise RuntimeError("Standings and rival squads do not refer to the same finished gameweek.")
    if ARCHIVE.exists():
        archive = read("league_history.json")
    else:
        archive = {"league_id": 492197, "team_id": 5150250, "gameweeks": {}}
    if archive.get("league_id") != 492197 or archive.get("team_id") != 5150250:
        raise RuntimeError("Existing archive belongs to a different league or team.")
    key = str(gw)
    members = standings.get("members", [])
    squads = rivals.get("rivals", [])
    if not members:
        raise RuntimeError("No standings to archive.")
    # Keep previously archived GW data immutable. Current GW data may be
    # re-fetched, but only the first complete snapshot is stored.
    if key not in archive["gameweeks"]:
        archive["gameweeks"][key] = {
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "members": [
                {"entry": m.get("entry"), "team_name": m.get("entry_name"),
                 "rank": m.get("rank"), "total": m.get("total")}
                for m in members
            ],
            "squads": squads,
        }
        ARCHIVE.write_text(
            json.dumps(archive, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"Archived GW{gw}: {len(members)} league teams, {len(squads)} squads.")
    else:
        print(f"GW{gw} already archived; no changes made.")
    print("Archived gameweeks:", ", ".join(sorted(archive["gameweeks"], key=int)))

if __name__ == "__main__":
    main()
