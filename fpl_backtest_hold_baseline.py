"""Conservative FPL counterfactual: hold the real GW1 squad for ten GWs.

The starting squad is an observed historical baseline, not a predicted GW1
selection. Each GW's XI and captain use only prior-GW player results.
No transfers, chips, price assumptions, or post-deadline availability data.
This is NOT the final optimized-strategy backtest.
"""
import json
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent / "data"
API = "https://fantasy.premierleague.com/api"


def fetch(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "FPL-baseline/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def choose(squad, position, points_before):
    # Stable tie-breakers ensure that zero-information GW1 is reproducible.
    ranked = sorted(squad, key=lambda pid: (-points_before.get(pid, 0), pid))
    keep = []
    for pos, minimum in ((1, 1), (2, 3), (3, 2), (4, 1)):
        keep += [p for p in ranked if position[p] == pos][:minimum]
    remaining = [p for p in ranked if p not in keep and position[p] != 1]
    for pid in remaining:
        if len(keep) == 11:
            break
        if sum(position[p] == position[pid] for p in keep) < {2: 5, 3: 5, 4: 3}[position[pid]]:
            keep.append(pid)
    if len(keep) != 11:
        raise RuntimeError("Unable to construct legal starting XI")
    return keep


def main():
    bootstrap = json.loads((D / "bootstrap.json").read_text(encoding="utf-8"))
    state = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))
    players = state["players"]
    elements = {int(p["id"]): p for p in bootstrap["elements"]}
    entry = json.loads((D / "entry.json").read_text(encoding="utf-8"))
    entry_id = int(entry.get("id", 5150250))
    initial = fetch(f"/entry/{entry_id}/event/1/picks/")
    initial_picks = initial["picks"]
    squad = [int(p["element"]) for p in initial_picks]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise RuntimeError("Invalid GW1 squad")
    missing = [p for p in squad if str(p) not in players]
    if missing:
        raise RuntimeError(f"Missing historical players: {missing}")
    positions = {pid: int(elements[pid]["element_type"]) for pid in squad}
    if sorted([sum(positions[p] == pos for p in squad) for pos in range(1, 5)]) != sorted([2, 5, 5, 3]):
        raise RuntimeError("Invalid squad position distribution")

    result = []
    for gw in range(1, 11):
        prior = {}
        actual = {}
        for pid in squad:
            rows = players[str(pid)]
            prior_rows = [r for r in rows if int(r["gw"]) < gw]
            recent = [r for r in prior_rows if int(r["gw"]) >= gw - 3]
            # Recent points per GW, never current GW; no post-deadline inputs.
            prior[pid] = sum(int(r.get("total_points") or 0) for r in recent)
            actual[pid] = sum(int(r.get("total_points") or 0) for r in rows if int(r["gw"]) == gw)
        if gw == 1:
            # GW1 historical manager choice is fixed and observed, not backtested.
            starters = [int(p["element"]) for p in initial_picks if int(p["position"]) <= 11]
            captain = next(int(p["element"]) for p in initial_picks if p.get("is_captain"))
        else:
            starters = choose(squad, positions, prior)
            captain = max(starters, key=lambda pid: (prior[pid], -pid))
        # An intentionally simplified gross score: no autosubs or vice captain.
        gross = sum(actual[p] for p in starters) + actual[captain]
        result.append({"gw": gw, "starters": starters, "captain": captain,
                       "gross_points_without_autosubs": gross,
                       "auto_substitutions_modelled": False,
                       "transfers": 0, "chip": None})
    report = {
        "status": "experimental_baseline_not_full_backtest",
        "entry_id": entry_id,
        "initial_squad_source": "manager's actual published GW1 picks",
        "decision_policy": "GW1 observed lineup; GW2-10 rolling previous-three-GW points; no transfers",
        "gross_total_without_autosubs": sum(r["gross_points_without_autosubs"] for r in result),
        "gws": result,
        "limitations": [
            "Initial squad and GW1 lineup were selected by real manager, not by the model.",
            "No bench autosub, vice-captain substitution, or chips; totals are not exact FPL scoring.",
            "No player transfers, deadline prices, historical injury status, or fixture projections.",
            "Recent form features are strictly prior-GW; cannot be interpreted as optimized expected points.",
        ],
    }
    path = D / "backtest_hold_squad_baseline.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gross_total_without_autosubs": report["gross_total_without_autosubs"],
                      "gws": len(result)}))


if __name__ == "__main__":
    main()
