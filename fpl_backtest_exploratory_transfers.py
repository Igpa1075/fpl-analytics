"""Exploratory hindsight-free transfer simulation. NOT price-feasible FPL backtest.

Starts from observed GW1 squad. One optional transfer before each GW2-10,
based exclusively on completed prior GWs. Uses current bootstrap club IDs
as a provisional proxy; historical team memberships may differ.
No transfer is represented as budget-legal until deadline prices are archived.
"""
import json
from collections import Counter
from pathlib import Path
from fpl_backtest_hold_baseline import D, fetch, choose
from fpl_backtest_autosubs import resolve


def form_score(rows, gw):
    return sum(int(r.get("total_points") or 0)
               for r in rows if gw - 3 <= int(r["gw"]) < gw)


def best_transfer(squad, players, positions, teams, gw):
    """Single free transfer, same position, max three players per club."""
    scores = {p: form_score(players[str(p)], gw) for p in positions}
    clubs = Counter(teams[p] for p in squad)
    choices = []
    for outgoing in squad:
        for incoming in positions:
            if incoming in squad or positions[incoming] != positions[outgoing]:
                continue
            if teams[incoming] != teams[outgoing] and clubs[teams[incoming]] >= 3:
                continue
            gain = scores[incoming] - scores[outgoing]
            if gain > 0:
                choices.append((gain, -incoming, -outgoing, outgoing, incoming))
    if not choices:
        return None
    gain, _, _, outgoing, incoming = max(choices)
    return {"out": outgoing, "in": incoming, "form_gain": gain}


def main():
    bootstrap = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    state = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))
    players = state["players"]
    elements = {int(p["id"]): p for p in bootstrap["elements"]}
    positions = {p: int(e["element_type"]) for p, e in elements.items() if str(p) in players}
    teams = {p: int(elements[p]["team"]) for p in positions}
    entry = json.loads((D / "entry.json").read_text(encoding="utf-8"))
    entry_id = int(entry.get("id", 5150250))
    picks = fetch(f"/entry/{entry_id}/event/1/picks/")["picks"]
    squad = [int(p["element"]) for p in picks]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid observed GW1 squad")
    results = []
    for gw in range(1, 11):
        transfer = None
        if gw > 1:
            transfer = best_transfer(squad, players, positions, teams, gw)
            if transfer:
                squad.remove(transfer["out"])
                squad.append(transfer["in"])
        prior = {p: form_score(players[str(p)], gw) for p in squad}
        actual = {p: sum(int(r.get("total_points") or 0) for r in players[str(p)]
                         if int(r["gw"]) == gw) for p in squad}
        minutes = {p: sum(int(r.get("minutes") or 0) for r in players[str(p)]
                          if int(r["gw"]) == gw) for p in squad}
        if gw == 1:
            starters = [int(p["element"]) for p in picks if int(p["position"]) <= 11]
            captain = next(int(p["element"]) for p in picks if p["is_captain"])
            vice = next(int(p["element"]) for p in picks if p["is_vice_captain"])
            rest = [int(p["element"]) for p in sorted(picks, key=lambda p: p["position"])
                    if int(p["position"]) > 11]
            bench = [p for p in rest if positions[p] == 1] + [p for p in rest if positions[p] != 1]
        else:
            starters = choose(squad, positions, prior)
            eligible = sorted((p for p in starters if positions[p] != 1),
                              key=lambda p: (-prior[p], p))
            captain, vice = eligible[:2]
            rest = [p for p in squad if p not in starters]
            bench = sorted((p for p in rest if positions[p] == 1)) + sorted(
                (p for p in rest if positions[p] != 1), key=lambda p: (-prior[p], p))
        scored = resolve(starters + bench, positions, minutes, actual, captain, vice)
        results.append({"gw": gw, "points": scored["points"], "transfer": transfer,
                        "captain": captain, "vice": vice, "autosubs": scored["autosubs"]})
    report = {
        "status": "exploratory_not_budget_validated",
        "total": sum(r["points"] for r in results),
        "gws": results,
        "caveats": [
            "No historical deadline prices or selling prices; transfers may be unaffordable.",
            "Current bootstrap club membership is a proxy, not verified historic membership.",
            "GW1 squad and XI are observed real manager choices.",
            "Only one optional free transfer per GW; no chips or hits.",
            "Transfer rankings use strictly completed prior gameweeks.",
            "No contemporaneous injury, fixture, or availability data."
        ]
    }
    (D / "backtest_exploratory_transfers.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total": report["total"], "transfers": sum(bool(x["transfer"]) for x in results)}))


if __name__ == "__main__":
    main()
