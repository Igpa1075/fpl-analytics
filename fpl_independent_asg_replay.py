"""One-team, independent GW1 draft and forward-only GW1-10 FPL replay.

This is a retrospective baseline, NOT the existing GW11 contextual model.
GW1 opening prices approximated by first historical GW value; historical team
assignments and intraweek price changes are not available in the FPL API.
"""
import json, urllib.request, time
from collections import Counter
from pathlib import Path

D=Path("data"); API="https://fantasy.premierleague.com/api/"
def get(endpoint):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(API+endpoint,headers={"User-Agent":"FPL-research/1.0"}),timeout=40) as f:return json.load(f)
        except Exception:
            if i==3:raise
            time.sleep(2*(i+1))
def read(name):return json.loads((D/name).read_text())
def write(name,obj):(D/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def valid(s,meta):
    c=Counter(meta[i]["element_type"] for i in s)
    return len(s)==15 and len(set(s))==15 and c=={1:2,2:5,3:5,4:3} and max(Counter(meta[i]["team"] for i in s).values())<=3
def main():
    boot=get("bootstrap-static/"); meta={x["id"]:x for x in boot["elements"]}
    cache=read("historical_player_summaries.json")
    hist={int(k):{int(r["round"]):r for r in v.get("history",[]) if r.get("round")} for k,v in cache.items() if isinstance(v,dict)}
    past={int(k):v.get("history_past",[]) for k,v in cache.items() if isinstance(v,dict)}
    # Historical GW1 prices are observed GW1 values, not guaranteed opening prices.
    # Never use today's now_cost as a historical price.
    eligible={i for i in meta if i in hist and 1 in hist[i] and hist[i][1].get("value") is not None}
    prices={i:int(hist[i][1]["value"]) for i in eligible}
    def cost(i,gw):
        prior=[r for w,r in hist[i].items() if w<gw and r.get("value") is not None]
        return int(max(prior,key=lambda r:r["round"])["value"]) if prior else prices[i]
    def score(i,gw):
        rows=[r for w,r in hist[i].items() if w<gw]
        rows.sort(key=lambda r:r["round"])
        if rows:
            recent=rows[-5:]; minutes=sum(r.get("minutes",0) for r in recent)
            pp=sum(r.get("total_points",0) for r in recent)/len(recent)
            availability=min(1,minutes/(90*len(recent)))
            return (pp*availability+2*(1-availability))*(.85+.15*availability)
        # PRESEASON PRIOR: previous season total points and minutes, which were
        # available before GW1. No current-season GW1 outcome used.
        old=past.get(i,[])
        if old:
            r=old[-1]; minutes=float(r.get("minutes",0) or 0)
            ppg=float(r.get("total_points",0) or 0)/max(1,minutes/90)
            return min(8,max(1,ppg))*min(1,minutes/2400)*.85+1.4*(1-min(1,minutes/2400))
        return 1.8
    def lineup(s,sc):
        # Enumerate formations (2 GKs -> choose one), top scorers by position.
        groups={p:sorted((i for i in s if meta[i]["element_type"]==p),key=lambda i:(-sc[i],i)) for p in (1,2,3,4)}
        best=None
        for nd in (3,4,5):
            for nm in (2,3,4,5):
                nf=10-nd-nm
                if not 1<=nf<=3:continue
                xi=groups[1][:1]+groups[2][:nd]+groups[3][:nm]+groups[4][:nf]
                if len(xi)!=11:continue
                cap=max(xi,key=lambda i:(sc[i],-i))
                val=sum(sc[i] for i in xi)+sc[cap]
                if best is None or val>best[0]:best=(val,xi,cap)
        return best
    def draft():
        # Greedy marginal expected XI contribution under formation constraints.
        # Seed cheapest legal squad then upgrade to maximize GW1 expected XI.
        groups={p:sorted((i for i in eligible if meta[i]["element_type"]==p),key=lambda i:(prices[i],i)) for p in (1,2,3,4)}
        squad=[]; clubs=Counter()
        for pos,n in ((1,2),(2,5),(3,5),(4,3)):
            for i in groups[pos]:
                if n==0:break
                if clubs[meta[i]["team"]]>=3:continue
                squad.append(i);clubs[meta[i]["team"]]+=1;n-=1
        if not valid(squad,meta):raise ValueError("Cannot draft legal seed")
        bank=1000-sum(prices[i] for i in squad)
        if bank<0:raise ValueError("Minimum squad exceeds budget")
        sc={i:score(i,1) for i in eligible}
        for _ in range(80):
            baseline=lineup(squad,sc)[0]
            best=(0,None)
            for old in squad:
                for new in eligible:
                    if new in squad or meta[old]["element_type"]!=meta[new]["element_type"]:continue
                    if prices[new]>prices[old]+bank:continue
                    if clubs[meta[new]["team"]]>=3 and meta[old]["team"]!=meta[new]["team"]:continue
                    trial=[new if i==old else i for i in squad]
                    gain=lineup(trial,sc)[0]-baseline
                    if gain>best[0]+1e-7:best=(gain,(old,new))
            if best[1] is None:break
            old,new=best[1];squad=[new if i==old else i for i in squad]
            bank+=prices[old]-prices[new]
            clubs[meta[old]["team"]]-=1;clubs[meta[new]["team"]]+=1
        return squad,bank
    squad,bank=draft();initial=squad.copy()
    weeks=[];free=1;purchase={i:prices[i] for i in squad}
    for gw in range(1,11):
        sc={i:score(i,gw) for i in eligible}
        transfer=None
        if gw>1:
            baseline=lineup(squad,sc)[0]
            clubs=Counter(meta[i]["team"] for i in squad)
            best=(0,None)
            # Only buy players who have already appeared before GW.
            available=[i for i in eligible if any(w<gw for w in hist[i])]
            for old in squad:
                current=cost(old,gw)
                bought=purchase[old]
                sale=bought+max(0,(current-bought)//2) if current>bought else current
                for new in available:
                    if new in squad or meta[old]["element_type"]!=meta[new]["element_type"]:continue
                    if clubs[meta[new]["team"]]>=3 and meta[old]["team"]!=meta[new]["team"]:continue
                    price=cost(new,gw)
                    if price>bank+sale:continue
                    trial=[new if i==old else i for i in squad]
                    gain=lineup(trial,sc)[0]-baseline
                    if gain>best[0]+1e-7:best=(gain,(old,new,sale,price))
            if best[1]:
                old,new,sale,price=best[1];squad=[new if i==old else i for i in squad]
                bank+=sale-price;purchase.pop(old);purchase[new]=price
                transfer={"out":old,"in":new,"expected_gain":round(best[0],3),"out_name":meta[old]["web_name"],"in_name":meta[new]["web_name"]}
                free=1
            else:free=min(5,free+1)
        if not valid(squad,meta):raise ValueError(f"Illegal squad GW{gw}")
        projected,xi,cap=lineup(squad,sc)
        # Explicitly approximate official scoring: no autosubs or chips.
        missing=[i for i in xi if gw not in hist[i]]
        if missing:raise ValueError(f"Missing player rows GW{gw}: {missing}")
        pts=sum(int(hist[i][gw]["total_points"]) for i in xi)+int(hist[cap][gw]["total_points"])
        weeks.append({"gw":gw,"points":pts,"cumulative":pts+sum(x["points"] for x in weeks),
                      "captain":meta[cap]["web_name"],"captain_id":cap,
                      "xi":[{"id":i,"name":meta[i]["web_name"],"points":hist[i][gw]["total_points"]} for i in xi],
                      "transfer":transfer,"bank_tenths":bank,"projected":round(projected,2)})
        print(f"GW{gw}: {pts} cumulative {weeks[-1]['cumulative']}",flush=True)
    standings=read("league_standings.json")
    total=weeks[-1]["cumulative"]
    ranks=[m for m in standings["members"] if m["total"]>total]
    result={"method":"independent_draft_gw1_10_preseason_prior_v1","total":total,"rank_if_added":len(ranks)+1,
            "league":standings["league_name"],"league_last_finished_gw":standings["last_finished_gw"],
            "league_members":len(standings["members"]),"initial_squad":[{"id":i,"name":meta[i]["web_name"],"price_proxy":prices[i]} for i in initial],
            "weeks":weeks,"limitations":[
                "GW1 prices from GW1 element-summary history; may not be opening prices.",
                "Current player team/position metadata can differ historically.",
                "Preseason strength from last season FPL history_past; no predeadline injury/fixture odds.",
                "Fixture difficulty and actual chips not modeled.",
                "No auto substitutions or vice-captain fallback.",
                "One optional free transfer per week, not optimized across future weeks.",
                "League standings currently contain GW10 totals although last_finished_gw says 9.",
                "This is a simple reproducible historical baseline, NOT the existing contextual GW11 model."
            ]}
    write("independent_gw1_10_asg_replay.json",result)
    print(json.dumps({"total":total,"rank_if_added":len(ranks)+1,"league":standings["league_name"]}))
if __name__=="__main__":main()
