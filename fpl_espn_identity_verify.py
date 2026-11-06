
import csv
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path("data")
BASE = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/soccer/eng.1/summary?event="
)

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(
        request, timeout=25
    ) as response:
        return json.load(response)

audit = read_csv("espn_identity_audit.csv")
lineups = read_csv("espn_lineups.csv")

targets = {}

for row in audit:
    espn_id = row["espn_id"]

    if espn_id not in targets:
        targets[espn_id] = {
            "name": row["espn_name"],
            "team": row["espn_team"],
            "category": row["category"],
            "fpl_id": (
                row["fpl_id"]
                if row["category"] == "NEW_V4_MATCH"
                else ""
            )
        }

events_by_player = {}

for row in lineups:
    espn_id = row["espn_id"]

    if espn_id in targets:
        events_by_player.setdefault(
            espn_id, set()
        ).add(row["event_id"])

all_events = sorted({
    event
    for events in events_by_player.values()
    for event in events
})

event_data = {}
errors = {}

for event in all_events:
    try:
        event_data[event] = fetch_json(BASE + event)
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError
    ) as exc:
        errors[event] = str(exc)

    time.sleep(0.15)

def find_athlete(obj, target_id):
    found = []

    def walk(node):
        if isinstance(node, dict):
            athlete = node.get("athlete")

            if isinstance(athlete, dict):
                if str(athlete.get("id")) == target_id:
                    found.append(athlete)

            for value in node.values():
                walk(value)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return found

results = []

for espn_id, target in targets.items():
    events = events_by_player.get(espn_id, set())
    checked = 0
    found = 0
    names = set()
    urls = []

    for event in sorted(events):
        if event not in event_data:
            continue

        checked += 1
        athletes = find_athlete(
            event_data[event], espn_id
        )

        if athletes:
            found += 1

            for athlete in athletes:
                name = (
                    athlete.get("displayName")
                    or athlete.get("fullName")
                    or athlete.get("name")
                )
                if name:
                    names.add(name)

            urls.append(
                "https://www.espn.com/soccer/"
                "match/_/gameId/" + event
            )

    if checked == 0:
        status = "NOT_CHECKED"
    elif found == checked:
        status = "ESPN_ID_CONFIRMED"
    elif found > 0:
        status = "PARTIAL"
    else:
        status = "NOT_FOUND_IN_SUMMARIES"

    results.append({
        "espn_id": espn_id,
        "espn_name": target["name"],
        "espn_team": target["team"],
        "category": target["category"],
        "fpl_id": target["fpl_id"],
        "events_expected": len(events),
        "events_checked": checked,
        "events_found": found,
        "espn_names": "|".join(sorted(names)),
        "status": status,
        "source_urls": "|".join(urls)
    })

path = DATA / "espn_identity_source_check.csv"

with path.open(
    "w", newline="", encoding="utf-8"
) as f:
    writer = csv.DictWriter(
        f, fieldnames=list(results[0])
    )
    writer.writeheader()
    writer.writerows(results)

counts = Counter(r["status"] for r in results)

summary = {
    "players_checked": len(results),
    "events_requested": len(all_events),
    "events_downloaded": len(event_data),
    "event_errors": errors,
    "status_counts": dict(counts),
    "note": (
        "Confirms ESPN athlete IDs appear in match "
        "summaries. Does not independently confirm "
        "FPL identity, club registration or starts."
    )
}

with (DATA / "espn_identity_source_summary.json").open(
    "w", encoding="utf-8"
) as f:
    json.dump(
        summary, f,
        indent=2,
        ensure_ascii=False
    )

print("ESPN IDENTITY SOURCE CHECK")
print(json.dumps(summary, indent=2))
print("Saved:", path)
