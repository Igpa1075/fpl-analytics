"""Leakage-safe GW2-10 validation of a historical-form xPts proxy.

Not a backtest of current GW11 xG model: archived xG/xA and bonus are missing.
Uses only prior fixture results and prior player points/minutes.
"""
import json, math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def main():
 b=json.loads((D/"bootstrap.json").read_text())
 fs=json.loads((D/"fixtures.json").read_text())
 h=json.loads((D/"historical_players_gw1_10.json").read_text())["players"]
 players={int(p["id"]):p for p in b["elements"]}
 fixture_map=defaultdict(list)
 for f in fs:
  if isinstance(f.get("event"),int) and f["event"]<=10 and f.get("finished") and f.get("team_h_score") is not None:
   fixture_map[f["event"]].append(f)
 results=[];rankings=[];coverage=[]
 for gw in range(2,11):
  past=[f for k in range(1,gw) for f in fixture_map[k]]
  if not past:continue
  avg=sum(int(f["team_h_score"])+int(f["team_a_score"]) for f in past)/(2*len(past))
  conceded=defaultdict(list)
  for f in past:
   conceded[int(f["team_h"])].append((int(f["event"]),int(f["team_a_score"])))
   conceded[int(f["team_a"])].append((int(f["event"]),int(f["team_h_score"])))
  candidates=[]
  for pid,p in players.items():
   records=h.get(str(pid))
   if records is None:continue
   prev=[x for x in records if int(x["gw"])<gw]
   if not prev:continue
   target=[x for x in records if int(x["gw"])==gw]
   if not target:continue
   fixture=next((f for f in fixture_map[gw] if int(p["team"]) in (f["team_h"],f["team_a"])),None)
   if not fixture:continue
   opp=int(fixture["team_a"] if int(p["team"])==int(fixture["team_h"]) else fixture["team_h"])
   last=sorted(prev,key=lambda x:int(x["gw"]))[-5:]
   mins=sum(int(x.get("minutes") or 0) for x in prev)
   pts=sum(int(x.get("total_points") or 0) for x in prev)
   recent_mins=sum(int(x.get("minutes") or 0) for x in last)
   recent_pts=sum(int(x.get("total_points") or 0) for x in last)
   # 2.5 points per 90 prior, shrinkage to mitigate short histories
   season_rate=(pts+2.5*450/90)*90/(mins+450)
   recent_rate=(recent_pts+2.5*270/90)*90/(recent_mins+270)
   play_prob=(sum(int(x.get("minutes") or 0)>0 for x in prev)+2)/(len(prev)+3)
   recency_play=(sum(int(x.get("minutes") or 0)>0 for x in last)+2)/(len(last)+3)
   minutes_factor=.5*play_prob+.5*recency_play
   opp_rows=conceded[opp]
   opp_rate=(sum(v for _,v in opp_rows)+4*avg)/(len(opp_rows)+4)
   opp_mult=max(.8,min(1.2,(opp_rate/max(.5,avg))**.35))
   prediction=(.6*season_rate+.4*recent_rate)*minutes_factor*opp_mult
   baseline=season_rate*minutes_factor
   actual=sum(int(x.get("total_points") or 0) for x in target)
   row={"gw":gw,"id":pid,"name":p["web_name"],"position":int(p["element_type"]),
        "predicted":round(prediction,4),"baseline":round(baseline,4),
        "actual":actual,"prior_minutes":mins}
   results.append(row);candidates.append(row)
  # Captain benchmark across same 15 fixed candidate IDs, no future team selections
  selected=[x for x in candidates if x["id"] in (166,411,154,68,236,156,592,115,504,8,31,109)]
  eligible=[x for x in selected if x["position"]!=1 and x["prior_minutes"]>=90]
  if len(eligible)>=3:
   model=max(eligible,key=lambda x:x["predicted"])
   base=max(eligible,key=lambda x:x["baseline"])
   rankings.append({"gw":gw,"eligible":len(eligible),
     "model_captain":model["name"],"model_actual":model["actual"],
     "baseline_captain":base["name"],"baseline_actual":base["actual"]})
  coverage.append({"gw":gw,"scored_players":len(candidates),"eligible_captains":len(eligible)})
 def metrics(key):
  n=len(results)
  return {"n":n,"mae":round(sum(abs(r[key]-r["actual"]) for r in results)/n,3),
          "rmse":round(math.sqrt(sum((r[key]-r["actual"])**2 for r in results)/n),3),
          "bias":round(sum(r[key]-r["actual"] for r in results)/n,3)}
 out={"status":"strictly_lagged_historical_proxy_backtest_NOT_full_xg_model",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "target_gws":list(range(2,11)),
      "model":metrics("predicted"),"simple_prior_form_baseline":metrics("baseline"),
      "captain_comparison":{"rounds":len(rankings),
       "model_actual_captain_points":sum(x["model_actual"] for x in rankings),
       "baseline_actual_captain_points":sum(x["baseline_actual"] for x in rankings),
       "by_gw":rankings},
      "coverage":coverage,
      "limitations":[
        "This is a lagged historical-form proxy, NOT a validation of the GW11 xG/xA full-component model.",
        "Historical player data only contains minutes and total points; archived xG/xA, bonus and defensive actions are missing.",
        "Current player-to-team mappings are used to locate past fixtures and may be incorrect for transferred players; opponent factor therefore unreliable for such players.",
        "Captain comparison uses fixed candidate IDs, not the historical user squad; not a realistic manager backtest.",
        "The historical proxy was not tuned or selected on a holdout; report exploratory results only.",
        "No archived injury or starting XI information; all current-season GW2-10 player records covered by collection are evaluated."
      ]}
 (D/"gw11_xpts_backtest_audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"model":out["model"],"baseline":out["simple_prior_form_baseline"],"captains":out["captain_comparison"]}))
if __name__=="__main__":main()
