"""Refresh latest publicly visible FPL entry picks, never infer predeadline moves.

The official public entry/event/picks endpoint exposes a GW squad only
after that GW's deadline. Private transfers, live bank and free transfers
are not accessible here; do not fabricate them.
"""
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
API = "https://fantasy.premierleague.com/api"
ENTRY_ID = 5150250


def get(path):
    request = urllib.request.Request(API + path, headers={
        "User-Agent": "fpl-analytics/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.load(response)


def main():
    bootstrap = get("/bootstrap-static/")
    now = datetime.now(timezone.utc)
    eligible = sorted((e for e in bootstrap["events"]
                       if datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) <= now),
                      key=lambda e: e["id"], reverse=True)
    existing_path = DATA / "picks.json"
    existing = json.loads(existing_path.read_text(encoding="utf-8")) if existing_path.exists() else None
    old_gw = int((existing or {}).get("entry_history", {}).get("event") or 0)
    selected = existing
    for event in eligible:
        gw = int(event["id"])
        if gw <= old_gw:
            break
        try:
            candidate = get(f"/entry/{ENTRY_ID}/event/{gw}/picks/")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                continue
            raise
        if len(candidate.get("picks", [])) != 15:
            continue
        selected = candidate
        old_gw = gw
        break
    DATA.mkdir(exist_ok=True)
    if selected is not None:
        existing_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    future = [e for e in bootstrap["events"]
              if datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) > now]
    target = min(future, key=lambda e: e["deadline_time"])["id"] if future else None
    status = {
        "entry_id": ENTRY_ID,
        "latest_public_picks_gw": old_gw or None,
        "next_deadline_gw": target,
        "public_squad_is_current_for_next_deadline": False,
        "source": "Official public entry/event/picks endpoint; published only after GW deadline",
        "limitations": [
            "Predeadline private transfers and resulting squad are not publicly visible.",
            "Last published bank is historical, not guaranteed current.",
            "Individual current selling prices and free-transfer balance require private FPL data.",
            "Never automatically execute a transfer based on this public squad.",
        ],
    }
    (DATA / "squad_freshness.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Latest public picks: GW{old_gw or 'unknown'}; next GW{target}; "
          "predeadline current squad remains unverified")


if __name__ == "__main__":
    main()
