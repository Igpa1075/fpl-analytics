"""Archive immutable daily FPL market snapshots for forward-only evaluation.

Snapshots are captured at run time, not reconstructed as historical facts.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://fantasy.premierleague.com/api"
ROOT = Path("data") / "snapshots"


def fetch(endpoint):
    req = urllib.request.Request(BASE + endpoint, headers={
        "User-Agent": "fpl-analytics/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def main():
    now = datetime.now(timezone.utc)
    path = ROOT / (now.strftime("%Y-%m-%d") + ".json")
    if path.exists():
        print(f"Already archived: {path}; keeping original snapshot immutable")
        return
    bootstrap = fetch("/bootstrap-static/")
    fixtures = fetch("/fixtures/")
    upcoming = sorted(
        (e for e in bootstrap.get("events", []) if e.get("deadline_time")
         and datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) > now),
        key=lambda e: e["deadline_time"])
    next_event = upcoming[0] if upcoming else None
    # Retain the complete published player fields, including status, news,
    # price, availability and recent performance. No later updates overwrite it.
    snapshot = {
        "captured_at_utc": now.isoformat(),
        "source": "official_fpl_api",
        "next_event_id": next_event["id"] if next_event else None,
        "next_deadline_utc": next_event["deadline_time"] if next_event else None,
        "bootstrap": {
            "elements": bootstrap.get("elements", []),
            "teams": bootstrap.get("teams", []),
            "element_types": bootstrap.get("element_types", []),
            "events": bootstrap.get("events", []),
        },
        "fixtures": fixtures,
        "limitations": [
            "This is a daily observation, not guaranteed to be the final pre-deadline state.",
            "Only snapshots captured before a deadline can be used as inputs for that GW.",
            "Fixtures and injury statuses may change between snapshot and deadline.",
            "FPL API statistics can include earlier completed matches; freeze by captured_at_utc.",
        ],
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    print(f"Archived {path}: {len(snapshot['bootstrap']['elements'])} players, "
          f"{len(fixtures)} fixtures, next GW {snapshot['next_event_id']}")


if __name__ == "__main__":
    main()
