
import csv
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

DATA = Path("data")

def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", value.lower())

def read_csv(filename):
    with (DATA / filename).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

with (DATA / "bootstrap.json").open(encoding="utf-8") as f:
    boot = json.load(f)

with (DATA / "espn_fpl_team_mapping.json").open(
    encoding="utf-8"
) as f:
    team_map = json.load(f)

rows = read_csv("espn_fpl_matches_v3.csv")

teams = {
    t["id"]: t["name"]
    for t in boot["teams"]
}

players = boot["elements"]

grouped = defaultdict(list)
for row in rows:
    if row["status"] == "REVIEW":
        grouped[row["espn_id"]].append(row)

output = []

for espn_id, appearances in grouped.items():
    row = appearances[0]
    espn_name = row["player"]
    expected_team = team_map.get(row["team"])

    candidates = []

    for p in players:
        full = p["first_name"] + " " + p["second_name"]

        score = SequenceMatcher(
            None,
            normalize(espn_name),
            normalize(full)
        ).ratio()

        same_team = p["team"] == expected_team

        candidates.append({
            "score": score,
            "same_team": same_team,
            "id": p["id"],
            "name": full,
            "team": teams[p["team"]]
        })

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["same_team"]
        ),
        reverse=True
    )

    for rank, candidate in enumerate(candidates[:5], 1):
        output.append({
            "espn_id": espn_id,
            "espn_player": espn_name,
            "espn_team": row["team"],
            "appearances": len(appearances),
            "candidate_rank": rank,
            "fpl_id": candidate["id"],
            "fpl_player": candidate["name"],
            "fpl_team": candidate["team"],
            "same_team": candidate["same_team"],
            "name_similarity": round(
                candidate["score"], 3
            ),
            "decision": "MANUAL_REVIEW"
        })

path = DATA / "espn_player_review_candidates.csv"

with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0].keys())
    )
    writer.writeheader()
    writer.writerows(output)

print("PLAYER REVIEW CANDIDATES")
print("Unique players requiring review:", len(grouped))
print("Candidate rows:", len(output))
print("Saved:", path)
print("No automatic player matching performed.")
