
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
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

v3 = read_csv("espn_fpl_matches_v3.csv")
v4 = read_csv("espn_fpl_matches_v4.csv")

players = boot["elements"]
by_id = {str(p["id"]): p for p in players}
teams = {t["id"]: t["name"] for t in boot["teams"]}

def key(row):
    return (
        row["event_id"],
        row["team"],
        row["espn_id"]
    )

old = {key(r): r for r in v3}
grouped = defaultdict(list)

for row in v4:
    grouped[row["espn_id"]].append(row)

results = []
issues = []

# Check identities and club assignments.
reverse = defaultdict(set)

for espn_id, appearances in grouped.items():
    first = appearances[0]
    statuses = {r["status"] for r in appearances}
    ids = {r["fpl_id"] for r in appearances}

    if len(statuses) != 1 or len(ids) != 1:
        issues.append((espn_id, "INCONSISTENT_IDENTITY"))

    if first["status"] != "MATCHED":
        continue

    fpl_id = first["fpl_id"]
    reverse[fpl_id].add(espn_id)

    p = by_id.get(fpl_id)
    if p is None:
        issues.append((espn_id, "UNKNOWN_FPL_ID"))
        continue

    for row in appearances:
        expected = team_map.get(row["team"])
        if expected != p["team"]:
            issues.append((espn_id, "CLUB_MISMATCH"))
            break

for fpl_id, espn_ids in reverse.items():
    if len(espn_ids) > 1:
        issues.append((fpl_id, "FPL_ID_COLLISION"))

# Examine identities newly matched in V4.
for espn_id, appearances in grouped.items():
    first = appearances[0]
    if first["status"] != "MATCHED":
        continue

    previous = [
        old.get(key(r))
        for r in appearances
    ]

    newly_matched = any(
        p is None or p["status"] != "MATCHED"
        for p in previous
    )

    if not newly_matched:
        continue

    p = by_id.get(first["fpl_id"])
    if not p:
        continue

    full = p["first_name"] + " " + p["second_name"]

    results.append({
        "category": "NEW_V4_MATCH",
        "espn_id": espn_id,
        "espn_name": first["player"],
        "espn_team": first["team"],
        "appearances": len(appearances),
        "fpl_id": p["id"],
        "fpl_name": full,
        "fpl_team": teams[p["team"]],
        "method": first["method"],
        "similarity": round(
            SequenceMatcher(
                None,
                norm(first["player"]),
                norm(full)
            ).ratio(), 3
        ),
        "review_status": "PENDING_INDEPENDENT_CHECK"
    })

# Produce candidates for unresolved identities.
for espn_id, appearances in grouped.items():
    first = appearances[0]
    if first["status"] != "REVIEW":
        continue

    expected = team_map.get(first["team"])
    name = first["player"]
    candidates = []

    for p in players:
        if p["team"] != expected:
            continue

        full = p["first_name"] + " " + p["second_name"]
        web = p.get("web_name", "")

        score = max(
            SequenceMatcher(
                None, norm(name), norm(full)
            ).ratio(),
            SequenceMatcher(
                None, norm(name), norm(web)
            ).ratio()
        )

        candidates.append((score, p, full))

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    for score, p, full in candidates[:5]:
        results.append({
            "category": "UNRESOLVED_CANDIDATE",
            "espn_id": espn_id,
            "espn_name": name,
            "espn_team": first["team"],
            "appearances": len(appearances),
            "fpl_id": p["id"],
            "fpl_name": full,
            "fpl_team": teams[p["team"]],
            "method": "SUGGESTION_ONLY",
            "similarity": round(score, 3),
            "review_status": "MANUAL_REVIEW"
        })

output_path = DATA / "espn_identity_audit.csv"

with output_path.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f, fieldnames=list(results[0])
    )
    writer.writeheader()
    writer.writerows(results)

summary = {
    "v3_rows": len(v3),
    "v4_rows": len(v4),
    "v3_matched": sum(
        r["status"] == "MATCHED" for r in v3
    ),
    "v4_matched": sum(
        r["status"] == "MATCHED" for r in v4
    ),
    "new_v4_unique_identities": len({
        r["espn_id"] for r in results
        if r["category"] == "NEW_V4_MATCH"
    }),
    "unresolved_unique_identities": len({
        r["espn_id"] for r in results
        if r["category"] == "UNRESOLVED_CANDIDATE"
    }),
    "internal_issues": [
        {"id": k, "issue": v}
        for k, v in sorted(set(issues))
    ],
    "note": (
        "Internal consistency only. "
        "Independent match lineup verification pending."
    )
}

with (DATA / "espn_identity_audit_summary.json").open(
    "w", encoding="utf-8"
) as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("ESPN IDENTITY AUDIT")
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("Saved:", output_path)
