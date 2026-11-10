"""Walk-forward GW2-10 xG/xA-based FPL points evaluation on enriched players.

Uses only per-fixture historical fields from earlier gameweeks.
Player-specific fixture opponent is taken from archived match row.
"""
import json,math
from collections import defaultdict
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
def n(v):
 try:return float(v or 0)
 except (TypeError,ValueError):return 0.
def clamp(x,a,b):return max(a,min(b,x))
def metrics(rows,key):
 if not rows:return None
 return {"n":len(rows),"mae":round(sum(abs(r[key]-r["actual"]) for r in rows)/len(rows),3),
         "rmse":round(math.sqrt(sum((r[key]-r["actual"])**2 for r in rows)/len(rows)),3),
         "bias":round(sum(r[key]-r["actual"] for r in rows)/len(rows),3)}
def main():
 state=json.loads((D/"historical_players_gw1_10.json").read_text())
 boot=json.loads((D/"bootstrap.json").read_text())
 fixtures=json.loads((D/"fixtures.json").read_text())
 players={int(x["id"]):x for x in boot["elements"]}
 history=state["players"]
 records=[]
 coverage=[]
 captain=[]
 candidate_ids={411,166,68,154,115,504,8,31,109,236,156,592}
 for gw in range(2,11):
  past_f=[f for f in fixtures if isinstance(f.get("event"),int) and f["event"]<gw and f.get("finished") and f.get("team_h_score") is not None]
  goals=sum(int(f["team_h_score"])+int(f["team_a_score"]) for f in past_f)
  avg=goals/(2*len(past_f)) if past_f else 1.4
  against=defaultdict(list)
  for f in past_f:
   against[int(f["team_h"])].append(int(f["team_a_score"]))
   against[int(f["team_a"])].append(int(f["team_h_score"]))
  gw_rows=[]
  for pid_str,rows in history.items():
   pid=int(pid_str)
   if pid not in players:continue
   prior=[r for r in rows if int(r["gw"])<gw]
   target=[r for r in rows if int(r["gw"])==gw]
   if not prior or not target:continue
   if not all("expected_goals" in r and "expected_assists" in r and "bonus" in r for r in prior):
    continue
   if any("expected_goals" not in r for r in target):continue
   mins=sum(n(r.get("minutes")) for r in prior)
   if mins<90:continue
   recent=sorted(prior,key=lambda r:int(r["gw"]))[-5:]
   recent_minutes=sum(n(r.get("minutes")) for r in recent)
   # shrink rates to modest position priors, using prior data only
   pos=int(players[pid]["element_type"])
   prior_goal90={1:.001,2:.035,3:.16,4:.30}[pos]
   prior_assist90={1:.001,2:.035,3:.12,4:.10}[pos]
   xg90=(sum(n(r.get("expected_goals")) for r in prior)*90+prior_goal90*450)/(mins+450)
   xa90=(sum(n(r.get("expected_assists")) for r in prior)*90+prior_assist90*450)/(mins+450)
   recent_xg90=(sum(n(r.get("expected_goals")) for r in recent)*90+prior_goal90*270)/(recent_minutes+270)
   recent_xa90=(sum(n(r.get("expected_assists")) for r in recent)*90+prior_assist90*270)/(recent_minutes+270)
   xg90=.7*xg90+.3*recent_xg90
   xa90=.7*xa90+.3*recent_xa90
   play=(sum(n(r.get("minutes"))>0 for r in prior)+2)/(len(prior)+3)
   full=(sum(n(r.get("minutes"))>=60 for r in prior)+1.5)/(len(prior)+3)
   recent_play=(sum(n(r.get("minutes"))>0 for r in recent)+2)/(len(recent)+3)
   play=.5*play+.5*recent_play
   full=min(play,full)
   exp_min=min(90,(recent_minutes+180)/(len(recent)+2))*play
   opponent=int(target[0].get("opponent_team") or 0)
   opp_rows=against[opponent]
   opp_rate=(sum(opp_rows)+4*avg)/(len(opp_rows)+4)
   attack_mult=clamp((opp_rate/max(.5,avg))**.4,.75,1.35)
   if target[0].get("was_home") is True:attack_mult*=1.05
   elif target[0].get("was_home") is False:attack_mult*=.95
   goals_expected=xg90*exp_min/90*attack_mult
   assists_expected=xa90*exp_min/90*attack_mult
   base=2*full+(play-full)
   attacking=goals_expected*{1:6,2:6,3:5,4:4}[pos]+assists_expected*3
   cs=0
   if pos in (1,2,3):
    # conservative opponent clean sheet proxy from prior league GF
    opp_for=[]
    for f in past_f:
     if int(f["team_h"])==opponent:opp_for.append(int(f["team_h_score"]))
     if int(f["team_a"])==opponent:opp_for.append(int(f["team_a_score"]))
    lam=(sum(opp_for)+4*avg)/(len(opp_for)+4)
    cs=full*math.exp(-lam)*{1:4,2:4,3:1}[pos]
   bonus=sum(n(r.get("bonus")) for r in prior)/max(1,len(prior))*.65*play
   # Defensive contributions were introduced in 2025/26: points must be
   # inferred from historical total_points only when a per-match points field exists.
   def_points=sum(n(r.get("defensive_contribution_points")) for r in prior)/max(1,len(prior))*play
   predicted=base+attacking+cs+bonus+def_points
   prior_pts=sum(n(r.get("total_points")) for r in prior)
   baseline=(prior_pts+2.5*5)/(len(prior)+5)*play
   actual=sum(n(r.get("total_points")) for r in target)
   row={"gw":gw,"id":pid,"name":players[pid]["web_name"],"position":pos,
        "predicted":round(predicted,4),"baseline":round(baseline,4),
        "actual":actual,"prior_minutes":mins}
   records.append(row);gw_rows.append(row)
  eligible=[r for r in gw_rows if r["id"] in candidate_ids and r["position"]!=1]
  if len(eligible)>=3:
   m=max(eligible,key=lambda r:r["predicted"])
   b=max(eligible,key=lambda r:r["baseline"])
   haaland=next((r for r in eligible if r["id"]==411),None)
   captain.append({"gw":gw,"eligible":len(eligible),"haaland_available":haaland is not None,
                   "haaland_actual":haaland["actual"] if haaland is not None else None,
                   "model_captain":m["name"],
                   "model_actual":m["actual"],"baseline_captain":b["name"],
                   "baseline_actual":b["actual"]})
  coverage.append({"gw":gw,"players":len(gw_rows),"captain_candidates":len(eligible)})
 # GW2-7 is an exploratory development window; GW8-10 is a frozen audit window.
 # No parameters are fitted on either window here: this is a temporal split diagnostic.
 holdout=[r for r in records if r["gw"]>=8]
 development=[r for r in records if r["gw"]<=7]
 holdout_captains=[r for r in captain if r["gw"]>=8 and r["haaland_available"]]
 result={"status":"historical_xg_xa_walk_forward_partial_calibration",
         "temporal_split":{"development_gws":[2,3,4,5,6,7],"holdout_gws":[8,9,10],
           "development":{"model":metrics(development,"predicted"),"baseline":metrics(development,"baseline")},
           "holdout":{"model":metrics(holdout,"predicted"),"baseline":metrics(holdout,"baseline")},
           "holdout_by_position":{str(pos):{"model":metrics([r for r in holdout if r["position"]==pos],"predicted"),
              "baseline":metrics([r for r in holdout if r["position"]==pos],"baseline")} for pos in (1,2,3,4)},
           "holdout_captains":{"rounds":len(holdout_captains),
              "model_actual":sum(r["model_actual"] for r in holdout_captains),
              "baseline_actual":sum(r["baseline_actual"] for r in holdout_captains),
              "always_haaland_actual":sum(r["haaland_actual"] for r in holdout_captains),
              "by_gw":holdout_captains}},
         "created_at_utc":datetime.now(timezone.utc).isoformat(),
         "coverage":coverage,"model":metrics(records,"predicted"),
         "baseline":metrics(records,"baseline"),
         "by_position":{str(pos):{"model":metrics([r for r in records if r["position"]==pos],"predicted"),
                                  "baseline":metrics([r for r in records if r["position"]==pos],"baseline")}
                        for pos in (1,2,3,4)},
         "captain_comparison":{"rounds":len(captain),
           "model_actual":sum(x["model_actual"] for x in captain),
           "baseline_actual":sum(x["baseline_actual"] for x in captain),
           "by_gw":captain},
         "limitations":[
           "Uses historical xG/xA prior to each GW; no future player outcomes in features.",
           "Uses archived per-match opponent ID to avoid current-team transfer mismatch.",
           "This is a partial model, NOT identical to GW11 full-component implementation.",
           "Historical xG/xA archive enrichment may be incomplete; coverage per GW is explicit.",
           "No historical deadline availability or confirmed lineups.",
           "No robust BPS simulation; bonus is shrunk historical bonus rate.",
           "Defensive contribution points included only if archived as explicit field.",
           "Captain candidates are a fixed current-ID list, not actual past squad.",
           "GW8-10 is a chronological holdout audit; model parameters were not optimized on GW2-7, so this is not a trained-and-tuned holdout validation.",
           "Captain holdout only includes weeks with Haaland eligible in the fixed candidate list; not an actual historical squad.",
           "No forecast intervals validated."
         ]}
 (D/"gw11_historical_xg_backtest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"model":result["model"],"baseline":result["baseline"],"captain":result["captain_comparison"]}))
if __name__=="__main__":main()
