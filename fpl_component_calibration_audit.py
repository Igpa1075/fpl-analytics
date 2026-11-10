"""Audit xPts components using pre-GW history; no tuning on holdout."""
import json,math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def num(x):
 try:return float(x or 0)
 except (ValueError,TypeError):return 0.
def stat(a):
 if not a:return {"n":0}
 return {"n":len(a),"predicted_mean":round(sum(x[0] for x in a)/len(a),3),
         "actual_mean":round(sum(x[1] for x in a)/len(a),3),
         "bias":round(sum(x[0]-x[1] for x in a)/len(a),3),
         "mae":round(sum(abs(x[0]-x[1]) for x in a)/len(a),3)}
def main():
 state=json.loads((D/"historical_players_gw1_10.json").read_text())
 boot=json.loads((D/"bootstrap.json").read_text())
 positions={str(p["id"]):int(p["element_type"]) for p in boot["elements"]}
 metrics=defaultdict(list);coverage=defaultdict(int)
 for pid,rows in state["players"].items():
  if pid not in positions:continue
  pos=positions[pid]
  for gw in range(2,11):
   prior=[r for r in rows if int(r["gw"])<gw]
   target=[r for r in rows if int(r["gw"])==gw]
   if not prior or not target:continue
   if not all("bonus" in r and "minutes" in r for r in prior+target):continue
   recent=sorted(prior,key=lambda r:int(r["gw"]))[-5:]
   n=len(prior)
   played=sum(num(r.get("minutes"))>0 for r in prior)
   played_recent=sum(num(r.get("minutes"))>0 for r in recent)
   starts=sum(num(r.get("minutes"))>=60 for r in prior)
   starts_recent=sum(num(r.get("minutes"))>=60 for r in recent)
   pplay=min(.995,max(.15,(played+2+played_recent)/(n+3+len(recent))))
   pfull=min(pplay,max(.1,(starts+2+starts_recent)/(n+3+len(recent))))
   exp_min=min(90,(sum(num(r.get("minutes")) for r in recent)+180)/(len(recent)+2))*pplay
   actual_min=sum(num(r.get("minutes")) for r in target)
   actual_play=float(actual_min>0)
   actual_full=float(actual_min>=60)
   if len(target)!=1:continue # avoid double GW ambiguity
   phase="development" if gw<=7 else "holdout"
   key=(phase,str(pos))
   metrics[(key,"appearance")].append((pfull*2+max(0,pplay-pfull),2*actual_full+(actual_play-actual_full)))
   metrics[(key,"minutes")].append((exp_min,actual_min))
   metrics[(key,"play_probability")].append((pplay,actual_play))
   metrics[(key,"60min_probability")].append((pfull,actual_full))
   mins=sum(num(r.get("minutes")) for r in prior)
   bonus_per90=sum(num(r.get("bonus")) for r in prior)*90/max(450,mins)
   bonus=min(1.5,max(0,.65*bonus_per90))*pplay
   metrics[(key,"bonus")].append((bonus,num(target[0].get("bonus"))))
   if pos in (1,2,3):
    # Real clean-sheet eligibility requires 60+ and FPL clean_sheets match field
    if "clean_sheets" in target[0]:
     coverage["clean_sheet_outcomes"]+=1
     # Historical CS prior, shrunk with 4 match prior at .28
     prior_cs=sum(num(r.get("clean_sheets")) for r in prior)
     cs_prob=(prior_cs+4*.28)/(len(prior)+4)*pfull
     metrics[(key,"clean_sheet_eligibility")].append((cs_prob,num(target[0].get("clean_sheets"))))
   coverage["total"]+=1
 out={"status":"pre_gw_component_calibration_audit_no_retraining",
      "created_at_utc":datetime.now(timezone.utc).isoformat(),
      "coverage":dict(coverage),
      "development_gws":[2,3,4,5,6,7],"holdout_gws":[8,9,10],
      "by_period_position":{phase:{str(pos):{component:stat(metrics.get(((phase,str(pos)),component),[]))
            for component in ("appearance","minutes","play_probability","60min_probability","bonus","clean_sheet_eligibility")}
            for pos in (1,2,3,4)} for phase in ("development","holdout")},
      "notes":[
       "All predictions use only prior match history, not current-GW outcomes.",
       "Clean-sheet audit uses historical club-independent player CS frequency, NOT the fixture-aware GW11 CS formula; it diagnoses historical base rates only.",
       "Only single-fixture GWs included; double-GW handling needs separate fixture-level evaluation.",
       "Bonus predictions use the same historical bonus shrinkage as GW11 model.",
       "Holdout results are diagnostics only; no parameters are changed or optimized based on them.",
       "Missing enriched fields exclude records; coverage is explicitly reported."
      ]}
 (D/"gw11_component_calibration_audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"coverage":out["coverage"],"holdout":out["by_period_position"]["holdout"]}))
if __name__=="__main__":main()
