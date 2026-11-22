"""Forward FPL risk-aware shortlist for the next unstarted gameweek.
Structural estimates, NOT calibrated predictive intervals. No external news score.
Only pre-target fixtures enter team form. Never use target match results.
"""
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from fpl_defensive_risk import defensive_form, defensive_availability, squad_defensive_concentration

DATA=Path(__file__).resolve().parent/"data"
def clip(x,a,b): return max(a,min(b,x))
def num(x):
    try: return float(x or 0)
    except (TypeError,ValueError): return 0.0

def team_form(fixtures, target):
    past=[f for f in fixtures if isinstance(f.get("event"),int) and f["event"]<target
          and f.get("finished") and f.get("team_h_score") is not None and f.get("team_a_score") is not None]
    league=(sum(num(f["team_h_score"])+num(f["team_a_score"]) for f in past)/(2*len(past))) if past else 1.4
    league=max(.4,league)
    gf=defaultdict(list);ga=defaultdict(list);results=defaultdict(list)
    for f in sorted(past,key=lambda z:z["event"]):
        h,a=int(f["team_h"]),int(f["team_a"])
        hg,ag=num(f["team_h_score"]),num(f["team_a_score"])
        gf[h].append(hg);gf[a].append(ag)
        ga[h].append(ag);ga[a].append(hg)
        results[h].append((hg,ag));results[a].append((ag,hg))
    def rate(items,prior=4):
        return (sum(items)+prior*league)/(len(items)+prior)
    info={}
    for team in set(gf)|set(ga):
        season=rate(gf[team])
        recent=rate(gf[team][-5:],prior=3)
        # Recency is measured relative to a team's own historical baseline.
        # It is shrunk and bounded to avoid retrofitted crisis penalties.
        trend=clip((recent/max(.4,season))**.45,.83,1.13)
        info[team]={"attack":season,"recent_attack":recent,"defense":rate(ga[team]),
                    "recent_defense":rate(ga[team][-5:],prior=3),
                    "attack_trend":trend,"last5_results":results[team][-5:],
                    "games":len(gf[team])}
    return league,info

def participation(player,recent_rows=None):
    """Minutes-based rotation proxy: 60+ is NOT a confirmed historical start."""
    season_mins=num(player.get("minutes"))
    season_appearances=num(player.get("appearances"))
    season_appearances=max(season_appearances,round(season_mins/85),1)
    season_play=clip((season_appearances+2)/(season_appearances+3),.4,.97)
    baseline_min=clip(season_mins/max(1,season_appearances),15,90)
    rows=list(recent_rows or [])
    if rows:
        values=[clip(num(x.get("minutes")),0,120) for x in rows]
        played=sum(v>0 for v in values)
        recent_play=(played+2)/(len(values)+3)
        play=clip(.4*season_play+.6*recent_play,.1,.97)
        recent_avg=sum(values)/max(1,played) if played else baseline_min
        conditional_minutes=.45*baseline_min+.55*recent_avg
        sixty_ratio=(sum(v>=60 for v in values)+1)/(len(values)+2)
        cameo_ratio=sum(0<v<60 for v in values)/len(values)
    else:
        play=season_play
        conditional_minutes=baseline_min
        sixty_ratio=None
        cameo_ratio=None
    if player.get("status") not in ("a",None): play*=.65
    return {"play":clip(play,.03,.99),
            "conditional_minutes":clip(conditional_minutes,10,90),
            "expected_minutes":clip(play*conditional_minutes,0,90),
            "sixty_plus_rate":sixty_ratio,
            "cameo_rate":cameo_ratio,
            "recent_sample":len(rows)}

def forecast(boot,fixtures,picks=None,recent_minutes=None):
    events=boot.get("events",[])
    # Upcoming rather than current: no in-progress-match results in a projection.
    target=next((int(e["id"]) for e in events if e.get("is_next")),None)
    if target is None:
        unfinished=[int(e["id"]) for e in events if not e.get("finished") and not e.get("is_current")]
        if not unfinished:return {"status":"no_upcoming_gameweek"}
        target=min(unfinished)
    league,form=team_form(fixtures,target)
    fixture_by_team={}
    for f in fixtures:
        if f.get("event")!=target:continue
        fixture_by_team.setdefault(int(f["team_h"]),[]).append((int(f["team_a"]),True))
        fixture_by_team.setdefault(int(f["team_a"]),[]).append((int(f["team_h"]),False))
    teams={int(t["id"]):t["short_name"] for t in boot["teams"]}
    rows=[]
    defensive_flags={int(t["id"]):defensive_availability(boot["elements"],int(t["id"])) for t in boot["teams"]}
    recent_minutes=recent_minutes or {}
    minute_weeks=[int(g) for g in recent_minutes.get("completed_gws",[]) if int(g)<target]
    # Ensure the archive is current for the last five completed GWs; incomplete
    # or stale archives are not treated as proof of rotation.
    valid_archive=(len(minute_weeks)>0 and minute_weeks==recent_minutes.get("completed_gws",[]))
    player_minutes=recent_minutes.get("players",{}) if valid_archive else {}
    prominent=defaultdict(list)
    for p in boot["elements"]:
        if num(p.get("minutes"))>=450:
            prominent[int(p["team"])].append(p)
    for club in prominent:
        prominent[club].sort(key=lambda p:-num(p.get("minutes")))
    for p in boot["elements"]:
        team=int(p["team"]);pos=int(p["element_type"])
        mins=num(p.get("minutes"))
        if mins<90 or team not in fixture_by_team:continue
        xg90=num(p.get("expected_goals"))*90/max(90,mins)
        xa90=num(p.get("expected_assists"))*90/max(90,mins)
        history=[x for x in player_minutes.get(str(p["id"]),[])
                 if int(x.get("gw",0)) in minute_weeks]
        # Require complete archive coverage for each player; absence of an
        # element is not evidence of a zero-minute game.
        if len(history)!=len(minute_weeks): history=[]
        usage=participation(p,history)
        play=usage["play"]
        expected_minutes=usage["expected_minutes"]
        unavailable_peers=[other for other in prominent.get(team,[])[:6]
                           if int(other["id"])!=int(p["id"])
                           and other.get("status") not in ("a",None)]
        teammate_penalty=clip(1-.025*len(unavailable_peers),.92,1.)
        own=form.get(team,{})
        trend=own.get("attack_trend",1.)
        output=0.
        opponents=[]
        for opp,home in fixture_by_team[team]:
            other=form.get(opp,{})
            oppdef=other.get("defense",league)
            clubattack=own.get("attack",league)
            # Avoid counting the trend twice: season strength x recent shift.
            factor=clip((oppdef/league)**.45*(clubattack/league)**.20,.75,1.35)
            factor*=trend*(1.05 if home else .95)
            goal=xg90*expected_minutes/90*factor
            assist=xa90*expected_minutes/90*factor
            oppattack=other.get("attack",league)*other.get("attack_trend",1.)
            owndef=own.get("defense",league)
            defense_trend=defensive_form(own,league)
            conceded=clip(oppattack*owndef/league*defense_trend*(.93 if home else 1.07),.2,3.5)
            cs=math.exp(-conceded)
            appearance=play+(expected_minutes/max(1,usage["conditional_minutes"]))*clip(
                (usage["conditional_minutes"]-30)/30,0,1)
            attacking=(goal*{1:6,2:6,3:5,4:4}[pos]+assist*3)*teammate_penalty
            # Clean-sheet points require playing >=60 minutes. Avoid granting
            # full CS credit to a likely cameo or a player who may not feature.
            sixty=usage["sixty_plus_rate"]
            eligible60=(play*clip((usage["conditional_minutes"]-30)/50,0,1)
                        if sixty is None else min(play,sixty))
            cspts=eligible60*cs*{1:4,2:4,3:1,4:0}[pos]
            bonus=clip(num(p.get("bonus"))*90/max(450,mins)*.55,0,1.25)*play
            defensive=clip(num(p.get("defensive_contribution_points"))*90/max(450,mins),0,1.4)*play
            output+=appearance+attacking+cspts+bonus+defensive
            opponents.append(teams.get(opp,str(opp)))
        # Distribution width is illustrative only. Goals are discrete and
        # availability uncertainty is material; no validated CI is claimed.
        rotation_uncertainty=(usage["cameo_rate"] or 0)*.7
        conservative=output-0.55*math.sqrt(max(1,output))-1.5*(1-play)-rotation_uncertainty
        rows.append({"id":p["id"],"name":p["web_name"],"club":teams.get(team),
                     "position":pos,"opponents":opponents,
                     "expected_points_proxy":round(output,2),
                     "conservative_score":round(conservative,2),
                     "availability_proxy":round(play,2),
                     "expected_minutes":round(expected_minutes,1),
                     "sixty_plus_minute_rate_proxy":None if usage["sixty_plus_rate"] is None else round(usage["sixty_plus_rate"],2),
                     "cameo_rate":None if usage["cameo_rate"] is None else round(usage["cameo_rate"],2),
                     "recent_minutes_sample":usage["recent_sample"],
                     "key_teammates_unavailable":len(unavailable_peers),
                     "teammate_attack_factor_experimental":round(teammate_penalty,3),
                     "attack_trend":round(trend,3),
                     "defense_trend":round(defensive_form(own,league),3),
                     "defensive_absence_flags":defensive_flags[team],
                     "trend_label":"downturn" if trend<.96 else ("upturn" if trend>1.04 else "neutral"),
                     "status":p.get("status"),"news":p.get("news") or ""})
    rows.sort(key=lambda r:(-r["conservative_score"],-r["expected_points_proxy"]))
    squad=None
    if picks and int(picks.get("entry_history",{}).get("event",0))==target-1:
        ids={int(x["element"]) for x in picks.get("picks",[])}
        squad=[r for r in rows if r["id"] in ids]
        squad.sort(key=lambda r:-r["conservative_score"])
    lookup={int(p["id"]):p for p in boot["elements"]}
    concentration=squad_defensive_concentration(picks,lookup)
    return {"status":"exploratory_unvalidated_forward_risk_model",
            "gw":target,"created_at_utc":datetime.now(timezone.utc).isoformat(),
            "model_version":"forward-risk-0.3",
            "defensive_concentration":concentration,
            "recent_minutes_completed_gws":minute_weeks if valid_archive else [],
            "ranking":rows,"published_prior_gw_squad_candidates":squad,
            "warnings":["Results are structural proxies, not calibrated xPts or confidence intervals.",
                        "Do not treat public prior-gameweek picks as confirmed live squad.",
                        "Recent team trend uses goals scored, not team xG or causal news sentiment.",
                        "No allegation or legal news gets a penalty without validated incremental predictive evidence.",
                        "Conservative score is a heuristic ranking, not a probability or lower confidence bound.",
                        "Minutes-based 60+ proxy is not an actual starting lineup; substitutes and injuries are confounded.",
                        "Teammate absence factor is experimental, based on FPL status of six season-minute leaders, not validated causal impact.",
                        "Key goalkeeper and defender injuries are flags only; no unvalidated defensive-absence multiplier.",
                        "Defensive form uses goals conceded, not xGA, and is not calibrated.",
                        "Same-club defender concentration is reported, not penalized automatically.",
                        "Predeadline injuries, transfers, real player positions and starting XI need separate checks."]}

def main():
    boot=json.loads((DATA/"bootstrap.json").read_text(encoding="utf-8"))
    fixtures=json.loads((DATA/"fixtures.json").read_text(encoding="utf-8"))
    path=DATA/"picks.json"
    picks=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    recent_path=DATA/"recent_live_minutes.json"
    recent=json.loads(recent_path.read_text(encoding="utf-8")) if recent_path.exists() else None
    result=forecast(boot,fixtures,picks,recent)
    (DATA/"forward_risk_forecast.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"gw":result.get("gw"),
        "top": [(p["name"],p["expected_points_proxy"],p["conservative_score"])
                for p in result.get("ranking",[])[:10]]},ensure_ascii=False))
if __name__=="__main__": main()
