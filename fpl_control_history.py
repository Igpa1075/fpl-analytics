"""Incrementally collect published GW1-9 decisions for sampled control managers."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA = Path("data")
COHORT = DATA / "control_cohort.json"
OUTPUT = DATA / "control_history.json"
GW_MAX = 9
MANAGERS_PER_RUN = 25
API = "https://fantasy.premierleague.com/api"


def save(state):
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(OUTPUT)


def get_picks(entry_id, gw):
    req = urllib.request.Request(
        f"{API}/entry/{entry_id}/event/{gw}/picks/",
        headers={"User-Agent": "FPL-research/1.0", "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.load(response), "ok"
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None, "not_available"
            if error.code in (403, 429):
                return None, "pause"
            print(f"HTTP {error.code} for entry {entry_id}, GW{gw}")
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"Temporary error for entry {entry_id}, GW{gw}: {error}")
        time.sleep(2 * (attempt + 1))
    return None, "pause"


def main():
    if not COHORT.exists():
        print("No cohort yet; waiting for collector.")
        return
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    if OUTPUT.exists():
        state = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if state.get("cohort_seed") != cohort["seed"]:
            raise RuntimeError("Control cohort changed; refusing to mix samples")
    else:
        state = {
            "cohort_seed": cohort["seed"],
            "gameweeks": list(range(1, GW_MAX + 1)),
            "managers": {},
            "limitations": [
                "Retrospective GW picks are not pre-deadline predictions.",
                "Comparison with current top-100 is affected by selection/survivorship bias.",
                "No causal claims about chips, captains or transfers.",
                "Entry-ID sampling is not yet proven representative.",
            ],
        }

    processed_managers = 0
    pause = False
    for entry_id in cohort["sample_ids"]:
        key = str(entry_id)
        if cohort["results"].get(key, {}).get("status") != "ok":
            continue
        existing = state["managers"].setdefault(key, {})
        if len(existing) == GW_MAX:
            continue
        if processed_managers >= MANAGERS_PER_RUN:
            break
        processed_managers += 1
        for gw in range(1, GW_MAX + 1):
            gw_key = str(gw)
            if gw_key in existing:
                continue
            data, status = get_picks(entry_id, gw)
            if status == "pause":
                pause = True
                break
            if status == "not_available":
                existing[gw_key] = {"status": "not_available"}
            else:
                picks = data.get("picks", [])
                if len(picks) != 15:
                    print(f"Unexpected picks for entry {entry_id}, GW{gw}; retry later")
                    pause = True
                    break
                event = data.get("entry_history") or {}
                existing[gw_key] = {
                    "status": "ok",
                    "players": [p["element"] for p in picks],
                    "captain": next((p["element"] for p in picks if p.get("is_captain")), None),
                    "vice_captain": next((p["element"] for p in picks if p.get("is_vice_captain")), None),
                    "chip": data.get("active_chip"),
                    "transfers": event.get("event_transfers"),
                    "transfer_cost": event.get("event_transfers_cost"),
                    "points": event.get("points"),
                    "total_points": event.get("total_points"),
                    "overall_rank": event.get("overall_rank"),
                }
            time.sleep(0.3)
        save(state)
        if pause:
            print("API limit/error; progress saved for next run")
            break

    state["summary"] = {
        "valid_control_entries": sum(r.get("status") == "ok" for r in cohort["results"].values()),
        "managers_started": len(state["managers"]),
        "managers_complete": sum(len(gws) == GW_MAX for gws in state["managers"].values()),
        "successful_gw_records": sum(
            r.get("status") == "ok" for gws in state["managers"].values() for r in gws.values()
        ),
    }
    save(state)
    print(json.dumps(state["summary"], indent=2))


if __name__ == "__main__":
    main()
