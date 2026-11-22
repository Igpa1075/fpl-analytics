"""Defensive risk diagnostics for forward FPL forecasts.

No arbitrary narrative penalties. Team defense uses only pre-GW results.
Key defensive absences are *flagged*, not assigned an unvalidated causal penalty.
"""
from collections import defaultdict
import math

def clip(x, lo, hi):
    return max(lo, min(hi, x))

def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def defensive_form(team_data, league_rate):
    """Shrink recent conceded rate toward historical conceded rate."""
    season = max(.15, team_data.get("defense", league_rate))
    recent = max(.15, team_data.get("recent_defense", season))
    # Same conservative bounded movement for all clubs, not Arsenal-specific.
    trend = clip((recent / season) ** .4, .86, 1.16)
    return trend

def defensive_availability(players, club):
    """Flag prominent keeper/DEF with FPL injury/suspension status.

    This is informational; an injured backup goalkeeper is not equivalent
    to an injured starter. The model does not infer tactical importance.
    """
    defenders=[p for p in players if int(p["team"])==club and int(p["element_type"]) in (1,2)]
    keepers=sorted((p for p in defenders if int(p["element_type"])==1),
                   key=lambda p:-number(p.get("minutes")))
    regular_defenders=sorted((p for p in defenders if int(p["element_type"])==2),
                             key=lambda p:-number(p.get("minutes")))[:4]
    key = keepers[:1]+regular_defenders
    missing=[{"id":int(p["id"]),"name":p.get("web_name"),"type":int(p["element_type"]),
              "status":p.get("status"),"minutes":number(p.get("minutes"))}
             for p in key if p.get("status") not in ("a",None)]
    return {"key_defensive_absences":missing,
            "primary_gk_flag":any(x["type"]==1 for x in missing),
            "review_required":bool(missing)}

def squad_defensive_concentration(picks, player_lookup):
    """Diagnostics only: reveal correlated clean-sheet exposure in manager XI."""
    if not picks:
        return {"status":"no_picks"}
    starters=[]
    clubs=defaultdict(list)
    for pick in picks.get("picks",[]):
        if int(pick.get("position",99))>11:
            continue
        player=player_lookup.get(int(pick["element"]))
        if not player or int(player["element_type"]) not in (1,2):
            continue
        team=int(player["team"])
        clubs[team].append({"id":int(player["id"]),"name":player.get("web_name")})
        starters.append(int(player["id"]))
    clusters=[{"club_id":club,"players":rows,"count":len(rows)}
              for club,rows in clubs.items() if len(rows)>=2]
    clusters.sort(key=lambda r:(-r["count"],r["club_id"]))
    return {"status":"diagnostic_not_selection_penalty",
            "starting_defensive_players":len(starters),
            "same_club_clusters":clusters,
            "note":"Correlated clean-sheet outcomes; no automatic penalty without lineup-level backtest."}
