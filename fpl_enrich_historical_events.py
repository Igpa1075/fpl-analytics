"""Incrementally enrich archived GW1-10 player fixtures with official FPL xG/xA/BPS.

Never overwrite a known fixture with incomplete data. Resumable across runs.
"""
import argparse,json,time,urllib.error,urllib.request
from datetime import datetime,timezone
from fpl_backtest_hold_baseline import D
FIELDS=("expected_goals","expected_assists","expected_goal_involvements",
        "expected_goals_conceded","bonus","bps","defensive_contribution",
        "saves","goals_scored","assists","clean_sheets","yellow_cards",
        "red_cards","own_goals","penalties_missed","penalties_saved",
        "goals_conceded","total_points","minutes")
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--limit",type=int,default=140)
 ap.add_argument("--delay",type=float,default=.22)
 args=ap.parse_args()
 path=D/"historical_players_gw1_10.json"
 state=json.loads(path.read_text(encoding="utf-8"))
 boot=json.loads((D/"bootstrap.json").read_text(encoding="utf-8"))
 ids=set(str(x["id"]) for x in boot["elements"])
 # Prioritize current-squad and captain candidates; then every other archived player
 priority=[411,166,68,154,115,504,8,31,109,236,156,592]
 queue=[str(i) for i in priority if str(i) in ids]
 queue+=sorted(ids-set(queue),key=int)
 completed=0;errors={}
 for pid in queue:
  old=state["players"].get(pid)
  if old is None:continue
  if old and all("expected_goals" in r and "bonus" in r for r in old):continue
  try:
   req=urllib.request.Request("https://fantasy.premierleague.com/api/element-summary/"+pid+"/",
          headers={"User-Agent":"FPL-historical-feature-collector/1.0","Accept":"application/json"})
   with urllib.request.urlopen(req,timeout=25) as response:
    payload=json.load(response)
   by_fixture={int(r["fixture"]):r for r in payload.get("history",[])
                if isinstance(r.get("round"),int) and 1<=r["round"]<=10}
   for row in old:
    fresh=by_fixture.get(int(row.get("fixture") or 0))
    if fresh is not None:
     for key in FIELDS:
      if key in fresh:row[key]=fresh[key]
   completed+=1
  except (urllib.error.URLError,TimeoutError,ValueError) as exc:
   errors[pid]=str(exc)
   if isinstance(exc,urllib.error.HTTPError) and exc.code==429:
    break
  if completed%20==0:
   path.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
  if completed>=args.limit:break
  time.sleep(args.delay)
 state["enrichment_updated_at_utc"]=datetime.now(timezone.utc).isoformat()
 state["enrichment_complete_players"]=sum(bool(rows) and all("expected_goals" in r and "bonus" in r for r in rows) for rows in state["players"].values())
 state["enrichment_errors"]=errors
 path.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
 print(json.dumps({"enriched_this_run":completed,"complete_players":state["enrichment_complete_players"],
                   "archived_players":len(state["players"]),"errors":len(errors)}))
if __name__=="__main__":main()
