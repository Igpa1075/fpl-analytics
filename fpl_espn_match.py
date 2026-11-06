
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

DATA = Path("data")

def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())

with open(DATA / "bootstrap.json", encoding="utf-8") as f:
    bootstrap = json.load(f)

with open(DATA / "espn_lineups.csv", encoding="utf-8") as f:
    lineups = list(csv.DictReader(f))

teams = {
    t["id"]: t["name"]
    for t in bootstrap["teams"]
}

fpl_players = defaultdict(list)

for p in bootstrap["elements"]:
    team = normalize(teams[p["team"]])
    fpl_players[team].append(p)

aliases = {
    "manchestercity": "manchestercity",
    "manchesterunited": "manchesterunited",
    "tottenhamhotspur": "tottenham",
    "tottenham": "tottenham",
    "brightonandhovealbion": "brighton",
    "brighton": "brighton",
    "westhamunited": "westham",
    "westham": "westham",
    "newcastleunited": "newcastle",
    "newcastle": "newcastle",
    "wolverhamptonwanderers": "wolves",
    "wolverhampton": "wolves",
    "nottinghamforest": "nottinghamforest",
    "leedsunited": "leeds",
    "leeds": "leeds",
}

def team_key(name):
    key = normalize(name)
    return aliases.get(key, key)

fpl_by_team = defaultdict(list)

for team, players in fpl_players.items():
    fpl_by_team[team_key(team)].extend(players)

results = []
matched = 0
unmatched = 0
ambiguous = 0

for row in lineups:
    team = team_key(row["team"])
    name = normalize(row["player"])

    candidates = []

    for p in fpl_by_team.get(team, []):
        full = normalize(
            p["first_name"] + " " + p["second_name"]
        )
        if name == full:
            candidates.append(p)

    if len(candidates) == 1:
        p = candidates[0]
        status = "MATCHED"
        fpl_id = p["id"]
        matched += 1
    elif len(candidates) > 1:
        status = "AMBIGUOUS"
        fpl_id = ""
        ambiguous += 1
    else:
        status = "UNMATCHED"
        fpl_id = ""
        unmatched += 1

    results.append({
        "event_id": row["event_id"],
        "match_date": row["match_date"],
        "team": row["team"],
        "espn_id": row["espn_id"],
        "player": row["player"],
        "fpl_id": fpl_id,
        "formation_place": row["formation_place"],
        "status": status
    })

fields = [
    "event_id", "match_date", "team",
    "espn_id", "player", "fpl_id",
    "formation_place", "status"
]

with open(DATA / "espn_fpl_matches.csv", "w",
          newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

print("ESPN / FPL MATCHING REPORT")
print("Total records:", len(results))
print("Matched:", matched)
print("Unmatched:", unmatched)
print("Ambiguous:", ambiguous)

if results:
    print("Match rate:", round(
        100 * matched / len(results), 1
    ), "%")

print("Saved: data/espn_fpl_matches.csv")
print("Unmatched players require review.")
