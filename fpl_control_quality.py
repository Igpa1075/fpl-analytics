"""Audit control-cohort sampling, historical coverage and comparison readiness.

This reports observable quality checks; it does NOT certify representativeness.
"""
import json
from collections import Counter
from pathlib import Path

DATA = Path("data")
COHORT = DATA / "control_cohort.json"
HISTORY = DATA / "control_history.json"
ELITE = DATA / "elite100_cohort.json"
OUTPUT = DATA / "control_quality_report.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    if not COHORT.exists():
        print("Control cohort not available yet.")
        return
    cohort = read(COHORT)
    sample = [int(x) for x in cohort.get("sample_ids", [])]
    results = cohort.get("results", {})
    valid = {key for key, item in results.items() if item.get("status") == "ok"}
    upper = int(cohort["id_upper_bound_at_creation"])
    elite = {str(x) for x in read(ELITE)["manager_ids"]} if ELITE.exists() else set()
    history = read(HISTORY).get("managers", {}) if HISTORY.exists() else {}
    statuses = Counter(item.get("status", "unknown") for item in results.values())
    started = Counter(str(results[key].get("started_event")) for key in valid)
    gw_coverage = {}
    for gw in range(1, 10):
        records = [gws.get(str(gw)) for gws in history.values()]
        gw_coverage[str(gw)] = {
            "ok": sum(isinstance(r, dict) and r.get("status") == "ok" for r in records),
            "not_available": sum(isinstance(r, dict) and r.get("status") == "not_available" for r in records),
            "missing": sum(r is None for r in records),
        }
    id_quartiles = [0, 0, 0, 0]
    for entry in sample:
        idx = min(3, (entry - 1) * 4 // upper)
        id_quartiles[idx] += 1
    problems = []
    if len(set(sample)) != len(sample):
        problems.append("Duplicate IDs in sampled cohort")
    if any(entry < 1 or entry > upper for entry in sample):
        problems.append("Sample ID outside creation bounds")
    if any(key not in {str(x) for x in sample} for key in results):
        problems.append("Result for ID outside frozen sample")
    if any(key not in valid for key in history):
        problems.append("History contains manager without valid entry result")
    report = {
        "design": cohort.get("design"),
        "seed": cohort.get("seed"),
        "id_upper_bound_at_creation": upper,
        "target": len(sample),
        "processed": len(results),
        "valid": len(valid),
        "status_counts": dict(statuses),
        "sample_id_quartiles": id_quartiles,
        "valid_started_event_counts": dict(sorted(started.items())),
        "elite_overlap_valid": len(valid & elite),
        "history_managers": len(history),
        "history_gw_coverage": gw_coverage,
        "checks": {"passed": not problems, "problems": problems},
        "warnings": [
            "Uniform sampled entry IDs do not establish a representative sample of active managers.",
            "The upper bound is total_players, not a verified maximum entry ID.",
            "History is filled incrementally, so missingness and early comparisons can be biased.",
            "The fixed elite cohort was selected based on outcomes; comparison is descriptive.",
            "Current overall ranks and points must not be used as pre-deadline covariates.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("processed", "valid", "history_managers", "checks")}, indent=2))
    if problems:
        raise RuntimeError("; ".join(problems))


if __name__ == "__main__":
    main()
