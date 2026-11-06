"""FPL GW10 strategy: one transfer now vs bank for two in GW11.
Uses verified tactical-role annotations, not assumed role-based points bonuses.
Standard library only. Run: python fpl_strategy_roles.py > data/strategy_roles.txt
"""
import json
import itertools
from collections import Counter
from pathlib import Path

D = Path(__file__).resolve().parent / "data"
REFERENCE_GW, FT = 9, 1
ROLE_EVIDENCE = {
    "De Cuyper": {
        "role": "LW / advanced left winger (recent PL matches)",
        "source": "https://www.fotmob.com/players/1134871",
        "verified": "2026-11-06",
        "note": "FPL DEF; keep defender scoring rules. Re-check match-by-match positions."
    }
}

def load(n):
    return json.loads((D/n).read_text(encoding="utf-8"))

def num(v, default=0):
    try: return float(v)
    except (ValueError, TypeError): return default

def main():
    boot, picks, fixtures = load("bootstrap.json"), load("picks.json"), load("fixtures.json")
    players = {p["id"]:p for p in boot["elements"]}
    teams = {t["id"]:t["short_name"] for t in boot["teams"]}
    owned = frozenset(x["element"] for x in picks["picks"])
    next_gw = next((e["id"] for e in boot["events"] if e.get("is_next")), None)
    last = picks.get("entry_history", {}).get("event")
    print("CHUBAIS | GW10 strategy & tactical roles | EXPERIMENTAL")
    if next_gw != 10 or last != REFERENCE_GW or len(owned)!=15:
        print("STOP: user confirmation is only valid for GW10 with GW9 squad.")
        return
    weeks = list(range(10, 15))
    bank = num(picks["entry_history"].get("bank")) / 10
    print(f"Bank at GW9: GBP {bank:.1f}m; one FT confirmed; no transfers since GW9.")
    print("Selling prices, future injuries, actual match roles and transfers remain unverified.")
    print("ROLE ANNOTATIONS (FPL positions remain unchanged for all rules):")
    for pid in owned:
        p=players[pid]
        if p["web_name"] in ROLE_EVIDENCE:
            e=ROLE_EVIDENCE[p["web_name"]]
            print(f'  {p["web_name"]}: FPL DEF; on-pitch {e["role"]}; {e["source"]}')
    print("Other players: real match roles UNKNOWN until verified from match lineups.")
    print("Role annotations DO NOT automatically add fantasy points; avoids double counting.")
    fixtures_by_team={}
    for f in fixtures:
        w=f.get("event")
        if w not in weeks or f.get("finished"): continue
        for team,fdr in [(f["team_h"],f.get("team_h_difficulty")),(f["team_a"],f.get("team_a_difficulty"))]:
            fixtures_by_team.setdefault((team,w),[]).append(num(fdr,3))
    if any(not any(k[1]==w for k in fixtures_by_team) for w in weeks):
        print("STOP: incomplete upcoming fixture data.")
        return
    def points(p,w):
        games=fixtures_by_team.get((p["team"],w),[])
        if not games:return 0.
        base = num(p.get("ep_next")) if w==10 else .55*num(p.get("points_per_game"))+.45*num(p.get("form"))
        status=p.get("status")
        chance=p.get("chance_of_playing_next_round") if w==10 else None
        availability=max(0,min(1,num(chance)/100)) if chance is not None else (.15 if status in ("i","s","u") else .65 if status=="d" else 1.)
        return max(0,base)*availability*sum(max(.75,min(1.25,1+.08*(3-d))) for d in games)
    score={(pid,w):points(p,w) for pid,p in players.items() for w in weeks}
    def xi(ids,w):
        pool=[players[i] for i in ids]
        best=(-1,None)
        for group in itertools.combinations(pool,11):
            c=Counter(p["element_type"] for p in group)
            if not (c[1]==1 and 3<=c[2]<=5 and 2<=c[3]<=5 and 1<=c[4]<=3):continue
            captain=max((p for p in group if p["element_type"]!=1),key=lambda p:score[p["id"],w])
            total=sum(score[p["id"],w] for p in group)+score[captain["id"],w]
            if total>best[0]:best=(total,captain["web_name"])
        return best
    cache={}
    def val(ids,w):
        key=(frozenset(ids),w)
        if key not in cache:cache[key]=xi(ids,w)
        return cache[key][0]
    def total(ids,start=10):
        return sum(val(ids,w) for w in weeks if w>=start)
    baseline=total(owned)
    print(f"NO TRANSFERS THROUGH GW14: {baseline:.1f} heuristic pts (not calibrated xP)")
    clubcounts=Counter(players[i]["team"] for i in owned)
    def options(ids,budget,limit=10):
        counts=Counter(players[i]["team"] for i in ids)
        result=[]
        for outid in ids:
            out=players[outid]
            ceiling=num(out.get("now_cost"))/10+budget
            for inc in players.values():
                if inc["id"] in ids or inc["element_type"]!=out["element_type"]:continue
                if num(inc.get("now_cost"))/10>ceiling+1e-6:continue
                if counts[inc["team"]]>=3 and inc["team"]!=out["team"]:continue
                if inc.get("status") in ("i","s","u") or num(inc.get("minutes"))<180:continue
                rough=sum(score[inc["id"],w]-score[outid,w] for w in weeks)
                if rough>0:result.append((rough,outid,inc["id"],ceiling))
        return sorted(result,reverse=True)[:limit]
    # Conservative shortlist; current market value is only an upper bound on selling price.
    first=options(owned,bank,25)
    now=[]
    for _,out,inc,_ in first:
        ids=(owned-{out})|{inc}
        now.append((total(ids),out,inc))
    now.sort(reverse=True)
    print("\nONE TRANSFER NOW (GW10): 5-GW projected heuristic gain")
    for v,out,inc in now[:5]:
        print(f'  {players[out]["web_name"]} -> {players[inc]["web_name"]}: {v-baseline:+.1f}')
    # Approximate two GW11 transfers: select top preliminary combinations,
    # using GW10 untouched squad, and price differences as upper bounds.
    # No changes to GW10 score, no automatic validation of future sale prices.
    banked=[]
    for _,out1,inc1,_ in first[:12]:
        ids1=(owned-{out1})|{inc1}
        cash1=bank+num(players[out1].get("now_cost"))/10-num(players[inc1].get("now_cost"))/10
        if cash1<0:continue
        for _,out2,inc2,_ in options(ids1,cash1,12):
            ids2=(ids1-{out2})|{inc2}
            if len(ids2)!=15:continue
            v=val(owned,10)+total(ids2,11)
            banked.append((v,out1,inc1,out2,inc2))
    banked.sort(reverse=True)
    print("\nBANK GW10, USE TWO FTs IN GW11 (limited search; assumes GW11 prices/status unchanged):")
    for v,o1,i1,o2,i2 in banked[:5]:
        print(f'  {players[o1]["web_name"]}->{players[i1]["web_name"]}; '
              f'{players[o2]["web_name"]}->{players[i2]["web_name"]}: '
              f'{v-baseline:+.1f} vs no-transfer baseline')
    if not banked:print("  No feasible two-transfer scenario in preliminary shortlist.")
    print("\nCAUTION: scenarios use an approximate model, not probability of beating rivals.")
    print("No player-specific role adjustment until match-by-match role data are ingested.")
    print("Do not treat these scenarios as approved transfers; verify selling prices, lineup and news.")
    print("FT confirmation expires after GW10; next GW requires a fresh check.")

if __name__=="__main__":
    main()
