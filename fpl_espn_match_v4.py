
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")

def tokens(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )
    return re.findall(r"[a-z0-9]+", value.lower())

def norm(value):
    return "".join(tokens(value))

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

rows = read_csv("espn_fpl_matches_v3.csv")

players = boot["elements"]
by_id = {str(p["id"]): p for p in players}

by_team = defaultdict(list)
for p in players:
    by_team[p["team"]].append(p)

def candidate_method(name, player):
    full = (
        player["first_name"] + " " +
        player["second_name"]
    )
    web_name = player.get("web_name", "")

    a = norm(name)
    b = norm(full)
    w = norm(web_name)

    if a == b:
        return "EXACT_FULL"

    if a and a == w:
        return "EXACT_WEB_NAME"

    name_parts = tokens(name)
    full_parts = tokens(full)

    # Match all ESPN name tokens against complete FPL tokens.
    # Require at least two distinct tokens.
    if (
        len(name_parts) >= 2
        and len(set(name_parts)) >= 2
        and set(name_parts).issubset(set(full_parts))
    ):
        return "NAME_TOKENS"

    return None

grouped = defaultdict(list)
for row in rows:
    grouped[row["espn_id"]].append(row)

identity = {}

for espn_id, appearances in grouped.items():
    first = appearances[0]
    old_id = first["fpl_id"]

    team_ids = {
        team_map.get(r["team"])
        for r in appearances
    }

    if None in team_ids or len(team_ids) != 1:
        identity[espn_id] = (
            "", "REVIEW", "TEAM_INCONSISTENT"
        )
        continue

    team_id = next(iter(team_ids))

    # Preserve a verified V3 identity.
    if (
        first["status"] == "MATCHED"
        and old_id in by_id
        and by_id[old_id]["team"] == team_id
    ):
        identity[espn_id] = (
            old_id, "MATCHED", "V3"
        )
        continue

    # Candidate must work across all appearances.
    candidates = []

    for p in by_team[team_id]:
        methods = [
            candidate_method(r["player"], p)
            for r in appearances
        ]

        if all(methods):
            candidates.append((p, methods))

    if len(candidates) == 1:
        p, methods = candidates[0]
        method = sorted(set(methods))[0]

        identity[espn_id] = (
            str(p["id"]), "MATCHED", method
        )
    else:
        identity[espn_id] = (
            "", "REVIEW",
            "AMBIGUOUS" if candidates else "NO_MATCH"
        )

# Prevent one FPL player being assigned to multiple ESPN IDs.
reverse = defaultdict(set)

for espn_id, (fpl_id, status, _) in identity.items():
    if status == "MATCHED":
        reverse[fpl_id].add(espn_id)

for fpl_id, espn_ids in reverse.items():
    if len(espn_ids) > 1:
        for espn_id in espn_ids:
            identity[espn_id] = (
                "", "REVIEW", "ID_COLLISION"
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

path = DATA / "espn_fpl_matches_v4.csv"

with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0].keys())
    )
    writer.writeheader()
    writer.writerows(output)

counts = Counter(r["status"] for r in output)
methods = Counter(
    r["method"] for r in output
    if r["status"] == "MATCHED"
)

print("ESPN / FPL MATCHING V4")
print("Total rows:", len(output))
print("MATCHED:", counts["MATCHED"])
print("REVIEW:", counts["REVIEW"])
print(
    "Match rate:",
    round(100 * counts["MATCHED"] / len(output), 1),
    "%"
)

print("Methods:")
for method, count in sorted(methods.items()):
    print(method + ":", count)

print("Saved:", path)
print("No fuzzy similarity matches applied.")
