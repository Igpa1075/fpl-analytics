"""Historical full-component FPL xPts walk-forward (GW2-10).

Every feature is built from matches BEFORE the forecast GW. No current bootstrap
season totals, current club assignments, or future injury statuses are used.
This is a historical reconstruction of GW11 structural logic, not byte-identical
because historical deadline statuses are unavailable.
"""
import json,math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def n(v):
 try:return float(v or 0)
 except (TypeError,ValueError):return 0.
def clip(x,a,b):return max(a,min(b,x))
def metrics(rows,key):
 if not rows:return {"n":0}
 e=[r[key]-r["actual"] for r in rows]
 return {"n":len(e),"mae":round(sum(abs(x) for x in e)/len(e),3),
         "rmse":round(math.sqrt(sum(x*x for x in e)/len(e)),3),
         "bias":round(sum(e)/len(e),3)}
def main():
 players=json.loads((D/"bootstrap.json").read_text())["elements"]
 players={int(p["id"]):p for p in players}
 history=json.loads((D/"historical_players_gw1_10.json").read_text())["players"]
 fixtures=json.loads((D/"fixtures.json").read_text())
 predictions=[]
 candidates={250,115,504,8,427,156,154,236,68,411,166,109,592,31,599}
 decisions=[]
 for gw in range(2,11):
  prior_f=[f for f in fixtures if isinstance(f.get("event"),int) and f["event"]<gw and f.get("finished") and f.get("team_h_score") is not None]
  if not prior_f:continue
  league=sum(n(f["team_h_score"])+n(f["team_a_score"]) for f in prior_f)/(2*len(prior_f))
  gf=defaultdict(list);ga=defaultdict(list)
  for f in prior_f:
   h,a=int(f["team_h"]),int(f["team_a"])
   gf[h].append((f["event"],n(f["team_h_score"])))
   gf[a].append((f["event"],n(f["team_a_score"])))
   ga[h].append((f["event"],n(f["team_a_score"])))
   ga[a].append((f["event"],n(f["team_h_score"])))
  def shrink(seq,recency=False):
   if recency:seq=[(week,v) for week,v in seq if week>=gw-5]
   return (sum(v for _,v in seq)+4*league)/(len(seq)+4)
  gw_rows=[]
  for pid_s,rows in history.items():
   pid=int(pid_s)
   if pid not in players:continue
   prior=sorted([r for r in rows if int(r["gw"])<gw],key=lambda r:int(r["gw"]))
   target=[r for r in rows if int(r["gw"])==gw]
   if not prior or len(target)!=1:continue
   target=target[0]
   if any("expected_goals" not in r or "expected_assists" not in r for r in prior):continue
   if sum(n(r.get("minutes")) for r in prior)<90:continue
   # Opponent and historical team inferred from fixture schedule, never current team.
   opponent=int(target.get("opponent_team") or 0)
   was_home=target.get("was_home")
   if not opponent or not isinstance(was_home,bool):continue
   current_fixture=next((f for f in fixtures if f.get("event")==gw and
    (int(f["team_a"] if was_home else f["team_h"])==opponent)),None)
   if not current_fixture:continue
   club=int(current_fixture["team_h"] if was_home else current_fixture["team_a"])
   pos=int(players[pid]["element_type"])
   recent=prior[-5:]
   total_min=sum(n(r.get("minutes")) for r in prior)
   recent_min=sum(n(r.get("minutes")) for r in recent)
   played=sum(n(r.get("minutes"))>0 for r in prior)
   starts=sum(n(r.get("minutes"))>=60 for r in prior)
   pplay=clip((played+2+sum(n(r.get("minutes"))>0 for r in recent))/(len(prior)+3+len(recent)),.15,.995)
   pfull=clip((starts+2+sum(n(r.get("minutes"))>=60 for r in recent))/(len(prior)+3+len(recent)),.1,pplay)
   exp_min=clip((recent_min+180)/(len(recent)+2),0,90)*pplay
   season_xg90=sum(n(r.get("expected_goals")) for r in prior)*90/max(90,total_min)
   season_xa90=sum(n(r.get("expected_assists")) for r in prior)*90/max(90,total_min)
   recent_xg90=sum(n(r.get("expected_goals")) for r in recent)*90/max(90,recent_min)
   recent_xa90=sum(n(r.get("expected_assists")) for r in recent)*90/max(90,recent_min)
   xg90=.7*season_xg90+.3*recent_xg90
   xa90=.7*season_xa90+.3*recent_xa90
   opp_def=.65*shrink(ga[opponent])+.35*shrink(ga[opponent],True)
   attack=clip((opp_def/max(.1,league))**.5*(shrink(gf[club])/max(.1,league))**.25,.72,1.4)
   attack*=1.06 if was_home else .94
   goal=xg90*exp_min/90*attack*{1:6,2:6,3:5,4:4}[pos]
   assist=xa90*exp_min/90*attack*3
   opp_attack=.65*shrink(gf[opponent])+.35*shrink(gf[opponent],True)
   lam=clip(opp_attack*shrink(ga[club])/max(.4,league)*(.92 if was_home else 1.08),.15,3.5)
   clean_sheet={1:4,2:4,3:1,4:0}[pos]*pfull*math.exp(-lam)
   conceded=-pfull*sum((k//2)*math.exp(-lam)*lam**k/math.factorial(k) for k in range(20)) if pos in (1,2) else 0
   bonus=clip(.65*sum(n(r.get("bonus")) for r in prior)*90/max(450,total_min),0,1.5)*pplay
   defensive=clip(sum((n(r.get("defensive_contribution_points")) if "defensive_contribution_points" in r else
      (2 if n(r.get("defensive_contribution"))>=(10 if pos==2 else 12) else 0))
      for r in prior)*90/max(450,total_min),0,2)*pplay
   saves=(sum(n(r.get("saves")) for r in prior)*90/max(450,total_min)/3)*pplay if pos==1 else 0
   cards=sum(-n(r.get("yellow_cards"))-3*n(r.get("red_cards"))-2*n(r.get("own_goals"))-
       2*n(r.get("penalties_missed"))+5*n(r.get("penalties_saved")) for r in prior)/len(prior)*pplay
   appearance=2*pfull+max(0,pplay-pfull)
   forecast=appearance+goal+assist+clean_sheet+conceded+bonus+defensive+saves+cards
   baseline=(sum(n(r.get("total_points")) for r in prior)+12.5)/(len(prior)+5)*pplay
   row={"gw":gw,"id":pid,"name":players[pid]["web_name"],"position":pos,"club":club,
        "forecast":round(forecast,4),"baseline":round(baseline,4),
        "actual":sum(n(r.get("total_points")) for r in [target]),
        "components":{"appearance":round(appearance,3),"goals":round(goal,3),
          "assists":round(assist,3),"clean_sheet":round(clean_sheet,3),
          "conceded":round(conceded,3),"bonus":round(bonus,3),
          "defensive":round(defensive,3),"saves":round(saves,3),"other":round(cards,3)}}
   predictions.append(row);gw_rows.append(row)
  eligible=[r for r in gw_rows if r["id"] in candidates and r["position"]!=1]
  if len(eligible)>=3:
   top=max(eligible,key=lambda r:r["forecast"])
   base=max(eligible,key=lambda r:r["baseline"])
   haaland=next((r for r in eligible if r["id"]==411),None)
   decisions.append({"gw":gw,"candidate_count":len(eligible),
      "model":{"id":top["id"],"name":top["name"],"actual":top["actual"]},
      "baseline":{"id":base["id"],"name":base["name"],"actual":base["actual"]},
      "always_haaland":None if haaland is None else haaland["actual"]})
 def group_stats(rows):
  return {"model":metrics(rows,"forecast"),"baseline":metrics(rows,"baseline"),
    "by_position":{str(p):{"model":metrics([r for r in rows if r["position"]==p],"forecast"),
      "baseline":metrics([r for r in rows if r["position"]==p],"baseline")} for p in (1,2,3,4)}}
 holdout=[r for r in predictions if r["gw"]>=8]
 dev=[r for r in predictions if r["gw"]<=7]
 holdout_decisions=[d for d in decisions if d["gw"]>=8 and d["always_haaland"] is not None]
 result={"status":"historical_full_component_reconstruction_not_exact_deadline_snapshot",
  "created_at_utc":datetime.now(timezone.utc).isoformat(),
  "development_gws":[2,3,4,5,6,7],"holdout_gws":[8,9,10],
  "development":group_stats(dev),"holdout":group_stats(holdout),
  "overall":group_stats(predictions),
  "captain_holdout":{"rounds":len(holdout_decisions),
   "model_actual":sum(d["model"]["actual"] for d in holdout_decisions),
   "baseline_actual":sum(d["baseline"]["actual"] for d in holdout_decisions),
   "always_haaland_actual":sum(d["always_haaland"] for d in holdout_decisions),
   "by_gw":holdout_decisions},
  "coverage_by_gw":{str(gw):sum(r["gw"]==gw for r in predictions) for gw in range(2,11)},
  "limitations":[
    "Reconstructs the GW11 component formulas with strictly lagged xG/xA, team results, minutes and bonus.",
    "Historical deadline injury statuses and actual user historical squads unavailable.",
    "Captain comparison uses fixed current squad IDs, NOT actual historical eligibility or transfers.",
    "Historical FPL bootstrap positions assumed stable; club derived from historical fixture, not current club.",
    "Only one archived player row per GW is supported; double GW and ambiguous fixtures excluded.",
    "Baseline is lagged points with shrinkage; neither model is trained on the holdout.",
    "Not a live GW11 lineup/transfer optimization and not proof of higher season points."
  ]}
 (D/"gw11_full_xpts_walkforward.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"development":result["development"]["model"],"holdout":result["holdout"],
  "captain_holdout":result["captain_holdout"],"coverage":result["coverage_by_gw"]}))
if __name__=="__main__":main()
