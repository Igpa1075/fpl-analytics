"""Attribute score differences between model and manager to captain bonus and XI base.

This is a descriptive decomposition, not proof of which earlier transfer caused
a difference. Uses official published picks and per-player historical GW points.
"""
import json
from fpl_backtest_hold_baseline import D, fetch
from fpl_backtest_autosubs import resolve


def main():
    model = json.loads((D / "backtest_budget_constrained_proxy.json").read_text(encoding="utf-8"))
    players = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    boot = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    positions = {int(p["id"]): int(p["element_type"]) for p in boot["elements"]}
    entry = json.loads((D / "entry.json").read_text(encoding="utf-8"))
    entry_id = int(entry.get("id", 5150250))
    rows = []
    for m in model["gws"]:
        gw = int(m["gw"])
        published = fetch(f"/entry/{entry_id}/event/{gw}/picks/")
        picks = published["picks"]
        actual_points = {int(pid): sum(int(r.get("total_points") or 0)
                          for r in matches if int(r["gw"]) == gw)
                         for pid, matches in players.items()}
        actual_minutes = {int(pid): sum(int(r.get("minutes") or 0)
                           for r in matches if int(r["gw"]) == gw)
                          for pid, matches in players.items()}
        manager_gross = int(published["entry_history"]["points"])
        hit = int(published["entry_history"].get("event_transfers_cost", 0))
        chip = published.get("active_chip")
        manager_captain = next(int(p["element"]) for p in picks if p["is_captain"])
        manager_vice = next(int(p["element"]) for p in picks if p["is_vice_captain"])
        # Published pick multipliers are final after official substitutions.
        official_base = sum(actual_points[int(p["element"])]
                            for p in picks if int(p["multiplier"]) > 0)
        official_captain_bonus = sum(
            (int(p["multiplier"]) - 1) * actual_points[int(p["element"])]
            for p in picks if int(p["multiplier"]) > 1)
        # For standard captaincy, multiplier 2; other chips are not comparable.
        if chip in ("bench_boost", "3xc"):
            raise ValueError(f"GW{gw}: special chip needs separate scoring attribution")
        if official_base + official_captain_bonus != manager_gross:
            raise ValueError(f"GW{gw}: official published picks scoring mismatch: "
                             f"{official_base}+{official_captain_bonus}!={manager_gross}")
        # Model's scored points include one captain bonus and any autosubs.
        # Recover base from model final XI by replaying its transfer path.
        # Rather than infer a hidden XI, reconstruct squad and lineup deterministically
        # from the exact same policy.
        rows.append({
            "gw": gw, "manager_gross": manager_gross, "manager_hit": hit,
            "manager_net": manager_gross - hit,
            "manager_base": official_base,
            "manager_captain_bonus": official_captain_bonus,
            "manager_captain_id": manager_captain,
            "manager_vice_id": manager_vice,
            "manager_chip": chip,
            "model_total": int(m["points"]),
            "model_base": int(m["base_points"]),
            "model_captain_bonus": int(m["captain_bonus"]),
            "model_minus_manager_base": int(m["base_points"]) - official_base,
            "model_minus_manager_captain_bonus": int(m["captain_bonus"]) - official_captain_bonus,
            "model_captain_id": int(m["captain"]),
            "model_transfer": m.get("transfer"),
            "model_minus_manager_net": int(m["points"]) - (manager_gross - hit)
        })
    report = {
        "status": "base_captain_and_hit_decomposition",
        "rows": rows,
        "manager_base_total": sum(r["manager_base"] for r in rows),
        "manager_captain_bonus_total": sum(r["manager_captain_bonus"] for r in rows),
        "manager_net_total": sum(r["manager_net"] for r in rows),
        "model_total": sum(r["model_total"] for r in rows),
        "model_base_total": sum(r["model_base"] for r in rows),
        "model_captain_bonus_total": sum(r["model_captain_bonus"] for r in rows),
        "model_minus_manager_base": sum(r["model_minus_manager_base"] for r in rows),
        "model_minus_manager_captain_bonus": sum(r["model_minus_manager_captain_bonus"] for r in rows),
        "warnings": [
            "Comparisons include the effects of different squads, XI and transfers.",
            "GW8 wildcard is not replicated by model."
        ]
    }
    (D / "backtest_captain_xi_diagnostic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manager_base_total": report["manager_base_total"],
                      "manager_captain_bonus_total": report["manager_captain_bonus_total"],
                      "model_total": report["model_total"]}))


if __name__ == "__main__":
    main()
