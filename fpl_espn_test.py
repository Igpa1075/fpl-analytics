import json
import urllib.request

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"

def get(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except Exception as e:
        print("REQUEST ERROR:", type(e).__name__, str(e)[:160])
        return None

print("ESPN PREMIER LEAGUE LINEUP TEST")
data = get("/scoreboard?dates=20261031")

if not data:
    raise SystemExit("Scoreboard unavailable")

events = data.get("events") or []
print("Events returned:", len(events))

completed = [
    e for e in events
    if e.get("status", {}).get("type", {}).get("completed")
]
print("Completed matches:", len(completed))

for event in completed[-5:]:
    event_id = event.get("id")
    print("\nMATCH:", event.get("name"), event_id)
    summary = get("/summary?event=" + str(event_id))
    if not summary:
        continue
    rosters = summary.get("rosters") or []
    print("Rosters:", len(rosters))
    for roster in rosters:
        athletes = roster.get("roster") or []
        starters = [
            p for p in athletes
            if p.get("starter") is True
        ]
        print("Team:", roster.get("team", {}).get("displayName"))
        print("Roster players:", len(athletes),
              "starters:", len(starters))
        for p in starters[:3]:
            athlete = p.get("athlete") or {}
            print(
                "Sample:", athlete.get("displayName"),
                "| position:", athlete.get("position"),
                "| formationPlace:", p.get("formationPlace")
            )

print("\nTEST FINISHED")
