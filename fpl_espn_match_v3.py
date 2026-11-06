
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

with (DATA / "bootstrap.json").open(encoding="utf-8") as f:
    boot = json.load(f)

with (DATA / "espn_fpl_team_mapping.json").open(
    encoding="utf-8"
) as f:
    team_map = json.load(f)

rows = read_csv("espn_fpl_matches_v2.csv")

players = boot["elements"]
by_id = {str(p["id"]): p for p in players}

by_team_name = defaultdict(list)

for p in players:
    full = p["first_name"] + " " + p["second_name"]
    by_team_name[(p["team"], norm(full))].append(p)

# ESPN player identities must remain consistent.
grouped = defaultdict(list)

for row in rows:
    grouped[row["espn_id"]].append(row)

identity = {}

for espn_id, appearances in grouped.items():
    original = appearances[0]
    original_id = original["fpl_id"]

    # Preserve previously verified exact/word matches.
    if (
        original["status"] == "MATCHED"
        and original_id in by_id
        and all(
            team_map.get(r["team"]) == by_id[original_id]["team"]
            for r in appearances
        )
    ):
        identity[espn_id] = (
            original_id, "MATCHED", "V2"
        )
        continue

    candidate_sets = []

    for row in appearances:
        team_id = team_map.get(row["team"])
        candidates = by_team_name.get(
            (team_id, norm(row["player"])), []
        )
        candidate_sets.append({
            str(p["id"]) for p in candidates
        })

    common = (
        set.intersection(*candidate_sets)
        if candidate_sets else set()
    )

    if len(common) == 1:
        identity[espn_id] = (
            next(iter(common)), "MATCHED", "EXACT_TEAM_ID"
        )
    else:
        identity[espn_id] = (
            "", "REVIEW", ""
        )

# One FPL ID must not belong to two ESPN identities.
reverse = defaultdict(set)

for espn_id, (fpl_id, status, _) in identity.items():
    if status == "MATCHED":
        reverse[fpl_id].add(espn_id)

for fpl_id, espn_ids in reverse.items():
    if len(espn_ids) > 1:
        for espn_id in espn_ids:
            identity[espn_id] = (
                "", "REVIEW", ""
            )

output = []

for row in rows:
    fpl_id, status, method = identity[row["espn_id"]]

    output.append({
        **row,
        "fpl_id": fpl_id,
        "status": status,
        "method": method
    })

path = DATA / "espn_fpl_matches_v3.csv"

with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0].keys())
    )
    writer.writeheader()
    writer.writerows(output)

counts = Counter(r["status"] for r in output)

print("ESPN / FPL MATCHING V3")
print("Total rows:", len(output))
print("MATCHED:", counts["MATCHED"])
print("REVIEW:", counts["REVIEW"])
print(
    "Match rate:",
    round(100 * counts["MATCHED"] / len(output), 1),
    "%"
)
print("Saved:", path)
print("No fuzzy or speculative matches applied.")
