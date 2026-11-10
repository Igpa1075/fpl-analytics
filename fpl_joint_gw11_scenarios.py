"""Joint transfer/XI/captain search for GW11; exploratory price-proxy scenarios.

Current public squad has no authenticated purchase/selling prices. Therefore
the reported affordability is a proxy, NEVER a verified legal FPL transfer.
All form inputs are from GW1-10, strictly prior to GW11.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D, choose
from fpl_backtest_captain_policy_experiment import rank

TARGET_GW = 11
HORIZON = 3


def projected(pid, players, gw):
    rows = [r for r in players[str(pid)] if gw-3 <= int(r["gw"]) < gw]
    # Transparent proxy: recent 3-GW total divided by 3. Not calibrated xP.
    return sum(int(r.get("total_points") or 0) for r in rows) / 3


def optimize(squad, positions, players, gw):
    form = {p: projected(p, players, gw) for p in squad}
    xi = choose(squad, positions, form)
    eligible = sorted((p for p in xi if positions[p] != 1),
                      key=lambda p: (-rank(p, players, gw, "season_form")[0], p))
    captain, vice = eligible[:2]
    # One GW expected-score proxy; captain bonus uses chosen captain's
    # recent average, with no future fixture adjustment.
    estimate = sum(form[p] for p in xi) + form[captain]
    return {"xi": xi, "captain": captain, "vice": vice,
            "one_gw_proxy": round(estimate, 3),
            "three_gw_static_proxy": round(estimate * HORIZON, 3)}


def main():
    now = datetime.now(timezone.utc)
    boot = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    picks = json.loads((D / "picks.json").read_text(encoding="utf-8"))
    players = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    event = next(e for e in boot["events"] if int(e["id"]) == TARGET_GW)
    deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
    if now >= deadline:
        print("GW11 deadline passed: refusing to create new predeadline scenario")
        return
    if int(picks["entry_history"]["event"]) != 10:
        print("GW10 published squad unavailable: no scenario generated")
        return
    out = D / "joint_gw11_scenario.json"
    if out.exists():
        print("GW11 scenario already frozen; not overwriting")
        return
    elements = {int(e["id"]): e for e in boot["elements"]}
    squad = [int(p["element"]) for p in picks["picks"]]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid published squad")
    positions = {p: int(e["element_type"]) for p, e in elements.items() if str(p) in players}
    teams = {p: int(elements[p]["team"]) for p in positions}
    if any(p not in positions for p in squad):
        raise ValueError("Missing player history or position")
    if [sum(positions[p] == t for p in squad) for t in range(1, 5)] != [2, 5, 5, 3]:
        raise ValueError("Invalid squad distribution")
    bank = int(picks["entry_history"]["bank"])
    baseline = optimize(squad, positions, players, TARGET_GW)
    candidates = []
    counts = Counter(teams[p] for p in squad)
    for outgoing in squad:
        sale_proxy = int(elements[outgoing]["now_cost"])
        for incoming in positions:
            if incoming in squad or positions[incoming] != positions[outgoing]:
                continue
            if teams[incoming] != teams[outgoing] and counts[teams[incoming]] >= 3:
                continue
            buy = int(elements[incoming]["now_cost"])
            if buy > bank + sale_proxy:
                continue
            trial = [incoming if p == outgoing else p for p in squad]
            scored = optimize(trial, positions, players, TARGET_GW)
            delta = round(scored["three_gw_static_proxy"] -
                          baseline["three_gw_static_proxy"], 3)
            if delta <= 0:
                continue
            candidates.append({
                "out": outgoing, "in": incoming, "proxy_sale_tenths": sale_proxy,
                "current_buy_tenths": buy,
                "bank_after_proxy_tenths": bank + sale_proxy - buy,
                "delta_three_gw_static_proxy": delta, "lineup": scored
            })
    candidates.sort(key=lambda x: (-x["delta_three_gw_static_proxy"], x["in"], x["out"]))
    report = {
        "status": "frozen_exploratory_joint_scenarios_not_trade_verified",
        "created_at_utc": now.isoformat(), "deadline_utc": deadline.isoformat(),
        "gw": TARGET_GW, "source_squad_gw": 10, "bank_tenths": bank,
        "no_transfer": baseline, "top_transfer_scenarios": candidates[:10],
        "candidate_count": len(candidates),
        "limitations": [
            "Public GW10 picks do not expose purchase or selling prices.",
            "Uses current market price as outgoing selling-price proxy; can overstate actual sale proceeds.",
            "No transfer is certified affordable or executable; verify actual selling price in FPL.",
            "Uses current player team assignments, not verified pre-deadline historical assignments.",
            "3-GW horizon repeats the same 3-GW form proxy; not fixture-adjusted expected points.",
            "One hypothetical transfer only; no free-transfer balance, chip, injury or minutes model.",
            "GW11 existing captain-policy snapshot is not changed."
        ]
    }
    with out.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"scenarios": len(candidates), "baseline": baseline["one_gw_proxy"],
                      "top_delta": candidates[0]["delta_three_gw_static_proxy"] if candidates else None}))


if __name__ == "__main__":
    main()
