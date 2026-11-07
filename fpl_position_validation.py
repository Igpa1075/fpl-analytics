
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def read_json(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return json.load(f)

matches = read_csv("espn_fpl_matches_v4.csv")
verification = read_csv(
    "espn_fixture_verification_v2.csv"
)
bootstrap = read_json("bootstrap.json")
mapping = read_json("espn_fpl_team_mapping.json")

players = {
    str(p["id"]): p
    for p in bootstrap["elements"]
}

positions = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}

verified = {
    row["espn_event_id"]
    for row in verification
    if row["status"] == "VERIFIED"
}

groups = defaultdict(list)

for row in matches:
    team_id = mapping.get(row["team"])
    if (
        row["event_id"] in verified
        and team_id is not None
    ):
        groups[(int(team_id), row["event_id"])].append(row)

complete = {}

for key, group in groups.items():
    ids = [r["espn_id"] for r in group]
    if len(group) == 11 and len(set(ids)) == 11:
        complete[key] = group

# Validate slot numbering within each lineup.
slot_counts = defaultdict(Counter)
slot_examples = defaultdict(list)
bad_lineups = []
valid_lineups = 0
matched_records = 0

for (team_id, event), group in complete.items():
    slots = []

    for row in group:
        try:
            slots.append(int(row["formation_place"]))
        except (ValueError, TypeError):
            pass

    if sorted(slots) != list(range(1, 12)):
        bad_lineups.append({
            "team_id": team_id,
            "event_id": event,
            "slots": slots,
        })
        continue

    valid_lineups += 1

    for row in group:
        if row["status"] != "MATCHED":
            continue

        player = players.get(row["fpl_id"])
        if not player:
            continue
        if int(player["team"]) != team_id:
            continue

        slot = int(row["formation_place"])
        fpl_position = positions.get(
            player["element_type"], "UNKNOWN"
        )

        slot_counts[slot][fpl_position] += 1
        matched_records += 1

        if len(slot_examples[slot]) < 8:
            slot_examples[slot].append(
                player["web_name"]
            )

# A FPL position is not the same as a tactical
# role. This measures agreement, not accuracy.
output = []

for slot in range(1, 12):
    counts = slot_counts[slot]
    total = sum(counts.values())

    if total:
        common, number = counts.most_common(1)[0]
        agreement = round(
            number * 100 / total, 1
        )
    else:
        common = "UNKNOWN"
        agreement = 0

    if total < 20:
        confidence = "INSUFFICIENT_DATA"
    elif agreement >= 85:
        confidence = "CONSISTENT_FPL_CATEGORY"
    else:
        confidence = "MIXED_FPL_CATEGORIES"

    output.append({
        "espn_slot": slot,
        "records": total,
        "gk": counts["GK"],
        "def": counts["DEF"],
        "mid": counts["MID"],
        "fwd": counts["FWD"],
        "most_common_fpl_category": common,
        "agreement_pct": agreement,
        "category_consistency": confidence,
        "examples": ", ".join(
            slot_examples[slot]
        ),
    })

with (
    DATA / "position_slot_validation.csv"
).open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0])
    )
    writer.writeheader()
    writer.writerows(output)

summary = {
    "complete_lineups": len(complete),
    "valid_slot_lineups": valid_lineups,
    "invalid_slot_lineups": len(bad_lineups),
    "matched_player_records": matched_records,
    "slots_with_mixed_fpl_categories": [
        r["espn_slot"]
        for r in output
        if r["category_consistency"]
        == "MIXED_FPL_CATEGORIES"
    ],
    "limitations": (
        "FPL position categories are broad. "
        "Agreement does not validate tactical "
        "roles, formation coordinates, or "
        "attacking involvement."
    ),
    "invalid_examples": bad_lineups[:10],
}

with (
    DATA / "position_validation_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f,
        indent=2,
        ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
