
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def dt(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)

fixtures = json.loads(
    (DATA / "fixtures.json").read_text(encoding="utf-8")
)

lineups = read_csv("espn_lineups.csv")
old = read_csv("espn_fixture_verification.csv")

finished = {
    str(f["id"]): f
    for f in fixtures
    if f.get("finished") and f.get("kickoff_time")
}

events = defaultdict(list)
for row in lineups:
    events[row["event_id"]].append(row)

# Build verified team-to-ID mappings using intersections.
possible = defaultdict(list)

for row in old:
    if row["status"] != "VERIFIED":
        continue

    fixture = finished.get(row["fpl_fixture_id"])
    if not fixture:
        continue

    team_names = {
        r["team"]
        for r in events[row["espn_event_id"]]
    }

    if len(team_names) != 2:
        continue

    pair = {
        fixture["team_h"],
        fixture["team_a"]
    }

    for name in team_names:
        possible[name].append(pair)

mapping = {}

for name, sets in possible.items():
    common = set.intersection(*sets)
    if len(common) == 1:
        mapping[name] = next(iter(common))

# Match an ESPN event using verified team IDs and time.
def candidates(rows):
    names = sorted({r["team"] for r in rows})

    if len(names) != 2:
        return []

    try:
        when = dt(rows[0]["match_date"])
    except (ValueError, TypeError, KeyError):
        return []

    result = []

    for fixture in finished.values():
        delta = abs(
            (dt(fixture["kickoff_time"]) - when)
            .total_seconds()
        )

        if delta > 12 * 3600:
            continue

        pair = {
            fixture["team_h"],
            fixture["team_a"]
        }

        known = [
            mapping[n]
            for n in names
            if n in mapping
        ]

        if not all(team_id in pair for team_id in known):
            continue

        if len(set(known)) != len(known):
            continue

        result.append((fixture, delta))

    return result

# Infer missing IDs only from uniquely constrained matches.
for _ in range(5):
    changed = False

    for rows in events.values():
        names = sorted({r["team"] for r in rows})
        if len(names) != 2:
            continue

        unknown = [n for n in names if n not in mapping]
        if len(unknown) != 1:
            continue

        options = candidates(rows)
        if len(options) != 1:
            continue

        fixture, _ = options[0]
        pair = {fixture["team_h"], fixture["team_a"]}
        known_id = mapping[
            next(n for n in names if n in mapping)
        ]
        remaining = pair - {known_id}

        if len(remaining) != 1:
            continue

        new_id = next(iter(remaining))

        if new_id in mapping.values():
            continue

        mapping[unknown[0]] = new_id
        changed = True

    if not changed:
        break

# Verify all matches with both team IDs.
results = []

for event_id, rows in events.items():
    names = sorted({r["team"] for r in rows})
    ids = [mapping.get(n) for n in names]

    status = "UNVERIFIED"
    fixture_id = ""
    delta_hours = ""

    if len(names) == 2 and all(ids) and ids[0] != ids[1]:
        valid = []

        for fixture, delta in candidates(rows):
            pair = {fixture["team_h"], fixture["team_a"]}
            if pair == set(ids):
                valid.append((fixture, delta))

        if len(valid) == 1:
            status = "VERIFIED"
            fixture_id = valid[0][0]["id"]
            delta_hours = round(valid[0][1] / 3600, 2)
        elif len(valid) > 1:
            status = "AMBIGUOUS"

    results.append({
        "espn_event_id": event_id,
        "match_date": rows[0]["match_date"],
        "teams": " / ".join(names),
        "status": status,
        "fpl_fixture_id": fixture_id,
        "time_difference_hours": delta_hours
    })

with (DATA / "espn_fixture_verification_v2.csv").open(
    "w", newline="", encoding="utf-8"
) as f:
    fields = [
        "espn_event_id", "match_date", "teams",
        "status", "fpl_fixture_id",
        "time_difference_hours"
    ]
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

# Save the mapping for future checks.
(DATA / "espn_fpl_team_mapping.json").write_text(
    json.dumps(mapping, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

counts = Counter(r["status"] for r in results)

print("ESPN / FPL FIXTURE VERIFICATION V2")
print("Team mappings:", len(mapping))
print("Matches:", len(results))
print("VERIFIED:", counts["VERIFIED"])
print("UNVERIFIED:", counts["UNVERIFIED"])
print("AMBIGUOUS:", counts["AMBIGUOUS"])
print("Saved verification and team mapping files")
