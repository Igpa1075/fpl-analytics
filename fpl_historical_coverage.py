"""Validate GW1-10 historical fixture coverage before strategy backtesting."""
import json
from collections import defaultdict
from pathlib import Path

D = Path(__file__).resolve().parent / "data"


def main():
    source = D / "historical_players_gw1_10.json"
    if not source.exists():
        raise RuntimeError("Run fpl_historical_players.py first")
    state = json.loads(source.read_text(encoding="utf-8"))
    bootstrap = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    ids = {str(p["id"]) for p in bootstrap["elements"]}
    records = state.get("players", {})
    if not isinstance(records, dict):
        raise RuntimeError("Invalid historical players file")
    gws = {str(gw): {"players_with_fixture": 0, "player_fixture_rows": 0,
                     "players_with_minutes": 0, "points_sum_raw": 0,
                     "missing_fixture_value_rows": 0} for gw in range(1, 11)}
    duplicate_keys = []
    for pid, rows in records.items():
        seen = set()
        touched = set()
        played = set()
        for row in rows:
            gw = row.get("gw")
            if gw not in range(1, 11):
                continue
            fixture_key = (gw, row.get("fixture"))
            if fixture_key in seen:
                duplicate_keys.append({"player_id": pid, "gw": gw, "fixture": row.get("fixture")})
            seen.add(fixture_key)
            key = str(gw)
            gws[key]["player_fixture_rows"] += 1
            gws[key]["points_sum_raw"] += int(row.get("total_points") or 0)
            if row.get("value_at_fixture") is None:
                gws[key]["missing_fixture_value_rows"] += 1
            touched.add(key)
            if int(row.get("minutes") or 0) > 0:
                played.add(key)
        for key in touched:
            gws[key]["players_with_fixture"] += 1
        for key in played:
            gws[key]["players_with_minutes"] += 1
    result = {
        "processed_player_ids": len(records),
        "bootstrap_player_ids": len(ids),
        "coverage_pct": round(100 * len(set(records) & ids) / max(len(ids), 1), 2),
        "gws": gws,
        "duplicate_fixture_keys": duplicate_keys[:20],
        "duplicate_fixture_count": len(duplicate_keys),
        "safe_to_run_full_backtest": len(set(records) & ids) == len(ids) and not duplicate_keys,
        "limitations": [
            "Fixture points are raw per-player scores, not fantasy squad scores.",
            "Fixture values are not validated pre-deadline transfer prices.",
            "A complete player fixture dataset alone does not prevent hindsight leakage.",
        ],
    }
    path = D / "historical_coverage_report.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coverage_pct": result["coverage_pct"],
                      "duplicate_fixture_count": len(duplicate_keys),
                      "safe_to_run_full_backtest": result["safe_to_run_full_backtest"]}))


if __name__ == "__main__":
    main()
