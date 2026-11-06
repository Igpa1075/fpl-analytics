
import csv
import json
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"

def get(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except Exception as e:
        print("ERROR:", path, str(e)[:150])
        return None

events = {}

for offset in range(45):
    day = (date.today() - timedelta(days=offset)).strftime("%Y%m%d")
    data = get("/scoreboard?dates=" + day)
    if not data:
        continue
    for event in data.get("events") or []:
        if event.get("status", {}).get("type", {}).get("completed"):
            events[str(event["id"])] = event

by_team = defaultdict(list)

for event in events.values():
    competition = (event.get("competitions") or [{}])[0]
    for item in competition.get("competitors") or []:
        team_id = str((item.get("team") or {}).get("id") or "")
        if team_id:
            by_team[team_id].append(event)

selected = {}

for matches in by_team.values():
    matches.sort(key=lambda e: e.get("date", ""), reverse=True)
    for event in matches[:5]:
        selected[str(event["id"])] = event

rows = []
diagnostics = []

for event in selected.values():
    summary = get("/summary?event=" + str(event["id"]))
    if not summary:
        continue

    for roster in summary.get("rosters") or []:
        team = (roster.get("team") or {}).get("displayName", "")
        starters = [
            p for p in roster.get("roster") or []
            if p.get("starter") is True
        ]

        diagnostics.append({
            "event_id": event["id"],
            "team": team,
            "starters": len(starters),
            "formation": roster.get("formation"),
            "roster_keys": sorted(roster.keys()),
            "player_keys": sorted(starters[0].keys()) if starters else []
        })

        for player in starters:
            athlete = player.get("athlete") or {}
            rows.append({
                "event_id": event["id"],
                "match_date": event.get("date", ""),
                "team": team,
                "espn_id": athlete.get("id", ""),
                "player": athlete.get("displayName", ""),
                "formation_place": player.get("formationPlace", ""),
                "position_raw": json.dumps(
                    athlete.get("position"), ensure_ascii=False
                ),
                "source_url": BASE + "/summary?event=" + str(event["id"])
            })

Path("data").mkdir(exist_ok=True)

fields = [
    "event_id", "match_date", "team", "espn_id",
    "player", "formation_place", "position_raw", "source_url"
]

with open("data/espn_lineups.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

with open("data/espn_lineup_diagnostics.json", "w", encoding="utf-8") as f:
    json.dump(diagnostics, f, ensure_ascii=False, indent=2)

print("Matches selected:", len(selected))
print("Teams found:", len(by_team))
print("Starter records:", len(rows))
print("Complete starting XIs:",
      sum(d["starters"] == 11 for d in diagnostics),
      "/", len(diagnostics))
print("Diagnostics sample:", json.dumps(diagnostics[:2], ensure_ascii=False))

if not rows:
    raise SystemExit("No lineups collected")
