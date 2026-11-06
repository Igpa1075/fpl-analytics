
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())

with (DATA / "bootstrap.json").open(encoding="utf-8") as f:
    boot = json.load(f)

with (DATA / "espn_fpl_team_mapping.json").open(
    encoding="utf-8"
) as f:
    team_map = json.load(f)

with (DATA / "espn_fpl_matches_v2.csv").open(
    encoding="utf-8", newline=""
) as f:
    rows = list(csv.DictReader(f))

teams = {t["id"]: t["name"] for t in boot["teams"]}
players = {str(p["id"]): p for p in boot["elements"]}

by_name = defaultdict(list)

for p in boot["elements"]:
    full = p["first_name"] + " " + p["second_name"]
    by_name[norm(full)].append(p)

grouped = defaultdict(list)
for row in rows:
    grouped[row["espn_id"]].append(row)

output = []

for espn_id, appearances in grouped.items():
    first = appearances[0]
    name = first["player"]
    espn_team = first["team"]
    expected_team_id = team_map.get(espn_team)

    matches = by_name.get(norm(name), [])
    fpl_id = first["fpl_id"]

    if first["status"] == "MATCHED" and fpl_id in players:
        p = players[fpl_id]
        if p["team"] == expected_team_id:
            category = "MATCHED_OK"
        else:
            category = "MATCHED_CLUB_MISMATCH"
        candidates = [p]

    elif len(matches) == 0:
        category = "NAME_NOT_FOUND"
        candidates = []

    elif len(matches) > 1:
        category = "MULTIPLE_NAME_MATCHES"
        candidates = matches

    elif matches[0]["team"] != expected_team_id:
        category = "NAME_FOUND_OTHER_CLUB"
        candidates = matches

    else:
        category = "NAME_FOUND_SAME_CLUB"
        candidates = matches

    output.append({
        "espn_id": espn_id,
        "espn_player": name,
        "espn_team": espn_team,
        "appearances": len(appearances),
        "previous_status": first["status"],
        "category": category,
        "candidate_fpl_ids": "|".join(
            str(p["id"]) for p in candidates
        ),
        "candidate_fpl_teams": "|".join(
            teams[p["team"]] for p in candidates
        )
    })

output.sort(
    key=lambda r: (
        r["category"] == "MATCHED_OK",
        r["category"],
        -r["appearances"]
    )
)

path = DATA / "espn_player_verification.csv"

with path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(output[0]))
    writer.writeheader()
    writer.writerows(output)

counts = Counter(r["category"] for r in output)

print("ESPN PLAYER VERIFICATION")
print("Unique ESPN players:", len(output))
print("Total appearances:", len(rows))

for category, count in sorted(counts.items()):
    print(category + ":", count)

print("Saved:", path)
print("No player IDs were automatically changed.")
