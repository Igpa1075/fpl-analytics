"""Fetch public FPL live minutes for the last five *fully finished* gameweeks.
One API request per GW. Do not treat unplayed current-GW fixtures as DNPs.
"""
import json, urllib.request
from datetime import datetime,timezone
from pathlib import Path
from fpl_forward_risk import DATA

API="https://fantasy.premierleague.com/api"
def fetch(path):
    req=urllib.request.Request(API+path,headers={"User-Agent":"FPL-risk-monitor/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)

def collect(bootstrap, getter=fetch):
    finished=sorted(int(e["id"]) for e in bootstrap["events"] if e.get("finished"))
    target=next((int(e["id"]) for e in bootstrap["events"] if e.get("is_next")),None)
    weeks=[gw for gw in finished if target is None or gw<target][-5:]
    records={}
    for gw in weeks:
        live=getter(f"/event/{gw}/live/")
        for element in live.get("elements",[]):
            pid=str(element["id"])
            records.setdefault(pid,[]).append({"gw":gw,"minutes":int(element.get("stats",{}).get("minutes") or 0)})
    return {"updated_at_utc":datetime.now(timezone.utc).isoformat(),"completed_gws":weeks,
            "players":records,"source":"official FPL live completed gameweeks",
            "note":"A 60+ minute match is NOT proof of starting; shorter appearance may be a substitute or injury."}

def main():
    boot=json.loads((DATA/"bootstrap.json").read_text(encoding="utf-8"))
    result=collect(boot)
    (DATA/"recent_live_minutes.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"finished_gws":result["completed_gws"],"players":len(result["players"])}))
if __name__=="__main__":main()
