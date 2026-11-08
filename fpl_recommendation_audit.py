"""Audit FPL recommendation outputs without claiming predictive accuracy.

Hard invariants raise an error; methodological limitations become explicit flags.
No future match results are used.
"""
import json
from collections import Counter
from pathlib import Path

DATA = Path("data")
OUTPUT = DATA / "recommendation_audit.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition, message, errors):
    if not condition:
        errors.append(message)


def main():
    required = ["lineup_recommendation.json", "transfer_scenarios.json",
                "multiweek_transfer_plan.json"]
    missing = [name for name in required if not (DATA / name).exists()]
    if missing:
        print("Audit pending; missing: " + ", ".join(missing))
        return
    lineup, transfers, multi = (load(DATA / name) for name in required)
    errors, warnings = [], []
    gw = lineup["target_gw"]
    check(gw == transfers["target_gw"] == multi["target_gw"],
          "Different target GWs across reports", errors)
    xi = lineup["starting_xi"]
    ids = [p["player_id"] for p in xi]
    counts = Counter(p["position_id"] for p in xi)
    check(len(xi) == 11 and len(set(ids)) == 11, "XI must contain 11 unique players", errors)
    check(counts[1] == 1 and 3 <= counts[2] <= 5 and 2 <= counts[3] <= 5
          and 1 <= counts[4] <= 3, "Illegal XI formation", errors)
    check(lineup["captain"]["player_id"] in ids, "Captain not in XI", errors)
    check(lineup["vice_captain"]["player_id"] in ids, "Vice not in XI", errors)
    check(lineup["vice_captain"]["player_id"] != lineup["captain"]["player_id"],
          "Captain and vice must differ", errors)
    expected = sum(p["expected_points"] for p in xi) + lineup["captain"]["expected_points"]
    check(abs(expected - lineup["expected_xi_points_with_captain"]) < .02,
          "Lineup expected points inconsistent", errors)
    check(len(lineup["bench_goalkeeper"]) == 1 and
          len(lineup["bench_outfield_order"]) == 3, "Bench must contain 1 GK and 3 outfield", errors)
    hold = transfers["scenarios"]["0"]
    check(len(hold) == 1 and not hold[0]["transfers"], "Missing hold baseline", errors)
    check(abs(hold[0]["projected_xi_with_captain"] -
              lineup["expected_xi_points_with_captain"]) < .02,
          "Hold baseline differs from optimized XI", errors)
    check(abs(multi["hold_five_gw_expected_points"] -
              next(r["five_gw_gross_points"] for r in multi["ranked_scenarios"]
                   if r["transfer_count"] == 0)) < .02,
          "Multiweek hold baseline inconsistent", errors)
    for row in multi["ranked_scenarios"]:
        check(row["transfer_count"] == len(row["transfers"]),
              "Incorrect transfer count", errors)
        check(len(row["weekly"]) == multi["last_gw"] - gw + 1,
              "Incorrect future GW horizon", errors)
        check(abs(sum(x["expected_xi_with_captain"] for x in row["weekly"]) -
                  row["five_gw_gross_points"]) < .02,
              "Multiweek total differs from weekly points", errors)
        check(abs(row["gross_gain_vs_hold"] -
                  (row["five_gw_gross_points"] - multi["hold_five_gw_expected_points"])) < .02,
              "Multiweek gain differs from baseline", errors)
    latest_picks_gw = lineup.get("squad_event")
    if isinstance(latest_picks_gw, int) and latest_picks_gw < gw - 1:
        warnings.append(f"Squad is from GW{latest_picks_gw}; target is GW{gw}. "
                        "Squad may be outdated.")
    warnings.extend([
        "No actual free-transfer count or individual selling prices: transfer plans are advisory.",
        "No out-of-sample evaluation yet unless completed-GW forecast evaluations exist.",
        "Five-GW projections reuse frozen form and availability; not independent future forecasts.",
        "Two-transfer shortlist is not exhaustive and may exclude better long-term choices.",
        "Identical projected scores across different transfer plans may reflect unchanged XI.",
    ])
    evaluation = DATA / "forecast_evaluation.json"
    evaluated = load(evaluation).get("completed_gws_evaluated", 0) if evaluation.exists() else 0
    report = {
        "target_gw": gw,
        "passed": not errors,
        "error_count": len(errors),
        "errors": errors,
        "warnings": warnings,
        "completed_gws_evaluated": evaluated,
        "ready_for_automatic_transfers": False,
        "checks": {
            "lineup_formation": counts,
            "starting_xi_expected_points": lineup["expected_xi_points_with_captain"],
            "transfer_scenarios": sum(len(v) for v in transfers["scenarios"].values()),
            "multiweek_scenarios": len(multi["ranked_scenarios"]),
        },
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recommendation audit: {len(errors)} errors, {len(warnings)} warnings, "
          f"{evaluated} evaluated GWs")
    if errors:
        raise ValueError("; ".join(errors))


if __name__ == "__main__":
    main()
