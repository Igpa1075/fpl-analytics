"""Exploratory chip timing analysis using ONLY pre-decision performance for matching.

Within the random-ID control cohort, compare chip users to non-chip users in
the same GW, matched by cumulative points at the END of the previous GW.
Outcome is cumulative points gained through the END of the following GW.
Observational association only, not a causal estimate or backtest.
"""
import json
import statistics
from pathlib import Path

DATA = Path("data")
SOURCE = DATA / "control_history.json"
OUTPUT = DATA / "chip_outcomes.json"
CHIPS = ("wildcard", "freehit", "bboost", "3xc")
MAX_PRE_POINTS_GAP = 25
MIN_TREATED = 5
MIN_MATCHED_TREATED = 5


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def record(gws, gw):
    value = gws.get(str(gw))
    return value if isinstance(value, dict) and value.get("status") == "ok" else None


def observations(managers, gw):
    observations = []
    for entry, gws in managers.items():
        prev, current, following = (record(gws, x) for x in (gw - 1, gw, gw + 1))
        if not (prev and current and following):
            continue
        baseline = prev.get("total_points")
        end = following.get("total_points")
        if not (number(baseline) and number(end)):
            continue
        # Exclude managers who activated another chip in the following GW:
        # the follow-up outcome would otherwise conflate two chip decisions.
        if following.get("chip") is not None:
            continue
        observations.append({
            "id": entry,
            "baseline": baseline,
            "gain_two_gws": end - baseline,
            "chip": current.get("chip"),
        })
    return observations


def compare(rows, chip):
    treated = [r for r in rows if r["chip"] == chip]
    controls = [r for r in rows if r["chip"] is None]
    if len(treated) < MIN_TREATED:
        return {"status": "insufficient_treated", "treated": len(treated),
                "eligible_controls": len(controls)}
    matched = []
    for person in treated:
        eligible = [c for c in controls
                    if abs(c["baseline"] - person["baseline"]) <= MAX_PRE_POINTS_GAP]
        if not eligible:
            continue
        nearest = min(eligible, key=lambda c: (abs(c["baseline"] - person["baseline"]), c["id"]))
        matched.append({
            "treated_gain": person["gain_two_gws"],
            "control_gain": nearest["gain_two_gws"],
            "baseline_gap": abs(nearest["baseline"] - person["baseline"]),
        })
    if len(matched) < MIN_MATCHED_TREATED:
        return {"status": "insufficient_matches", "treated": len(treated),
                "matched_treated": len(matched), "eligible_controls": len(controls)}
    differences = [m["treated_gain"] - m["control_gain"] for m in matched]
    return {
        "status": "exploratory_only",
        "treated": len(treated),
        "eligible_controls": len(controls),
        "matched_treated": len(matched),
        "mean_treated_gain": round(statistics.mean(m["treated_gain"] for m in matched), 2),
        "mean_matched_control_gain": round(statistics.mean(m["control_gain"] for m in matched), 2),
        "mean_difference_points": round(statistics.mean(differences), 2),
        "median_difference_points": round(statistics.median(differences), 2),
        "mean_absolute_baseline_gap": round(statistics.mean(m["baseline_gap"] for m in matched), 2),
        "matching": "same GW, nearest prior-GW cumulative points within 25, with replacement",
    }


def main():
    if not SOURCE.exists():
        print("Control history unavailable; skipping outcomes.")
        return
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    managers = data.get("managers", {})
    output = {
        "design": "retrospective_same_GW_prior_points_nearest_neighbor",
        "outcome": "total_points_at_GW_plus_1_minus_total_points_at_GW_minus_1",
        "comparison": "chip at GW vs no chip at GW",
        "scope": "control cohort only; GW2-8",
        "limitations": [
            "Association, NOT causal effect; prior points alone do not control for team quality, injuries or fixtures.",
            "Nearest-neighbor controls may be reused and are not independent.",
            "Small samples and multiple comparisons make results unstable.",
            "Missing histories and nonrepresentative entry-ID sampling may bias results.",
            "Excludes managers using any chip in the following GW.",
            "This is retrospective; not a prospective prediction or strategy recommendation.",
            "A GW chip can affect future transfers; two-GW window does not capture full long-term impact.",
        ],
        "gameweeks": {},
    }
    for gw in range(2, 9):
        rows = observations(managers, gw)
        output["gameweeks"][str(gw)] = {
            "eligible_managers": len(rows),
            "chips": {chip: compare(rows, chip) for chip in CHIPS},
        }
    OUTPUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved exploratory chip outcomes for {len(output['gameweeks'])} GWs")


if __name__ == "__main__":
    main()
