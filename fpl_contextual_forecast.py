"""Prospective, conservative contextual overlay on the frozen FPL baseline.

ESPN formation slots are coarse role proxies, not physical tracking data.
Elite-manager and random-control cohorts are diagnostic only: selection bias
prevents using their ownership as a direct expected-points multiplier.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
BASE = DATA / "forecasts"
OUT = DATA / "contextual_forecasts"


def rows(name):
    path = DATA / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {int(r["fpl_id"]): r for r in csv.DictReader(handle) if r.get("fpl_id", "").isdigit()}


def adjust(forecast, starters, roles, captured_at):
    result = json.loads(json.dumps(forecast))
    applied = 0
    for player in result["predictions"]:
        pid = int(player["player_id"])
        original = float(player["expected_points"])
        factor = 1.0
        signals = []
        starter = starters.get(pid)
        if starter:
            matches = int(starter.get("matches_available") or 0)
            starts = int(starter.get("starts") or 0)
            # Require full verified 5-match coverage. Do not overreact to 1-2 games.
            if matches >= 5:
                rate = starts / matches
                # Only downside for uncertain minutes; already-stable starters
                # receive no unjustified upside.
                factor *= 0.85 + 0.15 * rate
                signals.append({"kind": "verified_espn_starts", "starts": starts,
                                "matches": matches, "factor": round(0.85 + 0.15 * rate, 3)})
        role = roles.get(pid)
        if role:
            matches = int(role.get("matches_available") or 0)
            observed = int(role.get("starts_with_position") or 0)
            # Treat attacking slots as evidence for a *small* exploratory
            # upside only when >=4 complete verified matches support the role.
            # Never infer an actual heatmap or FPL position reclassification.
            if matches >= 5 and observed >= 4:
                flag = role.get("position_flag", "")
                if (player["position_id"] == 2 and flag == "DEF_ADVANCED_SLOT_CANDIDATE"
                        and int(role.get("advanced_slot_starts") or 0) >= 4):
                    factor *= 1.04
                    signals.append({"kind": "advanced_defender_slot_proxy", "factor": 1.04})
                elif (player["position_id"] == 3 and flag == "MID_FORWARD_SLOT_CANDIDATE"):
                    factor *= 1.03
                    signals.append({"kind": "forward_midfielder_slot_proxy", "factor": 1.03})
        factor = min(1.05, max(0.85, factor))
        player["baseline_expected_points"] = original
        player["expected_points"] = round(original * factor, 3)
        player["context_factor"] = round(factor, 4)
        player["context_signals"] = signals
        if signals:
            applied += 1
    result["captured_at_utc"] = captured_at
    result["baseline_captured_at_utc"] = forecast["captured_at_utc"]
    result["method"] = "baseline_plus_verified_espn_context_v1_experimental"
    result["context_applied_players"] = applied
    result["context_inputs"] = ["data/starter_stability.csv", "data/position_analysis.csv"]
    result["elite_control_usage"] = "diagnostic_only_no_points_adjustment"
    result["warnings"] = forecast.get("warnings", []) + [
        "ESPN slots are approximate, not tracking coordinates.",
        "Starter and role factors are manually chosen, NOT validated on held-out GWs.",
        "Elite top-100 and random ID sample are biased; no direct points uplift.",
        "Context is observed at overlay time; never apply to already-played GWs.",
    ]
    return result


def main():
    files = sorted(BASE.glob("*.json"))
    if not files:
        print("No frozen baseline forecast.")
        return
    forecasts = [(json.loads(p.read_text(encoding="utf-8")), p) for p in files]
    baseline, source = max(forecasts, key=lambda x: x[0]["captured_at_utc"])
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(baseline["deadline_utc"].replace("Z", "+00:00"))
    if now >= deadline:
        print("Target deadline already passed; not creating retrospective overlay.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / source.name
    if target.exists():
        print(f"Preserving frozen contextual forecast {target}")
        return
    enriched = adjust(baseline, rows("starter_stability.csv"),
                      rows("position_analysis.csv"), now.isoformat())
    target.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contextual GW{enriched['target_gw']}: {enriched['context_applied_players']} players with signals")


if __name__ == "__main__":
    main()
