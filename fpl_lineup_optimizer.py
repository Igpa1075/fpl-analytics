"""Optimize a legal starting XI and captain from frozen next-GW forecasts.

Uses the last completed GW's squad as a *proxy*, not the actual upcoming
pre-deadline squad. Recommendations are advisory, never auto-submitted.
"""
import itertools
import json
from pathlib import Path

DATA = Path("data")
FORECASTS = DATA / "forecasts"
OUTPUT = DATA / "lineup_recommendation.json"


def main():
    if not FORECASTS.exists():
        print("No forecasts available; skipping lineup optimization.")
        return
    candidates = []
    for path in FORECASTS.glob("*.json"):
        forecast = json.loads(path.read_text(encoding="utf-8"))
        candidates.append((forecast["captured_at_utc"], path, forecast))
    if not candidates:
        print("No forecasts available.")
        return
    _, source, forecast = max(candidates)
    picks_path = DATA / "picks.json"
    if not picks_path.exists():
        print("No squad picks available.")
        return
    picks = json.loads(picks_path.read_text(encoding="utf-8"))
    ids = [p["element"] for p in picks.get("picks", [])]
    if len(ids) != 15 or len(set(ids)) != 15:
        raise ValueError("Expected 15 distinct squad players")
    projections = {p["player_id"]: p for p in forecast["predictions"]}
    missing = [i for i in ids if i not in projections]
    if missing:
        raise ValueError(f"Missing forecasts for squad IDs: {missing}")
    squad = [projections[i] for i in ids]
    best = None
    for xi in itertools.combinations(squad, 11):
        counts = {pos: sum(p["position_id"] == pos for p in xi) for pos in (1, 2, 3, 4)}
        if not (counts[1] == 1 and 3 <= counts[2] <= 5
                and 2 <= counts[3] <= 5 and 1 <= counts[4] <= 3):
            continue
        captain = max(xi, key=lambda p: (p["expected_points"], -p["player_id"]))
        score = sum(p["expected_points"] for p in xi) + captain["expected_points"]
        key = (round(score, 8), -captain["player_id"],
               tuple(sorted(p["player_id"] for p in xi)))
        if best is None or key > best[0]:
            best = (key, xi, captain)
    if best is None:
        raise ValueError("No legal starting XI available from squad")
    _, xi, captain = best
    starters = {p["player_id"] for p in xi}
    bench = sorted((p for p in squad if p["player_id"] not in starters),
                   key=lambda p: (-p["expected_points"], p["player_id"]))
    # Bench GK must be separated; outfield bench order prioritizes expected points.
    bench_gk = [p for p in bench if p["position_id"] == 1]
    outfield_bench = [p for p in bench if p["position_id"] != 1]
    vice = max((p for p in xi if p["player_id"] != captain["player_id"]),
               key=lambda p: (p["expected_points"], -p["player_id"]))
    report = {
        "target_gw": forecast["target_gw"],
        "forecast_captured_at_utc": forecast["captured_at_utc"],
        "forecast_source": str(source),
        "squad_source": "data/picks.json (last completed GW; may be stale)",
        "squad_event": picks.get("entry_history", {}).get("event"),
        "expected_xi_points_with_captain": round(best[0][0], 3),
        "formation": {
            "defenders": sum(p["position_id"] == 2 for p in xi),
            "midfielders": sum(p["position_id"] == 3 for p in xi),
            "forwards": sum(p["position_id"] == 4 for p in xi),
        },
        "starting_xi": sorted(xi, key=lambda p: (p["position_id"], -p["expected_points"])),
        "captain": captain,
        "vice_captain": vice,
        "bench_goalkeeper": bench_gk,
        "bench_outfield_order": outfield_bench,
        "warnings": [
            "Squad is the last completed GW, not necessarily current predeadline squad.",
            "Expected points use an unvalidated heuristic baseline.",
            "Ignores automatic substitutions, chip effects, and transfer optimization.",
            "Captain and vice-captain selections are advisory only.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GW{report['target_gw']} optimized XI: {report['formation']}, "
          f"captain {captain['name']}, expected {report['expected_xi_points_with_captain']}")


if __name__ == "__main__":
    main()
