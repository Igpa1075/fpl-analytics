"""GW11 defender head-to-head with position-aware forecasts and honest FT trade-off.

Separates appearance, defensive returns and attacking/bonus residuals.
Opponent clean-sheet probability is a shrunk historical estimate, not a
calibrated betting market probability. Do not treat as guaranteed points.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D

GWS=(11,12,13)
IDS=(8,112,31,304)
def main():
    boot=json.loads((D/"bootstrap.json").read_text(encoding="utf-8"))
    fixtures=json.loads((D/"fixtures.json").read_text(encoding="utf-8"))
    histories=json.loads((D/"historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    teams={int(t["id"]):t["name"] for t in boot["teams"]}
    players={int(p["id"]):p for p in boot["elements"]}
    by_gw=defaultdict(lambda:defaultdict(list))
    conceded=defaultdict(list)
    scored=defaultdict(list)
    for f in fixtures:
        h,a=int(f["team_h"]),int(f["team_a"])
        if f.get("event") in GWS:
            by_gw[f["event"]][h].append((a,True,int(f["team_h_difficulty"])))
            by_gw[f["event"]][a].append((h,False,int(f["team_a_difficulty"])))
        if f.get("finished") and isinstance(f.get("event"),int) and f["event"]<=10 and f.get("team_h_score") is not None and f.get("team_a_score") is not None:
            hs,as_=int(f["team_h_score"]),int(f["team_a_score"])
            conceded[h].append(as_);conceded[a].append(hs)
            scored[h].append(hs);scored[a].append(as_)
    league_attack=sum(sum(v) for v in scored.values())/max(1,sum(len(v) for v in scored.values()))
    league_def=sum(sum(v) for v in conceded.values())/max(1,sum(len(v) for v in conceded.values()))
    result={}
    for pid in IDS:
        p=players[pid]
        rows=[r for r in histories[str(pid)] if int(r["gw"])<=10]
        # GW1-10 for robust appearance, GW6-10 for residual recent returns
        mins=[int(r.get("minutes") or 0) for r in rows]
        recent=[r for r in rows if 6<=int(r["gw"])<=10]
        recent_pts=sum(int(r.get("total_points") or 0) for r in recent)
        recent_mins=sum(int(r.get("minutes") or 0) for r in recent)
        appearance=min(1.,(sum(mins)+180)/(max(1,len(rows))*90+180))
        starts=sum(m>=60 for m in mins)
        start_rate=(starts+2)/(max(1,len(rows))+3)
        # Expected appearance points: ~2 for 60+ min, less for cameos.
        app_points=2*start_rate + .5*max(0,appearance-start_rate)
        club=int(p["team"])
        # Shrunk attack/defence rates; Poisson P(0) for opponent scoring.
        defence=(sum(conceded[club])+4*league_def)/(len(conceded[club])+4)
        fixtures_out=[]
        total=0.
        for gw in GWS:
            gw_points=0.
            for opp,home,difficulty in by_gw[gw].get(club,[]):
                opp_attack=(sum(scored[opp])+4*league_attack)/(len(scored[opp])+4)
                lam=max(.2,min(3.5,opp_attack*defence/max(.4,league_def)*(.92 if home else 1.08)))
                import math
                cs_prob=math.exp(-lam)
                # Defender clean sheet +4 conditional on 60+ minutes
                cs_points=4*cs_prob*start_rate
                # 5 GW residual points are deliberately shrunk and capped.
                residual=max(-.5,min(2.0,recent_pts/max(1,len(recent))-app_points))
                residual*=.5
                gw_points+=app_points+cs_points+residual
                fixtures_out.append({"gw":gw,"opponent":teams[opp],"home":home,
                                     "difficulty":difficulty,
                                     "estimated_clean_sheet_probability":round(cs_prob,3),
                                     "proxy_points":round(app_points+cs_points+residual,3)})
            total+=gw_points
        result[str(pid)]={"name":p["web_name"],"team":teams[club],
                          "market_price_tenths":p["now_cost"],
                          "status":p.get("status"),"news":p.get("news"),
                          "chance_next_round":p.get("chance_of_playing_next_round"),
                          "historical_60min_appearances":starts,
                          "historical_matches":len(rows),
                          "season_minutes":sum(mins),
                          "recent_five_gw_points":recent_pts,
                          "three_gw_proxy":round(total,3),
                          "fixtures":fixtures_out}
    diff=round(result["112"]["three_gw_proxy"]-result["8"]["three_gw_proxy"],3)
    report={
      "status":"defender_comparison_exploratory_uncalibrated",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "comparison":"Calafiori 8 versus Van Hecke 112",
      "players":result,
      "van_hecke_minus_calafiori_three_gw_proxy":diff,
      "screenshot_confirmed_pair_feasible":True,
      "screenshot_confirmed_bank_after_both_tenths":8,
      "screenshot_confirmed_no_points_hit":True,
      "second_free_transfer_opportunity_cost":"not estimable from available data; recommend second transfer only with a meaningful, robust forecast advantage",
      "recommendation_rule":"Prefer keeping second FT unless defender advantage is material and robust across methods and player availability confirmed near deadline.",
      "limitations":[
        "Poisson clean-sheet probabilities are crude proxies, not validated or calibrated.",
        "Player starts are inferred from historical 60+ minutes, not actual team news.",
        "Defensive attacking/bonus residual is a shrunk recent-points proxy.",
        "Defender clean sheet model does not incorporate lineup, xG, injuries, or bookmaker odds.",
        "No authenticated live team or future price data.",
        "GW11 deadline 21 Nov; check status near deadline before submitting."
      ]}
    path=D/"gw11_defender_head_to_head.json"
    if path.exists():
        print("Defender head-to-head already frozen")
        return
    with path.open("x",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2);f.write("\n")
    print(json.dumps({"difference":diff,"names":{k:v["name"] for k,v in result.items()}}))
if __name__=="__main__":main()
