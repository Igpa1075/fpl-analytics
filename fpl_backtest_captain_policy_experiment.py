"""Counterfactual captain policies on the SAME proxy-model squads and starting XIs.

All captain rankings use only completed prior GWs. Scores use actual GW results
only after the decision, and preserve captain->vice fallback. No selection
of the best policy based on future scores is represented as a live forecast.
"""
import json
from fpl_backtest_hold_baseline import D


def history(rows, gw, window):
    return [r for r in rows if gw-window <= int(r["gw"]) < gw]


def rank(pid, players, gw, policy):
    rows = history(players[str(pid)], gw, 3 if policy != "season_form" else 10)
    pts = [int(r.get("total_points") or 0) for r in rows]
    mins = [int(r.get("minutes") or 0) for r in rows]
    form = sum(pts)
    starts = sum(m >= 60 for m in mins)
    appearances = sum(m > 0 for m in mins)
    if policy == "form_3":
        return (form,)
    if policy == "minutes_weighted":
        return (form * (1 + starts) / 4, starts, form)
    if policy == "reliability":
        return (starts, appearances, form)
    if policy == "season_form":
        return (form, starts, appearances)
    raise ValueError(policy)


def main():
    model = json.loads((D / "backtest_budget_constrained_proxy.json").read_text(encoding="utf-8"))
    players = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    boot = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    pos = {int(p["id"]): int(p["element_type"]) for p in boot["elements"]}
    policies = ("form_3", "minutes_weighted", "reliability", "season_form")
    output = {policy: [] for policy in policies}
    for row in model["gws"]:
        gw = int(row["gw"])
        final_xi = list(map(int, row["final_xi"]))
        initial_xi = final_xi.copy()
        for sub in reversed(row["autosubs"]):
            initial_xi.remove(int(sub["in"]))
            initial_xi.append(int(sub["out"]))
        assert len(initial_xi) == 11 and len(set(initial_xi)) == 11
        eligible = [p for p in initial_xi if pos[p] != 1]
        pts = {p: sum(int(r.get("total_points") or 0) for r in players[str(p)]
                      if int(r["gw"]) == gw) for p in initial_xi + final_xi}
        minutes = {p: sum(int(r.get("minutes") or 0) for r in players[str(p)]
                          if int(r["gw"]) == gw) for p in initial_xi + final_xi}
        base = int(row["base_points"])
        assert base == sum(pts[p] for p in final_xi)
        for policy in policies:
            if gw == 1:
                captain, vice = int(row["captain"]), int(row["vice"])
            else:
                ranking = sorted(eligible, key=lambda p: (rank(p, players, gw, policy), -p),
                                 reverse=True)
                captain, vice = ranking[:2]
            scoring = captain if minutes[captain] > 0 else (
                vice if minutes[vice] > 0 and vice in final_xi else None)
            bonus = pts[scoring] if scoring is not None else 0
            output[policy].append({"gw": gw, "captain": captain, "vice": vice,
                                   "scoring_captain": scoring, "base": base,
                                   "captain_bonus": bonus, "points": base + bonus})
    summaries = []
    for policy in policies:
        rows = output[policy]
        summaries.append({"policy": policy, "total": sum(r["points"] for r in rows),
                          "captain_bonus": sum(r["captain_bonus"] for r in rows),
                          "gws": rows})
    baseline = next(s for s in summaries if s["policy"] == "form_3")
    if baseline["total"] != int(model["total"]):
        raise ValueError(f"Baseline policy mismatch: {baseline['total']} != {model['total']}")
    result = {
        "status": "retrospective_captain_policy_comparison_not_out_of_sample",
        "fixed_squad_xi_and_transfers": True,
        "baseline_total": model["total"],
        "policies": summaries,
        "warnings": [
            "Same historical GW1 squad, transfer path and starting XI for all policies.",
            "No opponent strength or upcoming fixture features: historical fixture snapshot unavailable.",
            "GW1 captain is the manager's observed selection, not a model forecast.",
            "Comparing policy totals on GW1-10 is in-sample; selecting the winner is hindsight overfitting.",
            "Underlying transfer budget uses unverified fixture-time price proxies."
        ]
    }
    (D / "backtest_captain_policy_experiment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": result["baseline_total"],
                      "policies": {x["policy"]: x["total"] for x in summaries}}))


if __name__ == "__main__":
    main()
