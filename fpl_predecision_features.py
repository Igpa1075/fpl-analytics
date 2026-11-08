"""Leakage-safe manager/GW feature table for retrospective FPL research.

Every feature for decision GW t comes from the published record of GW t-1.
Outcomes are kept separately, NEVER used as model features. This does not
reconstruct true pre-deadline player forecasts or transfer availability.
"""
import json
from pathlib import Path

DATA = Path("data")
SOURCE = DATA / "control_history.json"
OUTPUT = DATA / "predecision_features.json"
GWS = range(2, 10)


def valid(gws, gw):
    r = gws.get(str(gw))
    return r if isinstance(r, dict) and r.get("status") == "ok" else None


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def build(managers):
    rows = []
    for entry, gws in managers.items():
        for gw in GWS:
            prev = valid(gws, gw - 1)
            current = valid(gws, gw)
            if prev is None or current is None:
                continue
            previous_players = prev.get("players") or []
            current_players = current.get("players") or []
            if len(previous_players) != 15 or len(current_players) != 15:
                continue
            baseline = prev.get("total_points")
            if not numeric(baseline):
                continue
            # Current picks are post-deadline: decision labels and outcomes ONLY.
            previous_set = set(previous_players)
            current_set = set(current_players)
            outcome = current.get("total_points")
            row = {
                "manager_id": str(entry),
                "decision_gw": gw,
                "features_before_gw": {
                    "prior_gw": gw - 1,
                    "prior_total_points": baseline,
                    "prior_overall_rank": prev.get("overall_rank"),
                    "prior_team_value_tenths_million": prev.get("team_value"),
                    "prior_bank_tenths_million": prev.get("bank"),
                    "prior_gw_points": prev.get("points"),
                    "prior_gw_transfer_cost": prev.get("transfer_cost"),
                    "prior_gw_captain": prev.get("captain"),
                    "prior_gw_players": previous_players,
                    "prior_gw_starting_xi": prev.get("starting_xi"),
                },
                "decision_labels_after_deadline": {
                    "chip": current.get("chip"),
                    "captain": current.get("captain"),
                    "transfers_reported": current.get("transfers"),
                    "players_added_vs_previous_gw": sorted(current_set - previous_set),
                    "players_removed_vs_previous_gw": sorted(previous_set - current_set),
                },
                "outcome_after_gw": {
                    "gw_points": current.get("points"),
                    "gw_transfer_cost": current.get("transfer_cost"),
                    "cumulative_points_gain": outcome - baseline if numeric(outcome) else None,
                },
            }
            rows.append(row)
    return rows


def main():
    if not SOURCE.exists():
        print("Control history not yet available; skipping feature table.")
        return
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = build(data.get("managers", {}))
    report = {
        "design": "prior_completed_GW_features_only",
        "source_cohort_seed": data.get("cohort_seed"),
        "rows": rows,
        "summary": {
            "rows": len(rows),
            "managers": len({r["manager_id"] for r in rows}),
            "by_decision_gw": {str(gw): sum(r["decision_gw"] == gw for r in rows)
                               for gw in GWS},
        },
        "limitations": [
            "Previous GW records are a retrospective approximation, not an archived deadline snapshot.",
            "Historical injuries, fixture difficulty, prices and expected points are NOT reconstructed.",
            "Transfers/chips/captain for decision GW are labels observed after deadline, not features.",
            "No future GW data is allowed in features_before_gw.",
            "Random entry-ID sampling and selection/missingness bias remain unresolved.",
            "This dataset is NOT sufficient to validate prospective transfer recommendations.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
