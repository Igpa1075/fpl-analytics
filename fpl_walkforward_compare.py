"""Compare a GW1-9 forward-only model replay to actual elite-manager picks.

Both columns use identical simplified scoring: the first 11 picks and
captain double points, no autosubs, no chip bonuses, no transfer deductions.
This is a conditional *lineup* comparison, not an official FPL rank comparison.
"""
import json
from pathlib import Path

DATA = Path("data")
GWS = range(1, 10)


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    replay = load("walkforward_elite100_gw1_9.json")
    picks = load("elite100_cache.json")
    history = load("historical_player_summaries.json")
    cohort = load("elite100_cohort.json")["manager_ids"]
    if len(cohort) != 100 or len(set(map(str, cohort))) != 100:
        raise ValueError("Expected exactly 100 distinct elite manager IDs")
    player_gw = {}
    for pid, doc in history.items():
        if not isinstance(doc, dict) or "history" not in doc:
            continue
        player_gw[int(pid)] = {int(r["round"]): int(r.get("total_points", 0))
                               for r in doc["history"] if r.get("round") is not None}

    by_manager = {}
    by_week = {str(gw): {"gw": gw, "model": 0, "actual": 0,
                         "delta": 0, "managers": 0} for gw in GWS}
    chips = {}
    excluded = []
    for mid in map(str, cohort):
        if mid not in replay["managers"] or mid not in picks:
            raise ValueError(f"Missing manager {mid}")
        actual_weeks = picks[mid]
        model_weeks = {int(w["gw"]): w for w in replay["managers"][mid]["weeks"]}
        rows = []
        for gw in GWS:
            p = actual_weeks.get(str(gw))
            m = model_weeks.get(gw)
            if not p or not m or len(p.get("players", [])) != 15:
                raise ValueError(f"Incomplete GW{gw} for {mid}")
            # Published pick order: first 11 are selected starting XI,
            # last 4 bench. Substitutions are not simulated in either side.
            xi = list(map(int, p["players"][:11]))
            cap = int(p["captain"])
            if cap not in xi:
                # Vice-captain is absent from cached picks. Exclude this
                # manager-week from BOTH sides, rather than guessing.
                excluded.append({"manager": mid, "gw": gw, "reason": "captain_outside_xi_vice_unknown"})
                continue
            missing = [pid for pid in xi + [cap] if gw not in player_gw.get(pid, {})]
            if missing:
                excluded.append({"manager": mid, "gw": gw, "reason": "missing_player_history", "players": missing})
                continue
            actual = sum(player_gw[i][gw] for i in xi) + player_gw[cap][gw]
            model = int(m["model_actual_points_no_chips"])
            chip = p.get("chip") or "none"
            chips[chip] = chips.get(chip, 0) + 1
            row = {"gw": gw, "model": model, "actual": actual,
                   "delta": model - actual, "actual_chip": chip,
                   "model_captain": m["captain"], "actual_captain": cap,
                   "model_transfer": m.get("transfer")}
            rows.append(row)
            agg = by_week[str(gw)]
            agg["model"] += model
            agg["actual"] += actual
            agg["delta"] += model - actual
            agg["managers"] += 1
        by_manager[mid] = {"model": sum(r["model"] for r in rows),
                           "actual": sum(r["actual"] for r in rows),
                           "delta": sum(r["delta"] for r in rows),
                           "weeks": rows}
    for gw in GWS:
        if by_week[str(gw)]["managers"] == 0:
            raise ValueError(f"No valid manager-weeks for GW{gw}")
    model_total = sum(m["model"] for m in by_manager.values())
    actual_total = sum(m["actual"] for m in by_manager.values())
    replay_included = sum(w["model_actual_points_no_chips"] for mid in map(str, cohort)
                          for w in replay["managers"][mid]["weeks"]
                          if not any(e["manager"] == mid and e["gw"] == w["gw"] for e in excluded))
    if model_total != replay_included:
        raise ValueError("Model replay mismatch; do not publish comparison")
    wins = sum(m["delta"] > 0 for m in by_manager.values())
    losses = sum(m["delta"] < 0 for m in by_manager.values())
    result = {
        "method": "matched_elite100_starting11_captain_double_no_chips_v1",
        "scope": "GW1-GW9, fixed post-hoc elite top-100 cohort",
        "summary": {"managers": 100, "matched_manager_weeks": sum(x["managers"] for x in by_week.values()),
                    "excluded_manager_weeks": len(excluded), "model_total": model_total,
                    "actual_total": actual_total,
                    "delta_total": model_total - actual_total,
                    "model_mean_per_manager_included_weeks": round(model_total / 100, 2),
                    "actual_mean_per_manager_included_weeks": round(actual_total / 100, 2),
                    "delta_mean_per_manager_included_weeks": round((model_total - actual_total) / 100, 2),
                    "model_wins": wins, "model_losses": losses,
                    "ties": 100 - wins - losses},
        "by_gw": by_week, "chips_observed": chips, "excluded": excluded,
        "coverage_warning": "Incomplete pairs: inspect exclusions before interpreting scores" if excluded else None,

        "limitations": [
            "Comparison is not official FPL points: excludes autosubs, chips, transfer hits.",
            "Manager starting XI reconstructed from first 11 stored pick IDs; verify original API ordering.",
            "Manager-weeks with captain outside the first XI or missing player history are excluded from both totals.",
            "Captain not in first 11: exclude both manager-week scores from paired comparison.",
            "Means are per 100 managers across available weeks, not nine-week complete totals when exclusions exist.",
            "Captain-outside-XI manager-weeks excluded from BOTH sides; vice-captain not cached.",
            "GW1 squads are copied from elite managers, not independently drafted by the model.",
            "Replay uses approximate historical prices, current team metadata, and neutral fixture difficulty.",
            "Replay performs exactly one free transfer each GW2-GW9; actual managers have different strategies.",
            "Elite managers selected using later rankings: survivorship bias.",
            "ESPN advanced role signals were not reconstructed predeadline for GW1-GW9.",
            "Replay does not validate the complete current GW11 contextual forecast model."
        ],
        "by_manager": by_manager
    }
    target = DATA / "walkforward_elite100_comparison.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    print("Per-GW:", json.dumps(by_week))
    print("Chips excluded:", json.dumps(chips))


if __name__ == "__main__":
    main()
