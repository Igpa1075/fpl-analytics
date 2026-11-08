"""Advisory 0/1/2-transfer FPL scenarios from frozen player projections.

IMPORTANT: latest publicly published GW squad, bank and public current prices are proxies.
Actual sale prices, free transfers, chips and current squad are unavailable.
No transfer is executed; rankings are NOT actionable until verified.
"""
import itertools
import json
from collections import Counter
from pathlib import Path
from fpl_verified_inputs import load_verified_inputs, transfer_hit

DATA = Path("data")
OUT = DATA / "transfer_scenarios.json"
FORECASTS = DATA / "forecasts"


def lineup_score(players):
    best = None
    for xi in itertools.combinations(players, 11):
        n = Counter(p["position_id"] for p in xi)
        if n[1] != 1 or not 3 <= n[2] <= 5 or not 2 <= n[3] <= 5 or not 1 <= n[4] <= 3:
            continue
        cap = max(xi, key=lambda p: (p["expected_points"], -p["player_id"]))
        value = sum(p["expected_points"] for p in xi) + cap["expected_points"]
        if best is None or value > best[0]:
            best = (value, cap["player_id"])
    return best


def main():
    if not FORECASTS.exists():
        print("No forecasts; skipping scenarios.")
        return
    files = sorted(FORECASTS.glob("*.json"))
    if not files or not (DATA / "picks.json").exists():
        print("No forecast or personal squad; skipping.")
        return
    # Latest capture, not filename, determines newest frozen prediction.
    docs = [(json.loads(p.read_text(encoding="utf-8")), p) for p in files]
    forecast, source = max(docs, key=lambda item: item[0]["captured_at_utc"])
    picks = json.loads((DATA / "picks.json").read_text(encoding="utf-8"))
    original_ids = [p["element"] for p in picks["picks"]]
    if len(original_ids) != 15 or len(set(original_ids)) != 15:
        raise ValueError("Expected exactly 15 distinct owned players")
    player_map = {p["player_id"]: p for p in forecast["predictions"]}
    if any(i not in player_map for i in original_ids):
        raise ValueError("Missing forecast for an owned player")
    original = [player_map[i] for i in original_ids]
    original_clubs = Counter(p["team_id"] for p in original)
    if any(count > 3 for count in original_clubs.values()):
        raise ValueError("Owned squad violates max-three-per-club")
    verified = load_verified_inputs(int(forecast["target_gw"]), original_ids)
    bank = verified["bank"] if verified else int(picks.get("entry_history", {}).get("bank") or 0)
    selling_price = (lambda p: verified["selling_prices"][p["player_id"]]
                     if verified else int(p["price_tenths_million"]))
    baseline = lineup_score(original)
    if baseline is None:
        raise ValueError("No legal starting XI in original squad")

    # Keep candidate search bounded; use top projected players in each position.
    shortlist = {}
    for position in (1, 2, 3, 4):
        eligible = [p for p in player_map.values() if p["position_id"] == position
                    and p["player_id"] not in original_ids]
        shortlist[position] = sorted(eligible,
                                   key=lambda p: (-p["expected_points"], p["player_id"]))[:20]
    options = [{"transfers": [], "projected_xi_with_captain": round(baseline[0], 3),
                "gross_gain_vs_hold": 0.0, "remaining_bank_proxy": bank}]
    # Two-player moves are allowed across positions, but each replacement
    # must match the outgoing player's position.
    choices = []
    for old in original:
        for new in shortlist[old["position_id"]]:
            if original_clubs[new["team_id"]] >= 3 and new["team_id"] != old["team_id"]:
                continue
            # Selling at current price is an optimistic approximation.
            remaining = bank + selling_price(old) - int(new["price_tenths_million"])
            if remaining < 0:
                continue
            choices.append((old, new))
    for old, new in choices:
        team = [p for p in original if p["player_id"] != old["player_id"]] + [new]
        score = lineup_score(team)
        if score:
            options.append({
                "transfers": [{"out": old["player_id"], "out_name": old["name"],
                               "in": new["player_id"], "in_name": new["name"]}],
                "projected_xi_with_captain": round(score[0], 3),
                "gross_gain_vs_hold": round(score[0] - baseline[0], 3),
                "remaining_bank_proxy": bank + int(old["price_tenths_million"]) -
                                        int(new["price_tenths_million"]),
            })
    # Limit double-transfer search to 10 strongest single replacements per
    # outgoing player; still check combined affordability and club cap.
    grouped = {}
    for old, new in choices:
        grouped.setdefault(old["player_id"], []).append((old, new))
    narrowed = [x for group in grouped.values()
                for x in sorted(group, key=lambda x: -(
                    x[1]["expected_points"] - x[0]["expected_points"]))[:10]]
    for (old1, new1), (old2, new2) in itertools.combinations(narrowed, 2):
        if old1["player_id"] == old2["player_id"] or new1["player_id"] == new2["player_id"]:
            continue
        ids = set(original_ids) - {old1["player_id"], old2["player_id"]}
        team = [player_map[i] for i in ids] + [new1, new2]
        if max(Counter(p["team_id"] for p in team).values()) > 3:
            continue
        remaining = bank + sum(selling_price(p) for p in (old1, old2)) - sum(
            int(p["price_tenths_million"]) for p in (new1, new2))
        if remaining < 0:
            continue
        score = lineup_score(team)
        if score:
            options.append({
                "transfers": [{"out": a["player_id"], "out_name": a["name"],
                               "in": b["player_id"], "in_name": b["name"]}
                              for a, b in ((old1, new1), (old2, new2))],
                "projected_xi_with_captain": round(score[0], 3),
                "gross_gain_vs_hold": round(score[0] - baseline[0], 3),
                "remaining_bank_proxy": remaining,
            })
    by_count = {}
    for n in (0, 1, 2):
        subset = [x for x in options if len(x["transfers"]) == n]
        by_count[str(n)] = sorted(subset, key=lambda x: (
            -x["gross_gain_vs_hold"], -x["remaining_bank_proxy"],
            str(x["transfers"])))[:10]
    if verified:
        for group in by_count.values():
            for item in group:
                hits = transfer_hit(len(item["transfers"]), verified["free_transfers"])
                item["hit_cost"] = hits
                item["net_gain_vs_hold"] = round(item["gross_gain_vs_hold"] - hits, 3)
    report = {
        "target_gw": forecast["target_gw"],
        "forecast_source": str(source),
        "squad_source": "data/picks.json, latest publicly published GW",
        "squad_event": picks.get("entry_history", {}).get("event"),
        "bank_tenths_million_proxy": bank,
        "baseline_expected_xi_with_captain": round(baseline[0], 3),
        "scenarios": by_count,
        "verified_private_inputs_used": bool(verified),
        "free_transfers": verified["free_transfers"] if verified else None,
        "budget_basis": "verified_selling_prices" if verified else "public_price_proxy",
        "warnings": [
            "Manual verification required before executing any transfer.",
            "Budget uses CURRENT quoted prices for both purchases and sales; selling proceeds may be lower.",
            "Free transfer balance is unknown: no hit cost is deducted. Compare net gain only after confirming hits.",
            "One-GW heuristic projections, NOT a multi-GW optimization.",
            "Two-transfer search uses a bounded shortlist and is not globally exhaustive.",
            "Player forecasts are not validated. Confirm injuries, deadline and prices manually.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GW{report['target_gw']}: {len(by_count['1'])} single and "
          f"{len(by_count['2'])} double scenario candidates saved")


if __name__ == "__main__":
    main()
