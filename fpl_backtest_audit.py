"""Audit historical FPL backtest inputs without introducing future-data leakage.

Run: python fpl_backtest_audit.py
Output: data/backtest_readiness.json
This is a readiness audit, NOT a simulated strategy result.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
OUT = DATA / "backtest_readiness.json"
TARGET_GWS = list(range(1, 11))


def load(name):
    path = DATA / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        return None


def main():
    history = load("history.json") or {}
    league = load("league_standings.json") or {}
    elite = load("elite100_history_summary.json") or {}
    archive = load("league_history.json") or {}
    bootstrap = load("bootstrap.json") or {}
    fixtures = load("fixtures.json")
    historical_players = load("historical_players_gw1_10.json") or {}
    own = {int(row["event"]): row for row in history.get("current", [])}
    complete_own = sorted(set(TARGET_GWS) & set(own))
    elite_coverage = elite.get("coverage", {})
    league_archive_gws = sorted(
        int(k) for k in archive.get("gameweeks", {}) if str(k).isdigit()
    )
    result = {
        "target_gameweeks": TARGET_GWS,
        "own_history_available_gws": complete_own,
        "own_total_after_gw10": own.get(10, {}).get("total_points"),
        "league_id": league.get("league_id"),
        "league_snapshot_last_finished_gw": league.get("last_finished_gw"),
        "league_snapshot_members": len(league.get("members", [])),
        "league_archived_gws": league_archive_gws,
        "elite_cohort_coverage": elite_coverage,
        "current_bootstrap_present": bool(bootstrap.get("elements")),
        "fixtures_present": isinstance(fixtures, list),
        "historical_player_records": len(historical_players.get("players", {})),
        "historical_player_collection_total": historical_players.get("total_players"),
        "historical_predeadline_player_prices_present": False,
        "historical_predeadline_availability_snapshots_present": False,
        "historical_predeadline_predictions_present": False,
        "backtest_completed": False,
        "blocking_requirements": [
            "Collect point-in-time prices and player availability for each GW deadline; current bootstrap prices must not be backfilled as historical prices.",
            "Construct and freeze predeadline expected-points features using only prior matches and information published before each deadline.",
            "Implement 15-player squad, starting XI, captain, autosubs, transfers, selling prices, bank and chips with season-specific FPL rules.",
            "Score simulated decisions on actual GW results and compare to same-GW mini-league standings.",
        ],
        "warnings": [
            "Elite top-100 selected retrospectively is subject to survivorship bias.",
            "Fixture or player match-history value fields are not guaranteed to equal deadline-time purchase prices.",
            "A GW9 league snapshot cannot be used to rank a GW10 simulated score.",
        ],
    }
    DATA.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
