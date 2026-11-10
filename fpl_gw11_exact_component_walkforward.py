"""Walk-forward audit of EXACT GW11 appearance, minutes, bonus and defensive formulas.

All inputs are pre-GW historical match rows. This is not a full xPts backtest.
"""
import json, math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def n(v):
 try:return float(v or 0)
 except (TypeError,ValueError):return 0.
def clamp(v,a,b):return max(a,min(b,v))
def metric(pairs):
 if not pairs:return {"n":0}
 return {"n":len(pairs),"forecast":round(sum(x for x,y in pairs)/len(pairs),3),
  "actual":round(sum(y for x,y in pairs)/len(pairs),3),
  "bias":round(sum(x-y for x,y in pairs)/len(pairs),3),
  "mae":round(sum(abs(x-y) for x,y in pairs)/len(pairs),3)}
def main():
 state=json.loads((D/"historical_players_gw1_10.json").read_text())["players"]
 boot=json.loads((D/"bootstrap.json").read_text())
 pos={str(x["id"]):int(x["element_type"]) for x in boot["elements"]}
 buckets=defaultdict(list)
 missing=defaultdict(int)
 for pid,rows in state.items():
  if pid not in pos:continue
  position=pos[pid]
  for gw in range(2,11):
   past=sorted((r for r in rows if int(r["gw"])<gw),key=lambda r:int(r["gw"]))
   current=[r for r in rows if int(r["gw"])==gw]
   if not past or len(current)!=1:continue
   target=current[0]
   recent=past[-5:]; last3=past[-3:]
   prior_minutes=sum(n(r.get("minutes")) for r in past)
   played=sum(n(r.get("minutes"))>0 for r in past)
   full=sum(n(r.get("minutes"))>=60 for r in past)
   pplay=clamp((played+2+sum(n(r.get("minutes"))>0 for r in recent))/(len(past)+3+len(recent)),.15,.995)
   pfull=clamp((full+2+sum(n(r.get("minutes"))>=60 for r in recent))/(len(past)+3+len(recent)),.1,pplay)
   # Historical deadline injury/status is unavailable: DO NOT apply current bootstrap status.
   expected_minutes=clamp((sum(n(r.get("minutes")) for r in recent)+180)/(len(recent)+2),0,90)*pplay
   actual_min=n(target.get("minutes"))
   appearance=2*pfull+max(0,pplay-pfull)
   actual_app=2 if actual_min>=60 else (1 if actual_min>0 else 0)
   bonus=clamp(.65*sum(n(r.get("bonus")) for r in past)*90/max(450,prior_minutes),0,1.5)*pplay
   defensive=clamp(sum((n(r.get("defensive_contribution_points")) if "defensive_contribution_points" in r else (2 if n(r.get("defensive_contribution"))>=(10 if position==2 else 12) else 0)) for r in past)*90/max(450,prior_minutes),0,2)*pplay
   phase="development" if gw<=7 else "holdout"
   for subset in ("all","regular" if sum(n(r.get("minutes"))>=60 for r in recent)>=3 else "irregular"):
    k=(phase,str(position),subset)
    for component,pred,actual in (
      ("appearance",appearance,actual_app),("minutes",expected_minutes,actual_min),
      ("play_probability",pplay,float(actual_min>0)),
      ("60min_probability",pfull,float(actual_min>=60)),
      ("bonus",bonus,n(target.get("bonus")))):
     buckets[(k,component)].append((pred,actual))
    if "defensive_contribution_points" in target:
     buckets[(k,"defensive")].append((defensive,n(target["defensive_contribution_points"])))
    else:missing["defensive_outcome_missing"]+=1
    if position in (1,2,3) and "clean_sheets" in target:
     missing["clean_sheet_outcomes_present"]+=1
 result={"status":"exact_gw11_component_formulas_walkforward_without_historical_status",
  "created_at_utc":datetime.now(timezone.utc).isoformat(),
  "development_gws":[2,3,4,5,6,7],"holdout_gws":[8,9,10],
  "by_period_position_subset":{phase:{str(p):{subset:{c:metric(buckets[((phase,str(p),subset),c)]) for c in ("appearance","minutes","play_probability","60min_probability","bonus","defensive")}
   for subset in ("all","regular","irregular")} for p in (1,2,3,4)} for phase in ("development","holdout")},
  "coverage_notes":dict(missing),
  "limitations":[
   "Uses exactly the current GW11 historical play/full/minutes/bonus/defensive formula, with all feature rows strictly before each GW.",
   "Historical pre-deadline injury statuses unavailable, so current status adjustment deliberately omitted.",
   "Regular means >=3 of prior 5 recorded matches with 60+ minutes; prior history may include unplayed rows.",
   "Not a full GW11 xPts backtest: opponent-adjusted goals, assists, CS, cards and saves are excluded.",
   "Defensive outcome evaluated only if an explicit points field exists; no guessed actual points.",
   "Historical GW team transfers and double gameweeks require additional handling; multiple target rows excluded.",
   "No coefficients are tuned; holdout is diagnostic only."
  ]}
 (D/"gw11_exact_component_walkforward.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"holdout_regular":{p:result["by_period_position_subset"]["holdout"][p]["regular"] for p in ("1","2","3","4")}}))
if __name__=="__main__":main()
