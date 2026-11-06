import json
import urllib.request
import urllib.parse
from datetime import date

BASE = "https://www.thesportsdb.com/api/v1/json/123/"

def get(endpoint, **params):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FPL-Analytics/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        print("REQUEST FAILED:", endpoint,
              type(e).__name__, str(e)[:160])
        return None

print("THESPORTSDB FREE API TEST")
print("League: English Premier League | 4328")
print("Season: 2026-2027")

data = get("eventsseason.php", id=4328, s="2026-2027")
if not isinstance(data, dict):
    raise SystemExit("Season request failed")

events = data.get("events") or []
print("Events returned:", len(events))

today = date.today().isoformat()
played = sorted(
    [e for e in events
     if e.get("dateEvent")
     and e["dateEvent"] <= today
     and e.get("intHomeScore") is not None],
    key=lambda e: e.get("dateEvent", ""),
    reverse=True
)
print("Completed matches:", len(played))

if not played:
    print("RESULT: No completed 2026/27 matches available")
    raise SystemExit(0)

found = 0
for event in played[:5]:
    eid = event.get("idEvent")
    print("\nMATCH:", event.get("strEvent"),
          event.get("dateEvent"), "ID:", eid)
    if not eid:
        continue

    response = get("lookuplineup.php", id=eid)
    if not isinstance(response, dict):
        continue

    lineups = (
        response.get("lineup")
        or response.get("lineups")
        or []
    )
    print("Lineup records:", len(lineups))

    if lineups:
        found += 1
        for player in lineups[:3]:
            print("Sample:", json.dumps(
                player, ensure_ascii=False
            )[:450])

print("\nMatches with lineup data:",
      found, "of", min(5, len(played)))
print("TEST FINISHED")
