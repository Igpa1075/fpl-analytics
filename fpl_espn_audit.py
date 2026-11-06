
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path("data")

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def norm(value):
    value = unicodedata.normalize(
        "NFKD", str(value or "")
    )
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
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

def club(name):
    key = norm(name)
    return ALIASES.get(key, key)

lineups = read_csv("espn_lineups.csv")
matches = read_csv("espn_fpl_matches_v2.csv")

with (DATA / "bootstrap.json").open(
    encoding="utf-8"
) as f:
    boot = json.load(f)

fpl_teams = {
    str(t["id"]): t["name"]
    for t in boot["teams"]
}
fpl_players = {
    str(p["id"]): p
    for p in boot["elements"]
}

issues = []
seen_issues = set()

def flag(category, severity, row, detail):
    key = (
        category,
        row.get("event_id", ""),
        row.get("espn_id", ""),
        detail
    )
    if key in seen_issues:
        return
    seen_issues.add(key)
    issues.append({
        "severity": severity,
        "category": category,
        "event_id": row.get("event_id", ""),
        "match_date": row.get("match_date", ""),
        "team": row.get("team", ""),
        "espn_id": row.get("espn_id", ""),
        "player": row.get("player", ""),
        "detail": detail,
    })

# 1. Check starting XI completeness and duplicates.
by_team_match = defaultdict(list)
by_event = defaultdict(list)
by_espn = defaultdict(list)

for row in lineups:
    key = (row["event_id"], row["team"])
    by_team_match[key].append(row)
    by_event[row["event_id"]].append(row)
    by_espn[row["espn_id"]].append(row)

for key, rows in by_team_match.items():
    if len(rows) != 11:
        flag(
            "STARTING_XI_SIZE", "HIGH", rows[0],
            f"Expected 11 players; found {len(rows)}"
        )

    ids = [r["espn_id"] for r in rows]
    if len(ids) != len(set(ids)):
        flag(
            "DUPLICATE_STARTER", "HIGH", rows[0],
            "Duplicate ESPN ID in one starting XI"
        )

for event, rows in by_event.items():
    clubs = {r["team"] for r in rows}
    if len(clubs) != 2:
        flag(
            "MATCH_TEAM_COUNT", "HIGH", rows[0],
            f"Expected 2 clubs; found {len(clubs)}"
        )

    ids = [r["espn_id"] for r in rows]
    if len(ids) != len(set(ids)):
        flag(
            "PLAYER_ON_BOTH_SIDES", "HIGH", rows[0],
            "Same ESPN ID appears twice in a match"
        )

# 2. Check ESPN identity consistency.
for espn_id, rows in by_espn.items():
    names = {norm(r["player"]) for r in rows}
    clubs = {club(r["team"]) for r in rows}

    if len(names) > 1:
        flag(
            "ESPN_ID_NAME_CONFLICT", "HIGH", rows[0],
            "One ESPN ID has different player names"
        )

    if len(clubs) > 1:
        flag(
            "ESPN_CLUB_CHANGE", "REVIEW", rows[0],
            "ESPN ID appears for multiple clubs: "
            + ", ".join(sorted({r["team"] for r in rows}))
        )

# 3. Check matching output against source.
source_keys = Counter(
    (r["event_id"], r["team"], r["espn_id"])
    for r in lineups
)
match_keys = Counter(
    (r["event_id"], r["team"], r["espn_id"])
    for r in matches
)

if source_keys != match_keys:
    flag(
        "SOURCE_ROW_MISMATCH", "HIGH", {},
        "V2 output does not match ESPN source rows"
    )

fpl_to_espn = defaultdict(set)
espn_to_fpl = defaultdict(set)

for row in matches:
    status = row["status"]
    fid = row["fpl_id"].strip()
    eid = row["espn_id"]

    if status != "MATCHED":
        continue

    if not fid or fid not in fpl_players:
        flag(
            "INVALID_FPL_ID", "HIGH", row,
            "Matched record has invalid FPL ID"
        )
        continue

    player = fpl_players[fid]
    fpl_club = fpl_teams[str(player["team"])]

    fpl_to_espn[fid].add(eid)
    espn_to_fpl[eid].add(fid)

    if club(row["team"]) != club(fpl_club):
        flag(
            "CLUB_MISMATCH", "REVIEW", row,
            f"ESPN: {row['team']}; "
            f"current FPL: {fpl_club}"
        )

for fid, ids in fpl_to_espn.items():
    if len(ids) > 1:
        flag(
            "FPL_ID_COLLISION", "HIGH", {},
            f"FPL ID {fid} maps to ESPN IDs: "
            + ", ".join(sorted(ids))
        )

for eid, ids in espn_to_fpl.items():
    if len(ids) > 1:
        flag(
            "ESPN_ID_COLLISION", "HIGH", {},
            f"ESPN ID {eid} maps to FPL IDs: "
            + ", ".join(sorted(ids))
        )

# 4. Check dates and formation places.
for row in lineups:
    try:
        date = datetime.fromisoformat(
            row["match_date"].replace("Z", "+00:00")
        )
        if date.year < 2020:
            raise ValueError("Unexpected date")
    except (ValueError, TypeError):
        flag(
            "INVALID_MATCH_DATE", "HIGH", row,
            "Invalid match date"
        )

    place = row.get("formation_place", "")
    try:
        value = int(place)
        if not 1 <= value <= 11:
            raise ValueError("Out of range")
    except (ValueError, TypeError):
        flag(
            "INVALID_FORMATION_PLACE", "REVIEW", row,
            f"Formation place: {place}"
        )

# 5. Save audit.
fields = [
    "severity", "category", "event_id",
    "match_date", "team", "espn_id",
    "player", "detail"
]

with (DATA / "espn_audit.csv").open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(issues)

counts = Counter(i["severity"] for i in issues)
categories = Counter(i["category"] for i in issues)

report = {
    "source_rows": len(lineups),
    "matched_rows": sum(
        r["status"] == "MATCHED" for r in matches
    ),
    "unique_matches": len(by_event),
    "unique_espn_players": len(by_espn),
    "issue_counts": dict(counts),
    "categories": dict(categories),
    "note": (
        "This audit checks internal consistency only. "
        "It does not independently verify ESPN lineups "
        "against official match reports or historical "
        "club registrations."
    )
}

(DATA / "espn_audit_summary.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("ESPN DATA QUALITY AUDIT")
print(json.dumps(report, indent=2, ensure_ascii=False))
print("Saved: data/espn_audit.csv")
print("Saved: data/espn_audit_summary.json")
