"""Audit leading GW11 transfer using fresh FPL player data and public transfer history.

Public API does not reveal the authenticated my-team selling price or free
transfer balance. This script NEVER marks a transfer confirmed executable.
"""
import json
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D, fetch

IDS = (304, 31)
ENTRY_ID = 5150250


def main():
    bootstrap = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    players = {int(p["id"]): p for p in bootstrap["elements"]}
    teams = {int(t["id"]): t["name"] for t in bootstrap["teams"]}
    picks = json.loads((D / "picks.json").read_text(encoding="utf-8"))
    gw = int(picks["entry_history"]["event"])
    bank = int(picks["entry_history"]["bank"])
    if gw != 10:
        print("Published GW10 reference squad unavailable; no new audit")
        return
    details = {}
    for pid in IDS:
        p = players[pid]
        details[str(pid)] = {
            "id": pid, "name": p["web_name"],
            "full_name": f'{p["first_name"]} {p["second_name"]}',
            "club": teams[int(p["team"])],
            "position_id": int(p["element_type"]),
            "market_price_tenths": int(p["now_cost"]),
            "status": p.get("status"),
            "news": p.get("news"),
            "chance_next_round": p.get("chance_of_playing_next_round"),
            "minutes_season": p.get("minutes"),
            "points_per_game": p.get("points_per_game"),
            "expected_goals": p.get("expected_goals"),
            "expected_assists": p.get("expected_assists"),
        }
    outgoing = details["304"]
    incoming = details["31"]
    if outgoing["position_id"] != incoming["position_id"]:
        raise ValueError("Incompatible transfer positions")
    squad = [int(p["element"]) for p in picks["picks"]]
    if 304 not in squad or 31 in squad:
        raise ValueError("Transfer not applicable to published squad")
    from collections import Counter
    counts = Counter(int(players[pid]["team"]) for pid in squad)
    club = int(players[31]["team"])
    club_limit_ok = counts[club] < 3 or int(players[304]["team"]) == club
    # Only known sufficient condition: bank alone covers buy price.
    # If not, exact sale price is required.
    buy = incoming["market_price_tenths"]
    minimum_sale_needed = max(0, buy-bank)
    market_sale_proxy = outgoing["market_price_tenths"]
    report = {
        "status": "public_data_audit_not_authenticated_trade_verification",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_published_squad_gw": gw,
        "bank_tenths": bank,
        "players": details,
        "club_limit_ok": club_limit_ok,
        "minimum_actual_sale_price_tenths_required": minimum_sale_needed,
        "current_market_sale_proxy_tenths": market_sale_proxy,
        "affordable_if_market_sale_proxy_used": bank + market_sale_proxy >= buy,
        "actual_sale_price_verified": False,
        "free_transfers_verified": False,
        "executable_verified": False,
        "notes": [
            "Player names, status and news are from fresh bootstrap data.",
            "Selling price is individual to the manager and not present in public picks.",
            "Check authenticated FPL My Team for exact selling price and free transfers.",
            "Current market price is not a substitute for actual selling price.",
            "No transfer should be recommended as executable until verified."
        ]
    }
    (D/"gw11_transfer_304_31_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"players": {k:v["name"] for k,v in details.items()},
                      "minimum_sale_tenths": minimum_sale_needed,
                      "club_limit_ok": club_limit_ok}))


if __name__ == "__main__":
    main()
