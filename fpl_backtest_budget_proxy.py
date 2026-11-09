"""Diagnostic budget stress test using fixture prices, never claiming legal transfers.

Uses GW1 observed bank from published picks and fixture-time prices as proxies.
Selling price approximates FPL half-profit rule. This is NOT a deadline backtest.
"""
import json
from pathlib import Path
from fpl_backtest_hold_baseline import D, fetch


def price(rows, gw):
    values = [int(r["value_at_fixture"]) for r in rows
              if int(r["gw"]) == gw and r.get("value_at_fixture") is not None]
    return values[0] if values else None


def selling_price(purchase, current):
    if current <= purchase:
        return current
    return purchase + (current - purchase) // 2


def main():
    history = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    simulated = json.loads((D / "backtest_exploratory_transfers.json").read_text(encoding="utf-8"))
    entry = json.loads((D / "entry.json").read_text(encoding="utf-8"))
    entry_id = int(entry.get("id", 5150250))
    picks_data = fetch(f"/entry/{entry_id}/event/1/picks/")
    initial = picks_data["picks"]
    observed_bank = picks_data.get("entry_history", {}).get("bank")
    bank = int(observed_bank) if observed_bank is not None else None
    purchase = {}
    missing = []
    for p in initial:
        pid = str(p["element"])
        v = price(history[pid], 1)
        if v is None:
            missing.append(int(pid))
        else:
            purchase[pid] = v
    rows = []
    for event in simulated["gws"]:
        t = event.get("transfer")
        if not t:
            continue
        gw = int(event["gw"])
        outgoing, incoming = str(t["out"]), str(t["in"])
        out_price = price(history[outgoing], gw)
        in_price = price(history[incoming], gw)
        bought_at = purchase.get(outgoing)
        sale = selling_price(bought_at, out_price) if bought_at is not None and out_price is not None else None
        bank_before = bank
        affordable_proxy = None
        if bank is not None and sale is not None and in_price is not None:
            affordable_proxy = bank + sale >= in_price
            if affordable_proxy:
                bank = bank + sale - in_price
                purchase.pop(outgoing, None)
                purchase[incoming] = in_price
            else:
                # Keep the simulated team path separate from budget validity.
                # Subsequent transfers cannot be budget-evaluated after an impossible trade.
                bank = None
        rows.append({"gw": gw, "out": int(outgoing), "in": int(incoming),
                     "fixture_price_out": out_price, "fixture_price_in": in_price,
                     "estimated_sale": sale, "estimated_bank_before": bank_before,
                     "affordable_under_fixture_proxy": affordable_proxy})
    report = {
        "status": "diagnostic_fixture_price_proxy_not_historical_deadline",
        "observed_gw1_bank_tenths": observed_bank,
        "missing_gw1_fixture_prices": missing,
        "first_proxy_unaffordable_gw": next(
            (r["gw"] for r in rows if r["affordable_under_fixture_proxy"] is False), None),
        "rows": rows,
        "warnings": [
            "GW1 fixture prices are not necessarily initial purchase prices.",
            "GW1 published bank may not reflect the exact initial pre-deadline bank.",
            "Fixture-time prices are not deadline prices.",
            "Once an unaffordable proxy transfer occurs, downstream budget estimates are unknown.",
            "This cannot certify any transfer as legal; it is only a diagnostic stress test."
        ]
    }
    (D / "backtest_budget_proxy_diagnostic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"first_proxy_unaffordable_gw": report["first_proxy_unaffordable_gw"],
                      "initial_bank_tenths": observed_bank}))


if __name__ == "__main__":
    main()
