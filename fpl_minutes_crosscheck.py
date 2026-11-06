
import csv
import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path("data")
API = "https://fantasy.premierleague.com/api/"


def read_csv(filename):
    with (DATA / filename).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))


def fetch_player(player_id):
    url = API + f"element-summary/{player_id}/"

    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(
                request, timeout=30
            ) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


lineups = read_csv("espn_fpl_matches_v4.csv")
audit = read_csv("espn_identity_audit.csv")
fixtures = read_csv("espn_fixture_verification_v2.csv")

fixture_map = {
    r["espn_event_id"]: r["fpl_fixture_id"]
    for r in fixtures
    if r["status"] == "VERIFIED"
    and r["fpl_fixture_id"]
}

# Candidates are not automatically accepted as matches.
candidate_map = {}

for row in audit:
    if row["category"] != "UNRESOLVED_CANDIDATE":
        continue

    espn_id = row["espn_id"]
    candidate_map.setdefault(espn_id, []).append(
        row["fpl_id"]
    )

# Use a candidate only if the audit lists exactly one.
unique_candidates = {
    espn_id: ids[0]
    for espn_id, ids in candidate_map.items()
    if len(set(ids)) == 1
}

player_ids = set()

for row in lineups:
    player_id = row["fpl_id"]

    if not player_id:
        player_id = unique_candidates.get(
            row["espn_id"], ""
        )

    if player_id:
        player_ids.add(player_id)

print("Players to request:", len(player_ids))

history_cache = {}
errors = {}

for index, player_id in enumerate(
    sorted(player_ids), start=1
):
    try:
        data = fetch_player(player_id)
        history_cache[player_id] = {
            str(h["fixture"]): h
            for h in data.get("history", [])
            if h.get("fixture") is not None
        }
    except Exception as exc:
        errors[player_id] = str(exc)

    if index % 50 == 0:
        print(f"Downloaded {index}/{len(player_ids)}")

    time.sleep(0.15)

results = []

for row in lineups:
    espn_id = row["espn_id"]
    event_id = row["event_id"]
    matched_id = row["fpl_id"]
    candidate_id = unique_candidates.get(
        espn_id, ""
    )

    player_id = matched_id or candidate_id
    fixture_id = fixture_map.get(event_id, "")
    minutes = ""

    if not player_id:
        status = "NO_ID_CANDIDATE"

    elif not fixture_id:
        status = "FIXTURE_NOT_VERIFIED"

    elif player_id in errors:
        status = "API_ERROR"

    else:
        history = history_cache.get(player_id, {})
        match = history.get(fixture_id)

        if match is None:
            status = "NO_FPL_HISTORY"
        else:
            minutes = match.get("minutes", 0)

            if minutes > 0:
                status = "MINUTES_CONFIRMED"
            else:
                status = "ZERO_MINUTES"

    results.append({
        "category": (
            "V4_MATCHED"
            if matched_id else "UNRESOLVED_CANDIDATE"
        ),
        "espn_id": espn_id,
        "espn_player": row["player"],
        "espn_team": row["team"],
        "fpl_id": player_id,
        "fpl_player": "",
        "espn_event_id": event_id,
        "fpl_fixture_id": fixture_id,
        "fpl_minutes": minutes,
        "status": status
    })

fields = [
    "category", "espn_id", "espn_player",
    "espn_team", "fpl_id", "fpl_player",
    "espn_event_id", "fpl_fixture_id",
    "fpl_minutes", "status"
]

with (
    DATA / "espn_fpl_minutes_crosscheck.csv"
).open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=fields
    )
    writer.writeheader()
    writer.writerows(results)

counts = Counter(
    row["status"] for row in results
)

summary = {
    "total_espn_rows": len(lineups),
    "rows_checked": len(results),
    "unique_fpl_ids_requested": len(player_ids),
    "status_counts": dict(counts),
    "api_errors": errors,
    "note": (
        "FPL minutes corroborate participation, "
        "not starting XI. Candidate identities "
        "remain unconfirmed. Unverified fixtures "
        "must be reviewed separately."
    )
}

with (
    DATA / "espn_fpl_minutes_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f, indent=2, ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
