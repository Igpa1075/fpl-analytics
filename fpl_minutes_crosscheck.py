
import csv
import json
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")
API = "https://fantasy.premierleague.com/api/"

def read_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)

audit = read_csv("espn_identity_audit.csv")
lineups = read_csv("espn_lineups.csv")
verified = read_csv("espn_fixture_verification_v2.csv")

fixture_map = {
    r["espn_event_id"]: int(r["fpl_fixture_id"])
    for r in verified
    if r["status"] == "VERIFIED"
}

targets = {}

for r in audit:
    espn_id = r["espn_id"]
    if espn_id not in targets:
        targets[espn_id] = r

appearances = defaultdict(list)

for r in lineups:
    if r["espn_id"] in targets:
        appearances[r["espn_id"]].append(r)

# Fetch each candidate FPL player only once.
history_cache = {}
errors = {}

for espn_id, target in targets.items():
    fpl_id = target["fpl_id"]

    if fpl_id in history_cache:
        continue

    try:
        data = fetch(
            API + "element-summary/" + fpl_id + "/"
        )
        history_cache[fpl_id] = {
            int(h["fixture"]): h
            for h in data.get("history", [])
            if h.get("fixture") is not None
        }
    except Exception as exc:
        errors[fpl_id] = str(exc)

    time.sleep(0.2)

output = []

for espn_id, target in targets.items():
    fpl_id = target["fpl_id"]
    history = history_cache.get(fpl_id, {})

    for appearance in appearances[espn_id]:
        event_id = appearance["event_id"]
        fixture_id = fixture_map.get(event_id)

        minutes = ""
        if fpl_id in errors:
            status = "API_ERROR"
        elif fixture_id is None:
            status = "FIXTURE_NOT_VERIFIED"
        elif fixture_id not in history:
            status = "NO_FPL_HISTORY"
        else:
            minutes = history[fixture_id].get("minutes", 0)
            if minutes > 0:
                status = "MINUTES_CONFIRMED"
            else:
                status = "ZERO_MINUTES"

        output.append({
            "category": target["category"],
            "espn_id": espn_id,
            "espn_player": target["espn_name"],
            "espn_team": target["espn_team"],
            "fpl_id": fpl_id,
            "fpl_player": target["fpl_name"],
            "espn_event_id": event_id,
            "fpl_fixture_id": fixture_id or "",
            "fpl_minutes": minutes,
            "status": status
        })

path = DATA / "espn_fpl_minutes_crosscheck.csv"

with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(output[0])
    )
    writer.writeheader()
    writer.writerows(output)

counts = Counter(r["status"] for r in output)

summary = {
    "players": len(targets),
    "appearances": len(output),
    "status_counts": dict(counts),
    "api_errors": errors,
    "note": (
        "Positive FPL minutes corroborate participation, "
        "not necessarily a start. Unresolved identities "
        "remain suggestions only."
    )
}

with (DATA / "espn_fpl_minutes_summary.json").open(
    "w", encoding="utf-8"
) as f:
    json.dump(
        summary, f, indent=2, ensure_ascii=False
    )

print("ESPN VS FPL MINUTES CROSSCHECK")
print(json.dumps(summary, indent=2))
print("Saved:", path)
