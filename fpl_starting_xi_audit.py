
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

v4 = read_csv("espn_fpl_matches_v4.csv")
audit = read_csv("espn_identity_audit.csv")
minutes = read_csv("espn_fpl_minutes_crosscheck.csv")

# Candidate FPL IDs for unresolved ESPN identities.
candidates = defaultdict(list)

for row in audit:
    if row["category"] == "UNRESOLVED_CANDIDATE":
        candidates[row["espn_id"]].append(row)

# Verified participation from the FPL API.
minute_lookup = {}

for row in minutes:
    key = (
        row["espn_id"],
        row["espn_event_id"]
    )
    minute_lookup[key] = row

output = []

for row in v4:
    espn_id = row["espn_id"]
    event_id = row["event_id"]
    fpl_id = row["fpl_id"]
    status = row["status"]

    candidate_id = ""

    if status != "MATCHED":
        options = candidates.get(espn_id, [])

        if options:
            candidate_id = options[0]["fpl_id"]

    minute_row = minute_lookup.get(
        (espn_id, event_id)
    )

    fpl_minutes = ""
    minute_status = "NOT_CHECKED"

    if minute_row:
        fpl_minutes = minute_row["fpl_minutes"]
        minute_status = minute_row["status"]

    if status == "MATCHED":
        if minute_status == "MINUTES_CONFIRMED":
            decision = "PARTICIPATION_CONFIRMED"
        elif minute_status == "NOT_CHECKED":
            decision = "MATCHED_NOT_CROSSCHECKED"
        else:
            decision = "REVIEW"

    elif (
        candidate_id
        and minute_status == "MINUTES_CONFIRMED"
    ):
        decision = "CANDIDATE_PARTICIPATION_CONFIRMED"

    else:
        decision = "REVIEW"

    output.append({
        "event_id": event_id,
        "team": row["team"],
        "espn_id": espn_id,
        "espn_player": row["player"],
        "v4_fpl_id": fpl_id,
        "candidate_fpl_id": candidate_id,
        "fpl_minutes": fpl_minutes,
        "minute_status": minute_status,
        "decision": decision
    })

path = DATA / "espn_starting_xi_audit.csv"

with path.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0])
    )
    writer.writeheader()
    writer.writerows(output)

counts = Counter(r["decision"] for r in output)

summary = {
    "total_espn_starter_rows": len(output),
    "decision_counts": dict(counts),
    "note": (
        "FPL minutes confirm participation only. "
        "ESPN starter designation is not independently "
        "verified by this audit."
    )
}

with (DATA / "espn_starting_xi_summary.json").open(
    "w", encoding="utf-8"
) as f:
    json.dump(
        summary, f, indent=2, ensure_ascii=False
    )

print("STARTING XI AUDIT")
print(json.dumps(summary, indent=2))
print("Saved:", path)
