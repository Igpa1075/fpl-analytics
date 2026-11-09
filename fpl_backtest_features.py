"""Build strictly lagged FPL player features for GW1-10.

Historical fixture values are excluded from prices and all predictive inputs.
GW1 has no current-season match evidence; features remain null rather than
using post-deadline season aggregates. These are features, not predictions.
"""
import json
from collections import defaultdict
from pathlib import Path

D = Path(__file__).resolve().parent / "data"


def build(records, target_gws=range(1, 11)):
    output = {}
    for pid, matches in records.items():
        ordered = sorted(matches, key=lambda m: (int(m["gw"]), str(m.get("kickoff_time") or ""), int(m.get("fixture") or 0)))
        output[str(pid)] = {}
        for gw in target_gws:
            prior = [m for m in ordered if int(m["gw"]) < gw]
            minutes = sum(int(m.get("minutes") or 0) for m in prior)
            points = sum(int(m.get("total_points") or 0) for m in prior)
            starts_proxy = sum(int(m.get("minutes") or 0) >= 60 for m in prior)
            last3 = [m for m in prior if int(m["gw"]) >= gw - 3]
            output[str(pid)][str(gw)] = {
                "prior_fixture_rows": len(prior),
                "prior_minutes": minutes,
                "prior_points": points,
                "prior_points_per_90": round(points * 90 / minutes, 3) if minutes else None,
                "prior_60min_appearances": starts_proxy,
                "last3_fixture_rows": len(last3),
                "last3_minutes": sum(int(m.get("minutes") or 0) for m in last3),
                "last3_points": sum(int(m.get("total_points") or 0) for m in last3),
                "price_before_deadline": None,
                "availability_before_deadline": None,
            }
    return output


def main():
    src = D / "historical_players_gw1_10.json"
    state = json.loads(src.read_text(encoding="utf-8"))
    records = state.get("players", {})
    features = build(records)
    out = {
        "method": "strictly_lagged_current_season_fixture_features",
        "players_processed": len(features),
        "features": features,
        "limitations": [
            "Only fixture data from GW strictly less than target GW are used.",
            "GW1 has no current-season performance data; prior-season data not collected.",
            "Historical fixture prices are not valid pre-deadline buying prices.",
            "No lineup, transfers, chip, injury forecast, or expected-points model yet.",
        ],
    }
    target = D / "backtest_lagged_features.json"
    target.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"players_processed": len(features), "target_gws": 10}))


if __name__ == "__main__":
    main()
