"""Descriptive GW-by-GW comparison of fixed elite and random-ID control cohorts.

This is observational: current elite status is selected on outcomes.
Never interpret differences as causal effects or predictive backtests.
"""
import json
from collections import Counter
from pathlib import Path

DATA = Path("data")
ELITE_CACHE = DATA / "elite100_cache.json"
ELITE_IDS = DATA / "elite100_cohort.json"
CONTROL_HISTORY = DATA / "control_history.json"
OUTPUT = DATA / "cohort_comparison.json"
GWS = range(1, 10)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(records):
    count = len(records)
    if not count:
        return {"n": 0}
    chips = Counter(str(r.get("chip") or "none") for r in records)
    captains = Counter(str(r["captain"]) for r in records if r.get("captain") is not None)
    transfers = [r["transfers"] for r in records if isinstance(r.get("transfers"), int)]
    hits = [r["transfer_cost"] for r in records if isinstance(r.get("transfer_cost"), (int, float))]
    points = [r["points"] for r in records if isinstance(r.get("points"), (int, float))]
    return {
        "n": count,
        "chip_counts": dict(sorted(chips.items())),
        "chip_rates": {k: round(v / count, 4) for k, v in sorted(chips.items())},
        "top_captains": [{"player_id": int(k), "count": v, "share": round(v / count, 4)}
                         for k, v in captains.most_common(10)],
        "mean_transfers": round(sum(transfers) / len(transfers), 3) if transfers else None,
        "transfers_observed": len(transfers),
        "mean_transfer_cost": round(sum(hits) / len(hits), 3) if hits else None,
        "transfer_cost_observed": len(hits),
        "mean_gw_points": round(sum(points) / len(points), 3) if points else None,
        "gw_points_observed": len(points),
    }


def main():
    if not (ELITE_CACHE.exists() and ELITE_IDS.exists()):
        print("Elite history not available yet; skipping comparison.")
        return
    if not CONTROL_HISTORY.exists():
        print("Control history not available yet; skipping comparison.")
        return

    elite = read(ELITE_CACHE)
    ids = [str(x) for x in read(ELITE_IDS)["manager_ids"]]
    control_state = read(CONTROL_HISTORY)
    control = control_state.get("managers", {})
    result = {
        "method": "descriptive_fixed_elite_vs_random_id_controls",
        "elite_cohort_size": len(ids),
        "control_managers_started": len(control),
        "gameweeks": {},
        "limitations": [
            "Current top-100 selection is conditioned on final/current success (selection bias).",
            "Random entry IDs have not been proven representative of all FPL managers.",
            "Control data are collected incrementally and may be incomplete or nonrandomly missing.",
            "Do not interpret elite-control differences as causal or prospective predictive power.",
            "Elite cache does not contain per-GW points; do not compare score means across groups.",
            "Chip and captain rates use available GW records as denominators.",
        ],
    }
    for gw in GWS:
        key = str(gw)
        er = [elite.get(entry, {}).get(key) for entry in ids]
        er = [r for r in er if isinstance(r, dict) and len(r.get("players", [])) == 15]
        cr = [gws.get(key) for gws in control.values()]
        cr = [r for r in cr if isinstance(r, dict) and r.get("status") == "ok"
              and len(r.get("players", [])) == 15]
        es, cs = summarize(er), summarize(cr)
        chip_differences = {
            chip: round(es["chip_rates"].get(chip, 0) - cs["chip_rates"].get(chip, 0), 4)
            for chip in sorted(set(es.get("chip_rates", {})) | set(cs.get("chip_rates", {})))
        } if er and cr else {}
        result["gameweeks"][key] = {
            "elite": es,
            "control": cs,
            "elite_minus_control_chip_rate": chip_differences,
            "comparison_available": bool(er and cr),
        }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    available = [gw for gw, v in result["gameweeks"].items() if v["comparison_available"]]
    print(f"Comparison saved: {len(available)} GWs with both cohorts; GWs {available}")


if __name__ == "__main__":
    main()
