"""Rank existing hold/1/2 transfer scenarios over up to five future GWs.

All inputs are from one frozen snapshot. This is a static-squad comparison:
no later transfers, future injuries, changing prices or chip strategies.
"""
import json
from collections import Counter
from pathlib import Path
from fpl_transfer_scenarios import lineup_score

DATA = Path("data")
SNAPS = DATA / "snapshots"
SCENARIOS = DATA / "transfer_scenarios.json"
OUTPUT = DATA / "multiweek_transfer_plan.json"
HORIZON = 5


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main():
    if not SCENARIOS.exists():
        print("No transfer scenarios yet.")
        return
    plan = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    path = DATA / plan["forecast_source"]
    if not path.exists():
        print("Frozen forecast missing.")
        return
    frozen = json.loads(path.read_text(encoding="utf-8"))
    snapshot_file = SNAPS / path.name
    if not snapshot_file.exists():
        print("Matching frozen snapshot missing.")
        return
    snap = json.loads(snapshot_file.read_text(encoding="utf-8"))
    target = int(frozen["target_gw"])
    last_gw = min(38, target + HORIZON - 1)
    future = {}
    for f in snap["fixtures"]:
        gw = f.get("event")
        if gw is None or not target <= gw <= last_gw or f.get("finished"):
            continue
        for team, opponent, home in ((f["team_h"], f["team_a"], True),
                                     (f["team_a"], f["team_h"], False)):
            difficulty = number(f.get("team_h_difficulty" if home else "team_a_difficulty"), 3)
            future.setdefault((gw, team), []).append({
                "opponent": opponent, "home": home, "difficulty": difficulty})
    base_players = {p["player_id"]: p for p in frozen["predictions"]}
    picks = json.loads((DATA / "picks.json").read_text(encoding="utf-8"))
    owned = [p["element"] for p in picks["picks"]]
    if len(owned) != 15 or len(set(owned)) != 15:
        raise ValueError("Invalid owned squad")
    # Estimate future form from the same frozen data. No future actuals enter.
    projected = {}
    for gw in range(target, last_gw + 1):
        players = {}
        for pid, p in base_players.items():
            next_games = p.get("fixtures", [])
            # Reverse the one-GW fixture adjustment to obtain a baseline rate.
            current_factor = sum(max(0.75, min(1.25, 1 + (3 - number(
                g.get("difficulty"), 3)) * .08)) for g in next_games)
            rate = p["expected_points"] / current_factor if current_factor else 0.0
            # If blank in target GW, recover a provisional per-match rate from
            # frozen bootstrap player stats, not future match information.
            if not current_factor:
                player = next((x for x in snap["bootstrap"]["elements"]
                               if x["id"] == pid), None)
                if player:
                    minutes = number(player.get("minutes"))
                    reliability = min(1.0, minutes / 900.0)
                    rate = (reliability * (.55 * number(player.get("form")) +
                            .45 * number(player.get("points_per_game"))) +
                            (1 - reliability) * 2.0) * p["availability"]
            games = future.get((gw, p["team_id"]), [])
            points = rate * sum(max(.75, min(1.25, 1 + (3 - g["difficulty"]) * .08))
                                for g in games)
            players[pid] = dict(p, expected_points=round(points, 4))
        projected[gw] = players
    results = []
    for count, scenarios in plan["scenarios"].items():
        for item in scenarios:
            ids = set(owned)
            for transfer in item["transfers"]:
                ids.remove(transfer["out"])
                ids.add(transfer["in"])
            if len(ids) != 15:
                continue
            if max(Counter(base_players[i]["team_id"] for i in ids).values()) > 3:
                continue
            weekly = []
            for gw in range(target, last_gw + 1):
                result = lineup_score([projected[gw][pid] for pid in ids])
                weekly.append({"gw": gw, "expected_xi_with_captain":
                               round(result[0], 3) if result else None})
            total = sum(x["expected_xi_with_captain"] for x in weekly
                        if x["expected_xi_with_captain"] is not None)
            results.append({
                "transfer_count": int(count),
                "transfers": item["transfers"],
                "remaining_bank_proxy": item["remaining_bank_proxy"],
                "weekly": weekly,
                "five_gw_gross_points": round(total, 3),
            })
    hold = next(x["five_gw_gross_points"] for x in results
                if x["transfer_count"] == 0)
    for row in results:
        row["gross_gain_vs_hold"] = round(row["five_gw_gross_points"] - hold, 3)
        # Display hypothetical hit costs, not claims about actual free transfers.
        row["net_gain_if_all_transfers_cost_4"] = round(
            row["gross_gain_vs_hold"] - 4 * row["transfer_count"], 3)
    results.sort(key=lambda r: (-r["gross_gain_vs_hold"], r["transfer_count"]))
    OUTPUT.write_text(json.dumps({
        "target_gw": target, "last_gw": last_gw,
        "captured_at_utc": snap["captured_at_utc"],
        "forecast_source": str(path),
        "snapshot_source": str(snapshot_file),
        "hold_five_gw_expected_points": hold,
        "ranked_scenarios": results,
        "warnings": [
            "Illustrative frozen-data projection, not validated future GW predictions.",
            "Only scenarios shortlisted by the one-GW planner are considered.",
            "Future availability assumed unchanged; future fixture schedule may change.",
            "No subsequent transfers, chip usage or captain fallback are simulated.",
            "Current squad, selling prices and free transfer count remain unknown.",
            "Hypothetical hit-cost column is NOT the actual net transfer value.",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Compared {len(results)} scenarios through GW{last_gw}")


if __name__ == "__main__":
    main()
