
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")
WINDOW = 5

def load_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def load_json(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return json.load(f)

rows = load_csv("espn_fpl_matches_v4.csv")
verification = load_csv("espn_fixture_verification_v2.csv")
mapping = load_json("espn_fpl_team_mapping.json")
bootstrap = load_json("bootstrap.json")
picks = load_json("picks.json")

players = {
    str(p["id"]): p
    for p in bootstrap["elements"]
}
teams = {
    int(t["id"]): t["short_name"]
    for t in bootstrap["teams"]
}
verified = {
    r["espn_event_id"]
    for r in verification
    if r["status"] == "VERIFIED"
}

# Approximate ESPN lineup-slot classification.
# These slots are NOT physical tracking coordinates.
SLOT_ROLES = {
    1: "GOALKEEPER",
    2: "WIDE_DEFENSIVE_SLOT",
    3: "WIDE_DEFENSIVE_SLOT",
    4: "CENTRAL_MIDFIELD_SLOT",
    5: "CENTRAL_DEFENSIVE_SLOT",
    6: "CENTRAL_DEFENSIVE_SLOT",
    7: "WIDE_ADVANCED_SLOT",
    8: "CENTRAL_MIDFIELD_SLOT",
    9: "CENTRAL_FORWARD_SLOT",
    10: "ADVANCED_CENTRAL_SLOT",
    11: "WIDE_ADVANCED_SLOT",
}

POSITION_NAMES = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}

grouped = defaultdict(list)

for row in rows:
    event = row["event_id"]
    team_id = mapping.get(row["team"])
    if event not in verified or team_id is None:
        continue
    grouped[(int(team_id), event)].append(row)

# Only complete, unique starting XIs.
complete = {}

for key, group in grouped.items():
    ids = [r["espn_id"] for r in group]
    if len(group) == 11 and len(set(ids)) == 11:
        complete[key] = group

team_events = defaultdict(list)

for (team_id, event), group in complete.items():
    team_events[team_id].append(
        (group[0]["match_date"], event)
    )

latest = {}

for team_id, events in team_events.items():
    latest[team_id] = {
        event
        for _, event in sorted(
            events, reverse=True
        )[:WINDOW]
    }

player_slots = defaultdict(list)

for (team_id, event), group in complete.items():
    if event not in latest.get(team_id, set()):
        continue

    for row in group:
        if row["status"] != "MATCHED":
            continue

        fpl_id = row["fpl_id"]
        player = players.get(fpl_id)

        if not player:
            continue
        if int(player["team"]) != team_id:
            continue

        try:
            slot = int(row["formation_place"])
        except (ValueError, TypeError):
            continue

        if slot not in SLOT_ROLES:
            continue

        player_slots[fpl_id].append(slot)

output = []

for fpl_id, player in players.items():
    slots = player_slots.get(fpl_id, [])
    counts = Counter(slots)

    most_common = (
        counts.most_common(1)[0][0]
        if counts else None
    )

    roles = Counter(
        SLOT_ROLES[s] for s in slots
    )

    primary_role = (
        roles.most_common(1)[0][0]
        if roles else "NO_DATA"
    )

    fpl_position = POSITION_NAMES.get(
        player["element_type"], "UNKNOWN"
    )

    advanced_slots = sum(
        s in (7, 9, 10, 11)
        for s in slots
    )

    # Candidate flag, not proof of attacking play.
    if (
        fpl_position == "DEF"
        and advanced_slots >= 2
    ):
        flag = "DEF_ADVANCED_SLOT_CANDIDATE"
    elif (
        fpl_position == "MID"
        and counts.get(9, 0) >= 2
    ):
        flag = "MID_FORWARD_SLOT_CANDIDATE"
    else:
        flag = "NONE"

    output.append({
        "fpl_id": fpl_id,
        "player": player["web_name"],
        "team": teams.get(
            int(player["team"]), ""
        ),
        "fpl_position": fpl_position,
        "matches_available": len(
            latest.get(int(player["team"]), set())
        ),
        "starts_with_position": len(slots),
        "most_common_slot": (
            most_common if most_common else ""
        ),
        "primary_slot_role": primary_role,
        "advanced_slot_starts": advanced_slots,
        "position_flag": flag,
        "slot_history": ",".join(
            str(s) for s in slots
        ),
        "now_cost": player.get("now_cost", 0),
        "total_points": player.get(
            "total_points", 0
        ),
    })

output.sort(
    key=lambda r: (
        -r["advanced_slot_starts"],
        -r["starts_with_position"],
        r["player"],
    )
)

fields = list(output[0])

def save_csv(filename, records):
    with (DATA / filename).open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(records)

save_csv("position_analysis.csv", output)

squad_ids = {
    str(p["element"])
    for p in picks.get("picks", [])
}

my_players = [
    r for r in output
    if r["fpl_id"] in squad_ids
]

save_csv(
    "my_position_analysis.csv",
    my_players
)

candidates = [
    r for r in output
    if r["position_flag"] != "NONE"
]

save_csv(
    "position_candidates.csv",
    candidates
)

summary = {
    "players": len(output),
    "squad_players": len(my_players),
    "candidates": len(candidates),
    "teams": len(latest),
    "window": WINDOW,
    "warning": (
        "ESPN formation_place is a lineup slot, "
        "not tracking coordinates. Slot meanings "
        "may vary with formation. Candidate flags "
        "must be verified before tactical conclusions."
    )
}

with (
    DATA / "position_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f,
        indent=2,
        ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
