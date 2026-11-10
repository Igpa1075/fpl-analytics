"""Fixture-aware GW11-13 joint transfer, XI and captain exploratory scenarios.

Uses historical GW1-10 player form/minutes and GW11-13 fixture schedule.
Opponent strength is inferred ONLY from finished GW1-10 fixture goals.
Prices use public market value as a sale proxy; NOT verified affordability.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D, choose
from fpl_backtest_captain_policy_experiment import rank

GWS = (11, 12, 13)


def defensive_factors(fixtures):
    conceded = defaultdict(list)
    for f in fixtures:
        if not f.get("finished") or not isinstance(f.get("event"), int) or f["event"] > 10:
            continue
        if f.get("team_h_score") is None or f.get("team_a_score") is None:
            continue
        conceded[int(f["team_h"])].append(int(f["team_a_score"]))
        conceded[int(f["team_a"])].append(int(f["team_h_score"]))
    averages = {t: sum(v)/len(v) for t, v in conceded.items() if v}
    league = sum(sum(v) for v in conceded.values()) / max(1, sum(map(len, conceded.values())))
    # Shrink towards league mean to avoid extreme short-sample multipliers.
    return {t: max(.75, min(1.25, (.5*avg + .5*league)/max(.5, league)))
            for t, avg in averages.items()}


def player_forecast(pid, players, gw, opponent_factor, home):
    rows = [r for r in players[str(pid)] if int(r["gw"]) <= 10]
    recent = [r for r in rows if 8 <= int(r["gw"]) <= 10]
    points = sum(int(r.get("total_points") or 0) for r in recent)
    minutes = sum(int(r.get("minutes") or 0) for r in recent)
    # Both historical points and minutes are from completed GW1-10 only.
    availability = min(1.0, minutes / 210) if recent else 0
    base = points / 3
    return round(base * (.5 + .5*availability) * opponent_factor *
                 (1.04 if home else .96), 4)


def optimize(squad, positions, players, fixtures_by_gw, teams, factors):
    per_gw = []
    total = 0
    for gw in GWS:
        expected = {}
        for pid in squad:
            club = teams[pid]
            matches = fixtures_by_gw.get(gw, {}).get(club, [])
            expected[pid] = sum(player_forecast(pid, players, gw, factors.get(opponent, 1.0), home)
                                for opponent, home in matches)
        xi = choose(squad, positions, expected)
        captains = sorted((p for p in xi if positions[p] != 1),
                          key=lambda p: (-expected[p], p))
        captain, vice = captains[:2]
        points = round(sum(expected[p] for p in xi) + expected[captain], 3)
        total += points
        per_gw.append({"gw": gw, "starting_xi": xi, "captain": captain,
                       "vice_captain": vice, "proxy_points": points})
    return {"three_gw_proxy": round(total, 3), "gws": per_gw}


def main():
    now = datetime.now(timezone.utc)
    boot = json.loads((D/"bootstrap.json").read_text(encoding="utf-8"))
    picks = json.loads((D/"picks.json").read_text(encoding="utf-8"))
    fixtures = json.loads((D/"fixtures.json").read_text(encoding="utf-8"))
    players = json.loads((D/"historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    event = next(e for e in boot["events"] if int(e["id"]) == 11)
    deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
    if now >= deadline or int(picks["entry_history"]["event"]) != 10:
        print("Not eligible for predeadline GW11 fixture-aware scenario")
        return
    out = D/"joint_gw11_fixture_aware.json"
    if out.exists():
        print("Fixture-aware GW11 scenario already frozen")
        return
    elements = {int(e["id"]): e for e in boot["elements"]}
    squad = [int(x["element"]) for x in picks["picks"]]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid squad")
    positions = {p: int(e["element_type"]) for p,e in elements.items() if str(p) in players}
    teams = {p: int(elements[p]["team"]) for p in positions}
    if any(p not in positions for p in squad):
        raise ValueError("Missing squad players")
    by_gw = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        gw = f.get("event")
        if gw not in GWS:
            continue
        home, away = int(f["team_h"]), int(f["team_a"])
        by_gw[gw][home].append((away, True))
        by_gw[gw][away].append((home, False))
    if any(len(by_gw[gw]) < 20 for gw in GWS):
        raise ValueError("Incomplete fixture schedule for GW11-13")
    factors = defensive_factors(fixtures)
    bank = int(picks["entry_history"]["bank"])
    baseline = optimize(squad, positions, players, by_gw, teams, factors)
    counts = Counter(teams[p] for p in squad)
    candidates = []
    for outgoing in squad:
        sale = int(elements[outgoing]["now_cost"])
        for incoming in positions:
            if incoming in squad or positions[incoming] != positions[outgoing]:
                continue
            if teams[incoming] != teams[outgoing] and counts[teams[incoming]] >= 3:
                continue
            buy = int(elements[incoming]["now_cost"])
            if buy > sale + bank:
                continue
            trial = [incoming if p == outgoing else p for p in squad]
            result = optimize(trial, positions, players, by_gw, teams, factors)
            gain = round(result["three_gw_proxy"]-baseline["three_gw_proxy"], 3)
            if gain > 0:
                candidates.append({"out": outgoing, "in": incoming,
                                   "sale_price_proxy_tenths": sale,
                                   "buy_price_tenths": buy,
                                   "bank_after_proxy_tenths": bank+sale-buy,
                                   "gain_three_gw_proxy": gain, "lineup": result})
    candidates.sort(key=lambda x: (-x["gain_three_gw_proxy"], x["in"], x["out"]))
    report = {
        "status": "frozen_fixture_aware_exploratory_not_legal_transfer_verified",
        "created_at_utc": now.isoformat(), "deadline_utc": deadline.isoformat(),
        "source_squad_gw": 10, "gws": list(GWS),
        "baseline": baseline, "candidate_count": len(candidates),
        "top_transfer_scenarios": candidates[:10],
        "method": "GW8-10 points and minutes; GW11-13 fixture schedule; opponent goals conceded in finished GW1-10; mild home adjustment",
        "limitations": [
            "Current selling-price proxy may overstate real sale proceeds; do not execute without FPL confirmation.",
            "Expected points are heuristic and not calibrated to FPL points.",
            "Minutes factor uses historical minutes only, not news, injuries or projected lineups.",
            "Opponent factor uses historical goals conceded, not expected goals or team news.",
            "Current team memberships and fixtures are current API snapshots, not deadline-archived.",
            "Free transfer balance, chips, hits, and future price changes are not modeled.",
            "Each GW lineup and captain are jointly reoptimized after a hypothetical transfer.",
            "GW11 captain-policy forward snapshot remains unchanged."
        ]
    }
    with out.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"baseline": baseline["three_gw_proxy"],
                      "candidates": len(candidates),
                      "best_gain": candidates[0]["gain_three_gw_proxy"] if candidates else None}))


if __name__ == "__main__":
    main()
