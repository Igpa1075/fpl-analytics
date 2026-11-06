
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

DATA = Path("data")

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())

def words(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value if not unicodedata.combining(c)
    )
    return set(re.findall(r"[a-z0-9]+", value.lower()))

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
    "sunderlandafc": "sunderland",
}

def team_key(name):
    key = norm(name)
    return ALIASES.get(key, key)

with open(DATA / "bootstrap.json", encoding="utf-8") as f:
    boot = json.load(f)

with open(DATA / "espn_lineups.csv", encoding="utf-8") as f:
    espn_rows = list(csv.DictReader(f))

teams = {t["id"]: team_key(t["name"]) for t in boot["teams"]}

fpl_by_team = defaultdict(list)

for player in boot["elements"]:
    fpl_by_team[teams[player["team"]]].append(player)

def match_candidates(row):
    candidates = []
    name = row["player"]
    normalized = norm(name)
    name_words = words(name)

    for player in fpl_by_team.get(team_key(row["team"]), []):
        first = player["first_name"]
        last = player["second_name"]
        full = first + " " + last

        if norm(full) == normalized:
            candidates.append((player, "EXACT"))
        elif norm(last) == normalized and len(normalized) >= 5:
            candidates.append((player, "SURNAME"))
        elif (
            words(full) == name_words
            and len(name_words) >= 2
        ):
            candidates.append((player, "NAME_WORDS"))

    return candidates

# One ESPN identity must map consistently across all matches.
grouped = defaultdict(list)

for row in espn_rows:
    grouped[row["espn_id"]].append(row)

identity_map = {}

for espn_id, appearances in grouped.items():
    candidate_sets = []
    methods = defaultdict(set)

    for row in appearances:
        candidates = match_candidates(row)
        ids = {p["id"] for p, _ in candidates}
        candidate_sets.append(ids)

        for player, method in candidates:
            methods[player["id"]].add(method)

    if not candidate_sets:
        identity_map[espn_id] = ("", "UNMATCHED", "")
        continue

    common = set.intersection(*candidate_sets)

    if len(common) == 1:
        fpl_id = next(iter(common))
        method = ",".join(sorted(methods[fpl_id]))
        identity_map[espn_id] = (
            fpl_id, "MATCHED", method
        )
    elif len(common) > 1:
        identity_map[espn_id] = ("", "AMBIGUOUS", "")
    else:
        identity_map[espn_id] = ("", "REVIEW", "")

# Prevent two ESPN identities from sharing one FPL ID.
reverse = defaultdict(set)

for espn_id, (fpl_id, status, method) in identity_map.items():
    if status == "MATCHED":
        reverse[fpl_id].add(espn_id)

for fpl_id, espn_ids in reverse.items():
    if len(espn_ids) > 1:
        for espn_id in espn_ids:
            identity_map[espn_id] = ("", "REVIEW", "")

output = []
counts = defaultdict(int)

for row in espn_rows:
    fpl_id, status, method = identity_map[row["espn_id"]]
    counts[status] += 1

    output.append({
        "event_id": row["event_id"],
        "match_date": row["match_date"],
        "team": row["team"],
        "espn_id": row["espn_id"],
        "player": row["player"],
        "fpl_id": fpl_id,
        "formation_place": row["formation_place"],
        "status": status,
        "method": method,
    })

fields = [
    "event_id", "match_date", "team",
    "espn_id", "player", "fpl_id",
    "formation_place", "status", "method"
]

with open(DATA / "espn_fpl_matches_v2.csv", "w",
          newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(output)

print("ESPN / FPL MATCHING V2")
print("Total:", len(output))

for status in ["MATCHED", "UNMATCHED", "AMBIGUOUS", "REVIEW"]:
    print(status + ":", counts[status])

if output:
    print(
        "Match rate:",
        round(100 * counts["MATCHED"] / len(output), 1),
        "%"
    )

print("Saved: data/espn_fpl_matches_v2.csv")
print("No automatic tactical role assignments.")
