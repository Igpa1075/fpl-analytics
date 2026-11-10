"""GW11 captain candidates: official FPL xG/xA and defensive opponent form.

Proxy only: FPL expected goals are season totals, no public xGA in bootstrap.
No unverified historical H2H statistics are used.
"""
import json,math
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
IDS=[166,154,411,68,236,592,156,115]
def main():
 b=json.loads((D/"bootstrap.json").read_text())
 f=json.loads((D/"fixtures.json").read_text())
 hist=json.loads((D/"historical_players_gw1_10.json").read_text())["players"]
 teams={int(t["id"]):t["name"] for t in b["teams"]}
 elems={int(x["id"]):x for x in b["elements"]}
 league_goals=sum(int(x["team_h_score"])+int(x["team_a_score"]) for x in f if x.get("finished") and x.get("event") and x["event"]<=10 and x.get("team_h_score") is not None)
 league_games=sum(1 for x in f if x.get("finished") and x.get("event") and x["event"]<=10 and x.get("team_h_score") is not None)
 league_per_team=league_goals/(2*league_games)
 out=[]
 for pid in IDS:
  p=elems[pid];club=int(p["team"])
  fixture=next((x for x in f if x["event"]==11 and club in (x["team_h"],x["team_a"])),None)
  if not fixture:continue
  home=club==fixture["team_h"];opp=int(fixture["team_a"] if home else fixture["team_h"])
  recent_opp=[x for x in f if x.get("finished") and x.get("event") in (6,7,8,9,10) and opp in (x["team_h"],x["team_a"])]
  full_opp=[x for x in f if x.get("finished") and isinstance(x.get("event"),int) and x["event"]<=10 and opp in (x["team_h"],x["team_a"])]
  def conceded(rows):return sum(int(x["team_a_score"] if x["team_h"]==opp else x["team_h_score"]) for x in rows)
  h=hist[str(pid)];last5=[x for x in h if 6<=int(x["gw"])<=10];last3=[x for x in h if 8<=int(x["gw"])<=10]
  mins=sum(int(x.get("minutes") or 0) for x in h)
  xg=float(p.get("expected_goals") or 0);xa=float(p.get("expected_assists") or 0)
  # xG per90 smoothed with 450 mins league neutral proxy, modest recent weight
  xg90=xg*90/max(1,mins);xa90=xa*90/max(1,mins)
  defensive=((conceded(full_opp)+4*league_per_team)/(len(full_opp)+4))
  recent_def=((conceded(recent_opp)+3*league_per_team)/(len(recent_opp)+3))
  opp_multiplier=max(.7,min(1.45,(.55*defensive+.45*recent_def)/league_per_team))
  minutes_factor=min(1.,(sum(int(x.get("minutes") or 0) for x in last5)+90)/(len(last5)*90+90))
  # Estimate attacking FPL returns, excludes appearance, bonus, defensive contributions
  attack_proxy=(4 if int(p["element_type"])==3 else 5 if int(p["element_type"])==2 else 4)
  if int(p["element_type"])==4:attack_proxy=4
  goal_pts=6 if int(p["element_type"])==2 else 5 if int(p["element_type"])==3 else 4
  score=(xg90*goal_pts+xa90*3)*opp_multiplier*(1.06 if home else .94)*minutes_factor
  out.append({"id":pid,"name":p["web_name"],"club":teams[club],"opponent":teams[opp],"home":home,
              "fixture_difficulty":fixture["team_h_difficulty"] if home else fixture["team_a_difficulty"],
              "season_minutes":mins,"season_xg":xg,"season_xa":xa,"xg_per90":round(xg90,3),"xa_per90":round(xa90,3),
              "last5_points":sum(int(x.get("total_points") or 0) for x in last5),
              "last3_points":sum(int(x.get("total_points") or 0) for x in last3),
              "last5_minutes":sum(int(x.get("minutes") or 0) for x in last5),
              "opp_conceded_10":conceded(full_opp),"opp_conceded_5":conceded(recent_opp),
              "opp_games_10":len(full_opp),"opp_games_5":len(recent_opp),
              "attacking_return_proxy":round(score,3),"status":p.get("status"),"news":p.get("news")})
 out.sort(key=lambda x:-x["attacking_return_proxy"])
 result={"status":"exploratory_attack_only_not_calibrated_xpts","created_at":datetime.now(timezone.utc).isoformat(),
 "candidates":out,"method":"FPL season xG/xA per90 times goal/assist scoring, smoothed opponent goals conceded and home/away; estimated minutes factor.",
 "warnings":["Opponent goals conceded is NOT xGA","No historical H2H xG unless independently sourced","Attacking return proxy excludes appearance, bonus, clean sheet and defensive contribution points","FPL 2026-27 team mappings from bootstrap only","Do not infer strong certainty from small differences"]}
 path=D/"gw11_captain_xg_comparison.json"
 path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"rank":[(x["name"],x["attacking_return_proxy"]) for x in out]}))
if __name__=="__main__":main()
