"""Score frozen pre-deadline FPL forecasts against completed GW results.

One forecast per GW: the latest captured before its deadline. This avoids
counting multiple daily forecasts of the same GW as independent observations.
"""
import json
import math
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path("data")
FORECASTS = ROOT / "forecasts"
OUT = ROOT / "forecast_evaluation.json"
API = "https://fantasy.premierleague.com/api"


def fetch(endpoint):
    req = urllib.request.Request(API + endpoint, headers={
        "User-Agent": "fpl-analytics/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metrics(rows):
    if not rows:
        return None
    errors = [r["predicted"] - r["actual"] for r in rows]
    return {
        "n": len(rows),
        "mae": round(sum(abs(e) for e in errors) / len(errors), 4),
        "rmse": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 4),
        "bias": round(sum(errors) / len(errors), 4),
        "actual_mean": round(sum(r["actual"] for r in rows) / len(rows), 4),
        "predicted_mean": round(sum(r["predicted"] for r in rows) / len(rows), 4),
    }


def main():
    if not FORECASTS.exists():
        print("No frozen forecasts yet.")
        return
    bootstrap = fetch("/bootstrap-static/")
    finished = {int(e["id"]): e for e in bootstrap["events"]
                if e.get("finished") and e.get("data_checked")}
    by_gw = {}
    for path in sorted(FORECASTS.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        gw = int(doc["target_gw"])
        captured = parse_time(doc["captured_at_utc"])
        deadline = parse_time(doc["deadline_utc"])
        if captured >= deadline or gw not in finished:
            continue
        if gw not in by_gw or captured > by_gw[gw][0]:
            by_gw[gw] = (captured, path, doc)
    reports = []
    for gw, (_, path, doc) in sorted(by_gw.items()):
        live = fetch(f"/event/{gw}/live/")
        actual = {int(k): v for k, v in ((p["id"], p["stats"]) for p in live["elements"])}
        rows = []
        for p in doc["predictions"]:
            player_id = int(p["player_id"])
            stats = actual.get(player_id)
            if stats is None:
                continue
            rows.append({
                "player_id": player_id,
                "predicted": float(p["expected_points"]),
                "actual": float(stats["total_points"]),
                "minutes": int(stats.get("minutes", 0)),
                "fixtures": len(p.get("fixtures", [])),
            })
        played = [r for r in rows if r["minutes"] > 0]
        with_fixture = [r for r in rows if r["fixtures"] > 0]
        reports.append({
            "gw": gw,
            "forecast_file": str(path),
            "captured_at_utc": doc["captured_at_utc"],
            "all_players": metrics(rows),
            "scheduled_players": metrics(with_fixture),
            "players_with_minutes": metrics(played),
            "zero_prediction_baseline_scheduled": metrics([
                dict(r, predicted=0.0) for r in with_fixture]),
            "limitations": [
                "Actual points use the FPL event live endpoint after data_checked.",
                "This evaluates all listed players, not a selected fantasy XI.",
                "Playing-time filter uses outcomes and is diagnostic only.",
                "Multiple daily snapshots per GW are NOT independent tests.",
            ],
        })
    report = {
        "method": "latest_predeadline_snapshot_per_completed_gw",
        "completed_gws_evaluated": len(reports),
        "gameweeks": reports,
        "warnings": [
            "Small samples of completed GWs do not establish forecast skill.",
            "Do not tune model coefficients on the same GWs used to claim out-of-sample accuracy.",
            "Forecasts are immutable; evaluation can refresh after FPL corrections.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evaluated {len(reports)} completed GWs")


if __name__ == "__main__":
    main()
