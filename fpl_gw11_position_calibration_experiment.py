"""Position calibration experiment: fit GW2-7, evaluate untouched GW8-10.

Exact GW11 formulas for appearance/minutes/bonus (historical status unavailable).
Experimental only: does not modify production GW11 forecasts.
"""
import json,math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def n(x):
 try:return float(x or 0)
 except (TypeError,ValueError):return 0.
def clip(x,a,b):return max(a,min(b,x))
def score(rows,base,new,actual):
 if not rows:return {"n":0}
 def calc(key):
  errors=[r[key]-r[actual] for r in rows]
  return {"mae":round(sum(abs(e) for e in errors)/len(errors),4),
   "rmse":round(math.sqrt(sum(e*e for e in errors)/len(errors)),4),
   "bias":round(sum(errors)/len(errors),4)}
 return {"n":len(rows),"baseline":calc(base),"candidate":calc(new),
  "delta_mae":round(calc(new)["mae"]-calc(base)["mae"],4)}
def main():
 state=json.loads((D/"historical_players_gw1_10.json").read_text())["players"]
 boot=json.loads((D/"bootstrap.json").read_text())
 positions={str(x["id"]):int(x["element_type"]) for x in boot["elements"]}
 rows=[]
 for pid,history in state.items():
  if pid not in positions:continue
  pos=positions[pid]
  for gw in range(2,11):
   prior=sorted((r for r in history if int(r["gw"])<gw),key=lambda r:int(r["gw"]))
   target=[r for r in history if int(r["gw"])==gw]
   if not prior or len(target)!=1:continue
   recent=prior[-5:]
   mins=sum(n(r.get("minutes")) for r in prior)
   pplay=clip((sum(n(r.get("minutes"))>0 for r in prior)+2+sum(n(r.get("minutes"))>0 for r in recent))/(len(prior)+3+len(recent)),.15,.995)
   pfull=clip((sum(n(r.get("minutes"))>=60 for r in prior)+2+sum(n(r.get("minutes"))>=60 for r in recent))/(len(prior)+3+len(recent)),.1,pplay)
   predicted_min=clip((sum(n(r.get("minutes")) for r in recent)+180)/(len(recent)+2),0,90)*pplay
   predicted_bonus=clip(.65*sum(n(r.get("bonus")) for r in prior)*90/max(450,mins),0,1.5)*pplay
   actual_min=n(target[0].get("minutes"))
   actual_bonus=n(target[0].get("bonus"))
   regular=sum(n(r.get("minutes"))>=60 for r in recent)>=3
   rows.append({"gw":gw,"position":pos,"regular":regular,"minutes_base":predicted_min,
    "bonus_base":predicted_bonus,"minutes_actual":actual_min,"bonus_actual":actual_bonus,
    "appearance_base":2*pfull+max(0,pplay-pfull),
    "appearance_actual":2 if actual_min>=60 else (1 if actual_min>0 else 0)})
 development=[r for r in rows if r["gw"]<=7]
 holdout=[r for r in rows if r["gw"]>=8]
 params={}
 for pos in (1,2,3,4):
  params[str(pos)]={}
  for regular in (False,True):
   params[str(pos)][str(regular)]={}
   group=[r for r in development if r["position"]==pos and r["regular"]==regular]
   # Shrink fitted ratios toward 1 to limit small-sample instability.
   for component in ("minutes","bonus"):
    forecast=sum(r[component+"_base"] for r in group)
    actual=sum(r[component+"_actual"] for r in group)
    ratio=actual/max(1e-8,forecast)
    weight=len(group)/(len(group)+100)
    shrink=1+weight*(ratio-1)
    lo,hi=(.8,1.2) if component=="minutes" else (.65,1.8)
    params[str(pos)][str(regular)][component]=round(clip(shrink,lo,hi),5)
   params[str(pos)][str(regular)]["n"]=len(group)
 for r in rows:
  p=params[str(r["position"])][str(r["regular"])]
  r["minutes_candidate"]=clip(r["minutes_base"]*p["minutes"],0,90)
  r["bonus_candidate"]=clip(r["bonus_base"]*p["bonus"],0,3)
 result={"status":"development_fitted_holdout_evaluation_experimental_not_production",
  "created_at_utc":datetime.now(timezone.utc).isoformat(),
  "fit_gws":[2,3,4,5,6,7],"untouched_holdout_gws":[8,9,10],
  "parameters":params,
  "holdout":{component:{"all":score(holdout,component+"_base",component+"_candidate",component+"_actual"),
    "by_position":{str(pos):{"all":score([r for r in holdout if r["position"]==pos],component+"_base",component+"_candidate",component+"_actual"),
      "regular":score([r for r in holdout if r["position"]==pos and r["regular"]],component+"_base",component+"_candidate",component+"_actual")}
      for pos in (1,2,3,4)}} for component in ("minutes","bonus")},
  "development":{component:score(development,component+"_base",component+"_candidate",component+"_actual") for component in ("minutes","bonus")},
  "coverage":{"development":len(development),"holdout":len(holdout)},
  "limitations":[
    "Calibrates only minutes and bonus component means, not total xPts or the probability of >=60 minutes.",
    "Parameters estimated exclusively on GW2-7 and evaluated on GW8-10; no holdout fitting.",
    "Regular defined by >=3 prior five recorded 60+ minute games; historical deadline statuses unavailable.",
    "Bonuses and minutes evaluated on identical historical player-gameweek rows.",
    "A gain in component accuracy does not establish a gain in total FPL points or captain choice.",
    "Production GW11 forecast remains unchanged pending full-model validation."
  ]}
 (D/"gw11_position_calibration_experiment.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"parameters":params,"holdout":{k:v["all"] for k,v in result["holdout"].items()}}))
if __name__=="__main__":main()
