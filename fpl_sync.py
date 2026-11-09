
import json
import urllib.request\nimport urllib.error
from datetime import datetime, timezone
from pathlib import Path

ENTRY_ID = 5150250
BASE = "https://fantasy.premierleague.com/api"
OUT = Path("data")
OUT.mkdir(exist_ok=True)

def fetch(endpoint):
    url = BASE + endpoint
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def save(name, data):
    with open(OUT / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    bootstrap = fetch("/bootstrap-static/")
    fixtures = fetch("/fixtures/")
    entry = fetch(f"/entry/{ENTRY_ID}/")
    history = fetch(f"/entry/{ENTRY_ID}/history/")

    save("bootstrap.json", bootstrap)
    save("fixtures.json", fixtures)
    save("entry.json", entry)
    save("history.json", history)

    # A published GW squad is available after its deadline, even while the
    # bootstrap event's "finished" flag is still false (bonus corrections etc.).
    # Never use that flag alone to select the latest public picks.
    now = datetime.now(timezone.utc)
    eligible = sorted(
        (e for e in bootstrap.get("events", [])
         if datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) <= now),
        key=lambda e: int(e["id"]), reverse=True,
    )
    finished = [int(e["id"]) for e in bootstrap.get("events", []) if e.get("finished")]
    picks_path = OUT / "picks.json"
    old_gw = 0
    if picks_path.exists():
        try:
            old = json.loads(picks_path.read_text(encoding="utf-8"))
            old_gw = int(old.get("entry_history", {}).get("event") or 0)
        except (ValueError, TypeError, KeyError):
            old_gw = 0

    selected_gw = old_gw
    for event in eligible:
        gw = int(event["id"])
        if gw <= old_gw:
            break
        try:
            candidate = fetch(f"/entry/{ENTRY_ID}/event/{gw}/picks/")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                continue  # FPL has not published this GW's picks yet.
            raise
        if (len(candidate.get("picks", [])) != 15 or
                int(candidate.get("entry_history", {}).get("event") or 0) != gw):
            continue
        save("picks.json", candidate)
        selected_gw = gw
        print(f"Updated public squad to GW{gw}")
        break

    save("sync_status.json", {
        "entry_id": ENTRY_ID,
        "updated_at": now.isoformat(),
        "last_finished_gw": max(finished) if finished else None,
        "latest_public_picks_gw": selected_gw or None,
        "latest_history_gw": max((int(h["event"]) for h in history.get("current", [])), default=None),
    })

    print("FPL data updated successfully!")

if __name__ == "__main__":
    main()
