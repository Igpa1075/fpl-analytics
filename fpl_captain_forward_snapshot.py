"""Immutable pre-deadline captain-policy predictions for GW11-15.

Uses last PUBLIC manager squad as a fixed-squad reference, not a claimed
live manager squad or an executable transfer recommendation. Does not use
GW outcome data. Snapshot is never overwritten after its first creation.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from fpl_backtest_hold_baseline import D, choose
from fpl_backtest_captain_policy_experiment import rank

POLICIES = ("form_3", "season_form", "minutes_weighted", "reliability")
TARGETS = set(range(11, 16))


def snapshot(boot, picks, players, gw, now):
    event = next(e for e in boot["events"] if int(e["id"]) == gw)
    deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
    if now >= deadline:
        return None
    source_gw = int(picks["entry_history"]["event"])
    if source_gw >= gw:
        raise ValueError("Future/current picks cannot be used as pre-deadline squad")
    if source_gw < gw - 1:
        return None  # stale squad; never silently pretend it is current
    squad = [int(x["element"]) for x in picks["picks"]]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid source squad")
    elements = {int(p["id"]): p for p in boot["elements"]}
    positions = {p: int(elements[p]["element_type"]) for p in squad}
    if [sum(positions[p] == t for p in squad) for t in range(1, 5)] != [2, 5, 5, 3]:
        raise ValueError("Invalid squad positions")
    # Require all prior-GW histories needed for ranking. Data through GW10
    # is available in the historical archive; beyond that require a separate
    # pre-deadline history ingestion before making a prediction.
    if gw > 11:
        return None
    if any(str(p) not in players for p in squad):
        return None
    form = {p: rank(p, players, gw, "form_3")[0] for p in squad}
    xi = choose(squad, positions, form)
    eligible = [p for p in xi if positions[p] != 1]
    decisions = {}
    for policy in POLICIES:
        ordered = sorted(eligible, key=lambda p: (rank(p, players, gw, policy), -p),
                         reverse=True)
        decisions[policy] = {"captain": ordered[0], "vice_captain": ordered[1]}
    return {
        "status": "frozen_predeadline_prediction",
        "created_at_utc": now.isoformat(),
        "deadline_utc": deadline.isoformat(),
        "gw": gw,
        "source_published_squad_gw": source_gw,
        "squad": squad,
        "starting_xi": xi,
        "policies": decisions,
        "note": "Fixed published squad, no proposed transfers, no expected-points calibration."
    }


def main():
    now = datetime.now(timezone.utc)
    boot = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    picks = json.loads((D / "picks.json").read_text(encoding="utf-8"))
    players = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    outdir = D / "captain_forward_snapshots"
    outdir.mkdir(exist_ok=True)
    results = []
    for gw in sorted(TARGETS):
        path = outdir / f"gw{gw}.json"
        if path.exists():
            results.append({"gw": gw, "status": "already_frozen"})
            continue
        result = snapshot(boot, picks, players, gw, now)
        if result is None:
            results.append({"gw": gw, "status": "not_eligible_or_missing_predeadline_data"})
            continue
        # Exclusive creation: never overwrite an existing prediction.
        with path.open("x", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
        results.append({"gw": gw, "status": "frozen"})
    print(json.dumps(results))


if __name__ == "__main__":
    main()
