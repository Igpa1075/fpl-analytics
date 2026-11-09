
import json
import urllib.request
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

    events = bootstrap.get("events", [])
    finished = [e for e in events if e.get("finished")]

    if finished:
        gw = max(e["id"] for e in finished)
        picks = fetch(f"/entry/{ENTRY_ID}/event/{gw}/picks/")
        picks_path = OUT / "picks.json"
        old_gw = 0
        if picks_path.exists():
            try:
                old = json.loads(picks_path.read_text(encoding="utf-8"))
                old_gw = int(old.get("entry_history", {}).get("event") or 0)
            except (ValueError, TypeError, KeyError):
                old_gw = 0
        if gw >= old_gw:
            save("picks.json", picks)
        else:
            print(f"Preserving newer public picks GW{old_gw}; sync finished GW{gw}")

    save("sync_status.json", {
        "entry_id": ENTRY_ID,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_finished_gw": gw if finished else None
    })

    print("FPL data updated successfully!")

if __name__ == "__main__":
    main()
