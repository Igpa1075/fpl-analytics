"""GW11 full-component expected FPL points; uncertainty and model diagnostics.

Uses FPL bootstrap, fixtures and historical per-GW records, no external team
mapping. This is a structural model, not calibrated betting-market xPts.
"""
import json, math, random
from collections import defaultdict
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D

GW=11
IDS=[250,115,504,8,427,156,154,236,68,411,166,109,592,31,599]
def number(v):
 try:return float(v or 0)
 except (ValueError,TypeError):return 0.
def clamp(x,lo,hi):return max(lo,min(hi,x))
def main():
 b=json.loads((D/"bootstrap.json").read_text(encoding="utf-8"))
 fs=json.loads((D/"fixtures.json").read_text(encoding="utf-8"))
 hs=json.loads((D/"historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
 teams={int(x["id"]):x["name"] for x in b["teams"]}
 players={int(x["id"]):x for x in b["elements"]}
 ids=list(dict.fromkeys(IDS))
 completed=[f for f in fs if isinstance(f.get("event"),int) and f["event"]<=10 and f.get("finished") and f.get("team_h_score") is not None]
 league_goals=sum(int(f["team_h_score"])+int(f["team_a_score"]) for f in completed)
 league_rate=league_goals/(2*len(completed))
 goals_for=defaultdict(list);goals_against=defaultdict(list)
 for f in completed:
  h,a=int(f["team_h"]),int(f["team_a"]);hg,ag=int(f["team_h_score"]),int(f["team_a_score"])
  goals_for[h].append((f["event"],hg));goals_for[a].append((f["event"],ag))
  goals_against[h].append((f["event"],ag));goals_against[a].append((f["event"],hg))
 def shrink(rows,prior=4,recency=False):
  if recency:rows=[(gw,v) for gw,v in rows if gw>=6]
  return (sum(v for _,v in rows)+prior*league_rate)/(len(rows)+prior)
 def pmf0(lam):return math.exp(-lam)
 results=[]
 for pid in ids:
  p=players[pid];club=int(p["team"]);pos=int(p["element_type"])
  fixture=next((f for f in fs if f.get("event")==GW and club in (f["team_h"],f["team_a"])),None)
  if not fixture:continue
  home=club==int(fixture["team_h"]);opp=int(fixture["team_a"] if home else fixture["team_h"])
  history=[r for r in hs.get(str(pid),[]) if int(r["gw"])<=10]
  history.sort(key=lambda x:int(x["gw"]))
  recent=history[-5:];last3=history[-3:]
  n=len(history)
  minutes=sum(number(r.get("minutes")) for r in history)
  starts60=sum(number(r.get("minutes"))>=60 for r in history)
  played=sum(number(r.get("minutes"))>0 for r in history)
  # Beta shrinkage, emphasizing last five without double counting
  play_prob=clamp((played+2+sum(number(r.get("minutes"))>0 for r in recent))/(n+3+len(recent)),.15,.995)
  full_prob=clamp((starts60+2+sum(number(r.get("minutes"))>=60 for r in recent))/(n+3+len(recent)),.1,play_prob)
  if p.get("status") not in ("a",None):
   play_prob*=.65;full_prob*=.65
  expected_minutes=clamp((sum(number(r.get("minutes")) for r in recent)+180)/(len(recent)+2),0,90)*play_prob
  xg=number(p.get("expected_goals"));xa=number(p.get("expected_assists"))
  xg_recent=sum(number(r.get("expected_goals")) for r in recent)
  xa_recent=sum(number(r.get("expected_assists")) for r in recent)
  recent_mins=sum(number(r.get("minutes")) for r in recent)
  # Season per90 mixed with recent per90; fallback to season when no history xG data
  season_xg90=xg*90/max(90,minutes);season_xa90=xa*90/max(90,minutes)
  recent_xg90=xg_recent*90/max(90,recent_mins)
  recent_xa90=xa_recent*90/max(90,recent_mins)
  recent_available=any("expected_goals" in r for r in recent)
  xg90=.7*season_xg90+.3*recent_xg90 if recent_available else season_xg90
  xa90=.7*season_xa90+.3*recent_xa90 if recent_available else season_xa90
  opp_def=.65*shrink(goals_against[opp])+.35*shrink(goals_against[opp],recency=True)
  club_attack=shrink(goals_for[club])
  attack_factor=clamp((opp_def/league_rate)**.5*(club_attack/league_rate)**.25,.72,1.4)
  attack_factor*=1.06 if home else .94
  goal_lambda=xg90*(expected_minutes/90)*attack_factor
  assist_lambda=xa90*(expected_minutes/90)*attack_factor
  goal_points={1:6,2:6,3:5,4:4}[pos]
  appearance=full_prob*2+max(0,play_prob-full_prob)*1
  goals=goal_lambda*goal_points
  assists=assist_lambda*3
  opp_attack=.65*shrink(goals_for[opp])+.35*shrink(goals_for[opp],recency=True)
  own_def=shrink(goals_against[club])
  conceded_lambda=clamp(opp_attack*own_def/max(.4,league_rate)*(.92 if home else 1.08),.15,3.5)
  cs_probability=pmf0(conceded_lambda)
  cs_points=({1:4,2:4,3:1,4:0}[pos])*full_prob*cs_probability
  # Expected goals conceded penalty for GKs and defenders; -1 per 2 conceded
  # Poisson exact expected floor(N/2), conditioned on playing 60+.
  poisson=[math.exp(-conceded_lambda)*conceded_lambda**k/math.factorial(k) for k in range(20)]
  conceded_penalty=-full_prob*sum((k//2)*v for k,v in enumerate(poisson)) if pos in (1,2) else 0
  # Historical event components from official per-match FPL records, shrink bonus
  # and defensive contributions to avoid overreacting to last few games.
  bonus_per90=sum(number(r.get("bonus")) for r in history)*90/max(450,minutes)
  bonus=clamp(.65*bonus_per90,0,1.5)*play_prob
  def_per90=sum((number(r.get("defensive_contribution_points")) if "defensive_contribution_points" in r else (2 if number(r.get("defensive_contribution"))>= (10 if pos==2 else 12) else 0)) for r in history)*90/max(450,minutes)
  defensive=clamp(def_per90,0,2)*play_prob
  saves_per90=sum(number(r.get("saves")) for r in history)*90/max(450,minutes)
  saves=(saves_per90/3)*play_prob if pos==1 else 0
  yellow=sum(number(r.get("yellow_cards")) for r in history)/max(1,n)*(-1)*play_prob
  red=sum(number(r.get("red_cards")) for r in history)/max(1,n)*(-3)*play_prob
  own_goals=sum(number(r.get("own_goals")) for r in history)/max(1,n)*(-2)*play_prob
  missed_penalties=sum(number(r.get("penalties_missed")) for r in history)/max(1,n)*(-2)*play_prob
  penalties_saved=sum(number(r.get("penalties_saved")) for r in history)/max(1,n)*5*play_prob
  components={"appearance":appearance,"goals":goals,"assists":assists,"clean_sheet":cs_points,
              "conceded_penalty":conceded_penalty,"bonus":bonus,"defensive_contributions":defensive,
              "saves":saves,"yellow_cards":yellow,"red_cards":red,"own_goals":own_goals,
              "penalties_missed":missed_penalties,"penalties_saved":penalties_saved}
  total=sum(components.values())
  results.append({"id":pid,"name":p["web_name"],"club":teams[club],"opponent":teams[opp],
                  "home":home,"position":pos,"status":p.get("status"),"news":p.get("news"),
                  "season_minutes":minutes,"last5_points":sum(number(r.get("total_points")) for r in recent),
                  "last3_points":sum(number(r.get("total_points")) for r in last3),
                  "season_xg":xg,"season_xa":xa,"xg_per90":round(xg90,3),"xa_per90":round(xa90,3),
                  "play_probability":round(play_prob,3),"sixty_min_probability":round(full_prob,3),
                  "expected_minutes":round(expected_minutes,1),
                  "opp_goals_conceded_last5":sum(v for gw,v in goals_against[opp] if gw>=6),
                  "opp_goals_conceded_10":sum(v for _,v in goals_against[opp]),
                  "clean_sheet_probability":round(cs_probability,3),
                  "expected_goals":round(goal_lambda,3),"expected_assists":round(assist_lambda,3),
                  "components":{k:round(v,3) for k,v in components.items()},
                  "expected_points":round(total,3)})
 results.sort(key=lambda x:-x["expected_points"])
 out={"status":"full_components_structural_xpts_uncalibrated","created_at_utc":datetime.now(timezone.utc).isoformat(),
      "gw":GW,"ranking":results,
      "model_version":"0.2","limitations":[
      "Expected points model is structural and not empirically calibrated or out-of-sample validated.",
      "Team goals for/against are proxies, NOT xGA or xG team chances.",
      "Minutes and 60+ probabilities are smoothed historical proxies, not confirmed starts.",
      "Bonus is historical bonus/90 shrunk, not an actual BPS forecast.",
      "Defensive contributions inferred from official per-match counts using positional thresholds; absent fields treated as zero.",
      "Goal and assist means use FPL xG/xA; uncertainty intervals not yet validated.",
      "Current squad membership and clubs must be checked against user screenshot; public picks can lag transfers.",
      "No historical H2H xG claims are used.",
      "No claims of fully validated professional forecast."
      ]}
 path=D/"gw11_full_expected_points.json"
 path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"top":[(x["name"],x["expected_points"]) for x in results[:6]]}))
if __name__=="__main__":main()
