"""Cross-check official FPL manager picks against collected historical player points.

This is a scoring validation of the user's ACTUAL selections, not a
counterfactual backtest or a predictive strategy.
"""
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
API = "https://fantasy.premierleague.com/api"


def fetch(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "FPL-score-validation/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def score_picks(picks, points_by_player):
    """Multipliers reflect FPL's published autosubs, captain and chips."""
    return sum(int(p.get("multiplier") or 0) * points_by_player.get(str(p["element"]), 0)
               for p in picks)


def main():
    history_data = json.loads((DATA / "historical_players_gw1_10.json").read_text(encoding="utf-8"))
    bootstrap = json.loads((DATA / "bootstrap.json").read_text(encoding="utf-8"))
    entry_id = 5150250
    entry_path = DATA / "entry.json"
    if entry_path.exists():
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        entry_id = int(entry.get("id") or entry_id)
    fixtures = history_data.get("players", {})
    rows = []
    for gw in range(1, 11):
        official = fetch(f"/entry/{entry_id}/event/{gw}/picks/")
        picks = official.get("picks", [])
        history = official.get("entry_history", {})
        selected_ids = {str(p["element"]) for p in picks}
        missing = sorted(selected_ids - fixtures.keys(), key=int)
        points = {}
        for pid in selected_ids & fixtures.keys():
            points[pid] = sum(int(m.get("total_points") or 0)
                              for m in fixtures[pid] if m.get("gw") == gw)
        raw = score_picks(picks, points)
        hit = int(history.get("event_transfers_cost") or 0)
        official_points = history.get("points")
        # Some FPL chips alter how scoring is represented. Explicitly surface mismatches.
        computed = raw if not missing else None
        rows.append({
            "gw": gw,
            "selected_player_count": len(selected_ids),
            "missing_player_ids": missing,
            "official_points": official_points,
            "official_transfer_cost": hit,
            "computed_points": computed,
            "matches_official": computed == official_points if computed is not None else None,
            "active_chip": official.get("active_chip"),
        })
    complete = [r for r in rows if r["computed_points"] is not None]
    report = {
        "entry_id": entry_id,
        "source": "FPL official entry picks and player element-summary history",
        "gws": rows,
        "fully_scored_gws": len(complete),
        "matching_gws": sum(r["matches_official"] is True for r in complete),
        "notes": [
            "Official picks are the manager's real historic choices; not a hindsight-free simulated strategy.",
            "Official picks multipliers should include published captaincy and autosub effects.",
            "FPL entry_history.points is the gameweek score before transfer-hit deductions; transfer cost is reported separately.",
            "An incomplete player-history collection prevents scoring some gameweeks.",
            "Scores may differ for special chips or incomplete live gameweeks; mismatches are reported.",
        ],
    }
    dest = DATA / "backtest_scoring_validation.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fully_scored_gws": len(complete), "matching_gws": report["matching_gws"]}))


if __name__ == "__main__":
    main()
