import os
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://v3.football.api-sports.io"
KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()

def request(endpoint, params=None):
    url = BASE + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        print("HTTP error:", e.code)
    except Exception as e:
        print("Connection error:", type(e).__name__)
    return None

print("API-FOOTBALL CONNECTION TEST")

if not KEY:
    print("FAIL: API_FOOTBALL_KEY is missing")
    raise SystemExit(1)

status = request("/status")
if status is None:
    print("FAIL: API connection")
    raise SystemExit(1)
if status.get("errors"):
    print("API error:", str(status["errors"])[:300])
    raise SystemExit(1)

print("API connection: OK")
account = status.get("response", {})
requests = account.get("requests", {})
print("Daily limit:", requests.get("limit_day", "unknown"))
print("Used today:", requests.get("current", "unknown"))

fixtures = request("/fixtures", {"league": 39, "season": 2026, "last": 3})
if fixtures is None:
    print("Fixtures: request failed")
    raise SystemExit(0)
if fixtures.get("errors"):
    print("Fixtures API error:", str(fixtures["errors"])[:300])
    raise SystemExit(0)

matches = fixtures.get("response", [])
print("Premier League fixtures found:", len(matches))
if not matches:
    print("No completed fixtures returned.")
    raise SystemExit(0)

fixture_id = matches[0]["fixture"]["id"]
print("Sample fixture ID:", fixture_id)
lineups = request("/fixtures/lineups", {"fixture": fixture_id})
if lineups is None:
    print("Lineups: request failed")
    raise SystemExit(0)
if lineups.get("errors"):
    print("Lineups API error:", str(lineups["errors"])[:300])
    raise SystemExit(0)

teams = lineups.get("response", [])
print("Lineup teams returned:", len(teams))
for team in teams:
    name = team.get("team", {}).get("name", "Unknown")
    formation = team.get("formation", "Unknown")
    starters = team.get("startXI", [])
    positions = [p.get("player", {}).get("pos") for p in starters]
    print(name, "| formation:", formation, "| starters:", len(starters), "| positions:", positions)

print("TEST FINISHED")
