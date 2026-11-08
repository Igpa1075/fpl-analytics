"""Frozen, transparent FPL next-GW baseline forecasts from daily snapshots.

These are simple heuristic predictions, NOT a trained or validated ML model.
Only snapshots captured before the target deadline are eligible.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOTS = Path("data/snapshots")
OUTPUT = Path("data/forecasts")


def num(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def forecast(snapshot):
    captured = datetime.fromisoformat(snapshot["captured_at_utc"].replace("Z", "+00:00"))
    future = sorted((e for e in snapshot["bootstrap"].get("events", [])
                     if e.get("deadline_time") and
                     datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")) > captured),
                    key=lambda e: e["deadline_time"])
    if not future:
        return None
    event = future[0]["id"]
    deadline = future[0]["deadline_time"]

    fixtures = [f for f in snapshot["fixtures"] if f.get("event") == event
                and not f.get("finished")]
    team_fixtures = {}
    for f in fixtures:
        for team, opponent, home in ((f["team_h"], f["team_a"], True),
                                     (f["team_a"], f["team_h"], False)):
            team_fixtures.setdefault(team, []).append({
                "opponent": opponent, "home": home,
                "difficulty": f.get("team_h_difficulty" if home else "team_a_difficulty"),
            })
    predictions = []
    for p in snapshot["bootstrap"]["elements"]:
        minutes = num(p.get("minutes"))
        appearances = max(1, num(p.get("starts"), minutes / 90))
        ppg = num(p.get("points_per_game"))
        form = num(p.get("form"), ppg)
        # Low-minute players are pulled towards 2 points, to avoid spurious
        # early-season high points-per-game projections.
        reliability = min(1.0, minutes / 900.0)
        base = reliability * (0.55 * form + 0.45 * ppg) + (1 - reliability) * 2.0
        chance = p.get("chance_of_playing_next_round")
        availability = (max(0.0, min(1.0, num(chance) / 100.0))
                        if chance is not None else
                        (0.0 if p.get("status") == "u" else 1.0))
        games = team_fixtures.get(p["team"], [])
        projected = 0.0
        for g in games:
            difficulty = num(g["difficulty"], 3)
            # Modest fixture adjustment, intentionally not learned on outcomes.
            fixture_factor = max(0.75, min(1.25, 1 + (3 - difficulty) * 0.08))
            projected += base * fixture_factor * availability
        predictions.append({
            "player_id": p["id"], "name": p.get("web_name"),
            "team_id": p["team"], "position_id": p.get("element_type"),
            "price_tenths_million": p.get("now_cost"),
            "availability": round(availability, 3),
            "fixtures": games,
            "expected_points": round(projected, 3),
        })
    predictions.sort(key=lambda p: (-p["expected_points"], p["player_id"]))
    return {
        "captured_at_utc": snapshot["captured_at_utc"],
        "target_gw": event,
        "deadline_utc": deadline,
        "method": "heuristic_form_ppg_minutes_availability_fixture_v1",
        "predictions": predictions,
        "warnings": [
            "Unvalidated heuristic baseline; do not interpret as a proven edge.",
            "No optimized transfers or multi-GW forecasts yet.",
            "Historical FPL form is already aggregate and not a causal player model.",
            "Only snapshots captured before deadline are used.",
        ],
    }


def main():
    if not SNAPSHOTS.exists():
        print("No snapshots yet.")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    created = 0
    for path in sorted(SNAPSHOTS.glob("*.json")):
        target = OUTPUT / path.name
        if target.exists():
            continue
        result = forecast(json.loads(path.read_text(encoding="utf-8")))
        if result is None:
            continue
        target.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
        created += 1
    print(f"Created {created} frozen forecasts")


if __name__ == "__main__":
    main()
