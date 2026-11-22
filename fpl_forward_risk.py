"""Forward FPL risk-aware shortlist for the next unstarted gameweek.
Structural estimates, NOT calibrated predictive intervals. No external news score.
Only pre-target fixtures enter team form. Never use target match results.
"""
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

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

def forecast(boot,fixtures,picks=None):
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
    for p in boot["elements"]:
        team=int(p["team"]);pos=int(p["element_type"])
        mins=num(p.get("minutes"))
        if mins<90 or team not in fixture_by_team:continue
        xg90=num(p.get("expected_goals"))*90/max(90,mins)
        xa90=num(p.get("expected_assists"))*90/max(90,mins)
        season_games=max(1,round(mins/90))
        starts=num(p.get("starts"))
        # Approximate availability, not a promise that player will start.
        play=clip((season_games+2)/(season_games+3),.4,.97)
        if p.get("status") not in ("a",None):play*=.65
        expected_minutes=clip(mins/max(1,season_games),20,90)*play
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
            conceded=clip(oppattack*owndef/league*(.93 if home else 1.07),.2,3.5)
            cs=math.exp(-conceded)
            appearance=2*play
            attacking=goal*{1:6,2:6,3:5,4:4}[pos]+assist*3
            cspts=play*cs*{1:4,2:4,3:1,4:0}[pos]
            bonus=clip(num(p.get("bonus"))*90/max(450,mins)*.55,0,1.25)*play
            defensive=clip(num(p.get("defensive_contribution_points"))*90/max(450,mins),0,1.4)*play
            output+=appearance+attacking+cspts+bonus+defensive
            opponents.append(teams.get(opp,str(opp)))
        # Distribution width is illustrative only. Goals are discrete and
        # availability uncertainty is material; no validated CI is claimed.
        conservative=output-0.55*math.sqrt(max(1,output))-1.5*(1-play)
        rows.append({"id":p["id"],"name":p["web_name"],"club":teams.get(team),
                     "position":pos,"opponents":opponents,
                     "expected_points_proxy":round(output,2),
                     "conservative_score":round(conservative,2),
                     "availability_proxy":round(play,2),
                     "attack_trend":round(trend,3),
                     "trend_label":"downturn" if trend<.96 else ("upturn" if trend>1.04 else "neutral"),
                     "status":p.get("status"),"news":p.get("news") or ""})
    rows.sort(key=lambda r:(-r["conservative_score"],-r["expected_points_proxy"]))
    squad=None
    if picks and int(picks.get("entry_history",{}).get("event",0))==target-1:
        ids={int(x["element"]) for x in picks.get("picks",[])}
        squad=[r for r in rows if r["id"] in ids]
        squad.sort(key=lambda r:-r["conservative_score"])
    return {"status":"exploratory_unvalidated_forward_risk_model",
            "gw":target,"created_at_utc":datetime.now(timezone.utc).isoformat(),
            "model_version":"forward-risk-0.1",
            "ranking":rows,"published_prior_gw_squad_candidates":squad,
            "warnings":["Results are structural proxies, not calibrated xPts or confidence intervals.",
                        "Do not treat public prior-gameweek picks as confirmed live squad.",
                        "Recent team trend uses goals scored, not team xG or causal news sentiment.",
                        "No allegation or legal news gets a penalty without validated incremental predictive evidence.",
                        "Conservative score is a heuristic ranking, not a probability or lower confidence bound.",
                        "Predeadline injuries, transfers, real player positions and starting XI need separate checks."]}

def main():
    boot=json.loads((DATA/"bootstrap.json").read_text(encoding="utf-8"))
    fixtures=json.loads((DATA/"fixtures.json").read_text(encoding="utf-8"))
    path=DATA/"picks.json"
    picks=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    result=forecast(boot,fixtures,picks)
    (DATA/"forward_risk_forecast.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"gw":result.get("gw"),
        "top": [(p["name"],p["expected_points_proxy"],p["conservative_score"])
                for p in result.get("ranking",[])[:10]]},ensure_ascii=False))
if __name__=="__main__": main()
