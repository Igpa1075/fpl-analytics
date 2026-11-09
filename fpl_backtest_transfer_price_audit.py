"""Audit transfer-model price evidence without treating fixture prices as deadline prices."""
import json
from pathlib import Path

D = Path(__file__).resolve().parent / "data"


def fixture_value(rows, gw):
    values = [int(r["value_at_fixture"]) for r in rows
              if int(r["gw"]) == gw and r.get("value_at_fixture") is not None]
    return values[0] if values else None


def main():
    history = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    simulated = json.loads((D / "backtest_exploratory_transfers.json").read_text(encoding="utf-8"))
    rows = []
    for event in simulated["gws"]:
        transfer = event.get("transfer")
        if not transfer:
            continue
        gw = int(event["gw"])
        outgoing, incoming = str(transfer["out"]), str(transfer["in"])
        # Values from match records are NOT guaranteed to match transfer deadline prices.
        sale_proxy = fixture_value(history[outgoing], gw)
        buy_proxy = fixture_value(history[incoming], gw)
        rows.append({
            "gw": gw, "out": int(outgoing), "in": int(incoming),
            "fixture_value_out_tenths": sale_proxy,
            "fixture_value_in_tenths": buy_proxy,
            "fixture_price_difference_tenths": (
                buy_proxy - sale_proxy if sale_proxy is not None and buy_proxy is not None else None),
            "has_both_fixture_values": sale_proxy is not None and buy_proxy is not None,
            "deadline_price_verified": False,
            "transfer_budget_legal": None,
        })
    report = {
        "status": "not_budget_validated",
        "transfer_count": len(rows),
        "with_fixture_price_pair": sum(x["has_both_fixture_values"] for x in rows),
        "with_verified_deadline_price_pair": 0,
        "budget_legal_transfers_confirmed": 0,
        "rows": rows,
        "required_to_validate": [
            "Pre-deadline buy prices for incoming players in each GW",
            "Actual purchase prices and FPL half-profit selling prices for outgoing players",
            "Remaining bank balance before every transfer",
            "Historical club and player eligibility as of each deadline"
        ],
        "warning": "Fixture values are diagnostic only. Never use them to assert affordability."
    }
    (D / "backtest_transfer_price_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"transfers": len(rows), "fixture_pairs": report["with_fixture_price_pair"],
                      "verified_deadline_pairs": 0}))


if __name__ == "__main__":
    main()
