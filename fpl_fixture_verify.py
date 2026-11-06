
import csv
import json
import re
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")

def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())

ALIASES = {
    "tottenhamhotspur": "tottenham",
    "brightonandhovealbion": "brighton",
    "newcastleunited": "newcastle",
    "westhamunited": "westham",
    "wolverhamptonwanderers": "wolves",
    "wolverhampton": "wolves",
    "manchestercity": "mancity",
    "manchesterunited": "manutd",
    "nottinghamforest": "nottmforest",
    "leedsunited": "leeds",
}

def club(value):
    key = normalize(value)
    return ALIASES.get(key, key)

def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None

with (DATA / "bootstrap.json").open(encoding="utf-8") as f:
    bootstrap = json.load(f)

with (DATA / "fixtures.json").open(encoding="utf-8") as f:
    fixtures = json.load(f)

with (DATA / "espn_lineups.csv").open(
    encoding="utf-8", newline=""
) as f:
    lineups = list(csv.DictReader(f))

teams = {
    t["id"]: t["name"]
    for t in bootstrap["teams"]
}

fpl_matches = []

for fixture in fixtures:
    if fixture.get("finished") is not True:
        continue

    kickoff = parse_date(fixture.get("kickoff_time"))
    if not kickoff:
        continue

    fpl_matches.append({
        "id": fixture["id"],
        "date": kickoff,
        "teams": frozenset({
            club(teams[fixture["team_h"]]),
            club(teams[fixture["team_a"]])
        })
    })

espn_events = defaultdict(list)

for row in lineups:
    espn_events[row["event_id"]].append(row)

results = []

for event_id, rows in espn_events.items():
    names = sorted({r["team"] for r in rows})
    espn_date = parse_date(rows[0]["match_date"])
    team_set = frozenset(club(t) for t in names)

    candidates = []

    if len(team_set) == 2 and espn_date:
        for fixture in fpl_matches:
            if fixture["teams"] != team_set:
                continue

            hours = abs(
                (fixture["date"] - espn_date).total_seconds()
            ) / 3600

            if hours <= 12:
                candidates.append((hours, fixture))

    candidates.sort(key=lambda x: x[0])

    if len(candidates) == 1:
        status = "VERIFIED"
        fpl_id = candidates[0][1]["id"]
        diff = round(candidates[0][0], 2)
    elif len(candidates) > 1:
        status = "AMBIGUOUS"
        fpl_id = ""
        diff = ""
    else:
        status = "UNVERIFIED"
        fpl_id = ""
        diff = ""

    results.append({
        "espn_event_id": event_id,
        "match_date": rows[0]["match_date"],
        "teams": " / ".join(names),
        "status": status,
        "fpl_fixture_id": fpl_id,
        "time_difference_hours": diff,
    })

fields = [
    "espn_event_id", "match_date", "teams",
    "status", "fpl_fixture_id",
    "time_difference_hours"
]

with (DATA / "espn_fixture_verification.csv").open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

counts = Counter(r["status"] for r in results)

print("ESPN vs OFFICIAL FPL FIXTURES")
print("Total ESPN matches:", len(results))
print("Verified:", counts["VERIFIED"])
print("Unverified:", counts["UNVERIFIED"])
print("Ambiguous:", counts["AMBIGUOUS"])
print("Saved: data/espn_fixture_verification.csv")

if counts["UNVERIFIED"]:
    print("WARNING: Unverified matches require investigation")
