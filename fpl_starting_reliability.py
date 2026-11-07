
import csv
import json
from collections import defaultdict
from pathlib import Path

DATA = Path("data")
WINDOW = 5


def read_csv(filename):
    with (DATA / filename).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))


def read_json(filename):
    with (DATA / filename).open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


lineups = read_csv("espn_fpl_matches_v4.csv")
verification = read_csv(
    "espn_fixture_verification_v2.csv"
)
team_mapping = read_json(
    "espn_fpl_team_mapping.json"
)
bootstrap = read_json("bootstrap.json")
picks = read_json("picks.json")

players = {
    str(p["id"]): p
    for p in bootstrap["elements"]
}

teams = {
    int(t["id"]): t["short_name"]
    for t in bootstrap["teams"]
}

# Only include ESPN matches verified against FPL.
verified_events = {
    r["espn_event_id"]
    for r in verification
    if r["status"] == "VERIFIED"
}

# A team-match is counted only if ESPN supplies
# a complete XI of 11 distinct athletes.
event_teams = defaultdict(list)

for row in lineups:
    if row["event_id"] not in verified_events:
        continue

    team_id = team_mapping.get(row["team"])
    if team_id is None:
        continue

    key = (int(team_id), row["event_id"])
    event_teams[key].append(row)

complete = {}

for key, rows in event_teams.items():
    ids = [r["espn_id"] for r in rows]

    if len(rows) == 11 and len(set(ids)) == 11:
        complete[key] = rows

# Find the latest five verified matches per club.
team_events = defaultdict(list)

for (team_id, event_id), rows in complete.items():
    match_date = rows[0]["match_date"]
    team_events[team_id].append(
        (match_date, event_id)
    )

latest = {}

for team_id, events in team_events.items():
    ordered = sorted(
        events,
        reverse=True
    )
    latest[team_id] = {
        event_id for _, event_id in ordered[:WINDOW]
    }

# Count confirmed ESPN starter appearances.
starter_events = defaultdict(set)

for (team_id, event_id), rows in complete.items():
    if event_id not in latest.get(team_id, set()):
        continue

    for row in rows:
        if row["status"] != "MATCHED":
            continue

        fpl_id = row["fpl_id"]
        if not fpl_id:
            continue

        player = players.get(fpl_id)
        if not player:
            continue

        if int(player["team"]) != team_id:
            continue

        starter_events[fpl_id].add(event_id)

results = []

for fpl_id, player in players.items():
    team_id = int(player["team"])
    matches = len(latest.get(team_id, set()))
    starts = len(starter_events.get(fpl_id, set()))

    rate = (
        round(100 * starts / matches, 1)
        if matches else None
    )

    if matches < WINDOW:
        reliability = "INSUFFICIENT_SAMPLE"
    elif starts == 5:
        reliability = "VERY_STABLE"
    elif starts == 4:
        reliability = "STABLE"
    elif starts == 3:
        reliability = "MODERATE"
    else:
        reliability = "ROTATION_OR_ABSENCE"

    results.append({
        "fpl_id": fpl_id,
        "player": player["web_name"],
        "team": teams.get(team_id, ""),
        "position": player["element_type"],
        "matches_available": matches,
        "starts": starts,
        "start_rate_pct": (
            rate if rate is not None else ""
        ),
        "reliability": reliability,
        "minutes_season": player.get("minutes", 0),
        "now_cost": player.get("now_cost", 0)
    })

results.sort(
    key=lambda r: (
        -r["starts"],
        -r["matches_available"],
        r["player"]
    )
)

fields = list(results[0])

with (
    DATA / "starter_stability.csv"
).open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=fields
    )
    writer.writeheader()
    writer.writerows(results)

# Personal FPL squad, including bench players.
squad_ids = {
    str(p["element"])
    for p in picks.get("picks", [])
}

my_squad = [
    row for row in results
    if row["fpl_id"] in squad_ids
]

with (
    DATA / "my_starter_stability.csv"
).open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=fields
    )
    writer.writeheader()
    writer.writerows(my_squad)

summary = {
    "window": WINDOW,
    "teams_with_complete_matches": len(latest),
    "teams_with_full_window": sum(
        len(events) == WINDOW
        for events in latest.values()
    ),
    "players": len(results),
    "squad_players_found": len(my_squad),
    "note": (
        "Starts are taken from ESPN starter=true. "
        "Only verified matches with complete XIs "
        "are included. Unmatched identities are "
        "not credited. A zero start rate may reflect "
        "injury, transfer, absence or incomplete "
        "identity matching, not necessarily rotation. "
        "This is descriptive, not a future probability."
    )
}

with (
    DATA / "starter_stability_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f, indent=2, ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
print("Saved starter_stability.csv")
print("Saved my_starter_stability.csv")
