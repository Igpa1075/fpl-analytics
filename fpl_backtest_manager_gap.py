"""Decompose the observed manager-vs-proxy-model GW1-10 scoring gap.

The manager's published points are before hits. Model has no wildcard.
This is an accounting diagnostic, not causal attribution.
"""
import json
from fpl_backtest_hold_baseline import D


def main():
    model = json.loads((D / "backtest_budget_constrained_proxy.json").read_text(encoding="utf-8"))
    actual = json.loads((D / "backtest_scoring_validation.json").read_text(encoding="utf-8"))
    actual_by_gw = {int(r["gw"]): r for r in actual["gws"]}
    rows = []
    for m in model["gws"]:
        gw = int(m["gw"])
        a = actual_by_gw[gw]
        gross = int(a["official_points"])
        hit = int(a["official_transfer_cost"])
        net = gross - hit
        points = int(m["points"])
        rows.append({
            "gw": gw,
            "manager_gross": gross,
            "manager_hit_cost": hit,
            "manager_net": net,
            "model_points": points,
            "model_minus_manager_net": points - net,
            "model_transfer": m.get("transfer"),
            "manager_chip": a.get("active_chip"),
            "model_captain_id": m.get("captain"),
            "model_autosubs": len(m.get("autosubs", []))
        })
    result = {
        "status": "verified_arithmetic_not_causal_explanation",
        "manager_gross": sum(r["manager_gross"] for r in rows),
        "manager_hits": sum(r["manager_hit_cost"] for r in rows),
        "manager_net": sum(r["manager_net"] for r in rows),
        "model_total": sum(r["model_points"] for r in rows),
        "model_minus_manager_net": sum(r["model_minus_manager_net"] for r in rows),
        "model_better_gws": [r["gw"] for r in rows if r["model_minus_manager_net"] > 0],
        "manager_better_gws": [r["gw"] for r in rows if r["model_minus_manager_net"] < 0],
        "manager_wildcard_gws": [r["gw"] for r in rows if r["manager_chip"] == "wildcard"],
        "rows": rows,
        "limitations": [
            "GW-level score differences cannot be causally assigned to individual transfers or captaincy.",
            "Manager used wildcard in GW8; model does not implement chips.",
            "Model uses unverified fixture-time prices, not historical deadline prices.",
            "GW1 squad and XI were inherited from manager."
        ]
    }
    assert result["manager_net"] == 528
    assert result["model_total"] == 510
    (D / "backtest_manager_gap_decomposition.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manager_net": result["manager_net"],
                      "model_total": result["model_total"],
                      "gap": result["model_minus_manager_net"],
                      "manager_wildcard_gws": result["manager_wildcard_gws"]}))


if __name__ == "__main__":
    main()
