"""Audit robustness of proxy transfer affordability to unknown deadline prices.

For each selected transfer, calculate how much more expensive the incoming
player or how much lower the outgoing sale price could be before it fails.
This is NOT a reconstruction of actual deadline prices.
"""
import json
from fpl_backtest_hold_baseline import D


def main():
    report = json.loads((D / "backtest_budget_constrained_proxy.json").read_text(encoding="utf-8"))
    rows = []
    for gw_data in report["gws"]:
        transfer = gw_data.get("transfer")
        if not transfer:
            continue
        bank = int(transfer["bank_before_tenths"])
        sale = int(transfer["proxy_sale_tenths"])
        buy = int(transfer["proxy_buy_tenths"])
        margin = bank + sale - buy
        rows.append({
            "gw": int(gw_data["gw"]),
            "out": int(transfer["out"]),
            "in": int(transfer["in"]),
            "proxy_bank_before_tenths": bank,
            "proxy_sale_tenths": sale,
            "proxy_buy_tenths": buy,
            "affordability_margin_tenths": margin,
            "fails_if_buy_price_increases_by_tenths": margin + 1,
            "fails_if_sale_price_decreases_by_tenths": margin + 1,
            "survives_combined_one_tenth_adverse_move": margin >= 2,
            "survives_combined_two_tenths_adverse_move": margin >= 4,
            "verified_deadline_prices": False
        })
    result = {
        "status": "proxy_affordability_sensitivity_not_deadline_validation",
        "baseline_proxy_points": report["total"],
        "transfers": len(rows),
        "minimum_margin_tenths": min((r["affordability_margin_tenths"] for r in rows), default=None),
        "fragile_combined_one_tenth": [r["gw"] for r in rows if not r["survives_combined_one_tenth_adverse_move"]],
        "fragile_combined_two_tenths": [r["gw"] for r in rows if not r["survives_combined_two_tenths_adverse_move"]],
        "rows": rows,
        "warnings": [
            "This is a local sensitivity audit of the existing transfer path, not a re-optimized simulation.",
            "The simulated bank depends on unverified earlier purchases and sales.",
            "Actual deadline prices cannot be inferred solely from match-week fixture prices.",
            "Margins do not certify any transfer as historically legal."
        ]
    }
    (D / "backtest_deadline_price_sensitivity.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"transfers": len(rows),
                      "minimum_margin_tenths": result["minimum_margin_tenths"],
                      "fragile_combined_one_tenth": result["fragile_combined_one_tenth"]}))


if __name__ == "__main__":
    main()
