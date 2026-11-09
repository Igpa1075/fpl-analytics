"""Budget-constrained *proxy* backtest, NOT a verified deadline-price backtest.

Uses fixture-time player prices as imperfect proxies and the published GW1 bank.
A transfer is executed only if it is affordable under those assumptions.
All forecasts use only earlier GW points; price proxies may be post-deadline.
"""
import json
from collections import Counter
from fpl_backtest_hold_baseline import D, fetch, choose
from fpl_backtest_autosubs import resolve
from fpl_backtest_exploratory_transfers import form_score
from fpl_backtest_budget_proxy import price, selling_price


def affordable_transfer(squad, players, positions, teams, purchase, bank, gw):
    form = {pid: form_score(players[str(pid)], gw) for pid in positions}
    clubs = Counter(teams[p] for p in squad)
    candidates = []
    for outgoing in squad:
        old_price = price(players[str(outgoing)], gw)
        if old_price is None or outgoing not in purchase:
            continue
        proceeds = selling_price(purchase[outgoing], old_price)
        for incoming in positions:
            if incoming in squad or positions[incoming] != positions[outgoing]:
                continue
            if teams[incoming] != teams[outgoing] and clubs[teams[incoming]] >= 3:
                continue
            new_price = price(players[str(incoming)], gw)
            if new_price is None or proceeds + bank < new_price:
                continue
            gain = form[incoming] - form[outgoing]
            if gain > 0:
                candidates.append((gain, -incoming, -outgoing, outgoing, incoming, proceeds, new_price))
    if not candidates:
        return None
    gain, _, _, outgoing, incoming, proceeds, new_price = max(candidates)
    return {"out": outgoing, "in": incoming, "form_gain": gain,
            "proxy_sale_tenths": proceeds, "proxy_buy_tenths": new_price,
            "bank_before_tenths": bank, "bank_after_tenths": bank + proceeds - new_price}


def main():
    boot = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    players = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    elements = {int(p["id"]): p for p in boot["elements"]}
    positions = {p: int(e["element_type"]) for p, e in elements.items() if str(p) in players}
    teams = {p: int(elements[p]["team"]) for p in positions}
    entry = json.loads((D / "entry.json").read_text(encoding="utf-8"))
    entry_id = int(entry.get("id", 5150250))
    initial = fetch(f"/entry/{entry_id}/event/1/picks/")
    picks = initial["picks"]
    squad = [int(p["element"]) for p in picks]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid GW1 squad")
    raw_bank = initial.get("entry_history", {}).get("bank")
    if raw_bank is None:
        raise ValueError("GW1 bank unavailable; cannot simulate budget")
    bank = int(raw_bank)
    purchase = {p: price(players[str(p)], 1) for p in squad}
    if any(v is None for v in purchase.values()):
        raise ValueError("Missing initial fixture-price proxy")
    results = []
    for gw in range(1, 11):
        transfer = None
        if gw > 1:
            transfer = affordable_transfer(squad, players, positions, teams, purchase, bank, gw)
            if transfer:
                outgoing, incoming = transfer["out"], transfer["in"]
                squad.remove(outgoing)
                squad.append(incoming)
                purchase.pop(outgoing)
                purchase[incoming] = transfer["proxy_buy_tenths"]
                bank = transfer["bank_after_tenths"]
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
                        "bank_after_tenths": bank, "captain": captain, "vice": vice,
                        "autosubs": scored["autosubs"]})
    report = {
        "status": "budget_constrained_fixture_price_proxy_not_verified",
        "total": sum(r["points"] for r in results),
        "transfers": sum(bool(r["transfer"]) for r in results),
        "initial_bank_tenths": int(raw_bank),
        "gws": results,
        "caveats": [
            "Fixture prices may differ from prices at transfer deadlines.",
            "GW1 fixture prices are proxies for original purchase prices.",
            "Current team assignments may differ from historical team assignments.",
            "The observed GW1 squad and XI are not selected by the model.",
            "One optional free transfer per GW; no chips, hits, injuries or fixture projections.",
            "All form forecasts use only prior GW results, but fixture-price proxy is not deadline-safe."
        ]
    }
    (D / "backtest_budget_constrained_proxy.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total": report["total"], "transfers": report["transfers"]}))


if __name__ == "__main__":
    main()
