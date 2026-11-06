"""FPL rival-aware shortlist; descriptive heuristic, not win probabilities.
Run after fpl_league.py: python fpl_strategy.py > data/strategy_analysis.txt
"""
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
MY_ID = 5150250

def load(filename):
    return json.loads((DATA / filename).read_text(encoding="utf-8"))

def num(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0

def main():
    boot = load("bootstrap.json")
    league = load("league_rivals.json")
    standings = load("league_standings.json")
    players = {p["id"]: p for p in boot["elements"]}
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    pos = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    rivals = [r for r in league["rivals"] if r["entry"] != MY_ID]
    mine = next((r for r in league["rivals"] if r["entry"] == MY_ID), None)
    if not mine:
        raise RuntimeError("Your squad is missing from league_rivals.json")
    counts = Counter(pid for r in rivals for pid in set(r["all_ids"]))
    captains = Counter(r["captain_id"] for r in rivals)
    my_ids = set(mine["all_ids"])
    n = len(rivals)
    print(f"ASG rival-aware shortlist | completed GW{league['gw']} | {n} rivals")
    print("CAUTION: rival squads and your own squad are from the last COMPLETED GW.")
    print("Ownership is based on these rivals, not worldwide FPL ownership.")
    print("Scores are ranking HEURISTICS, not projected points or probabilities.")
    print("No automatic transfer advice: current squad, sale prices, free transfers,")
    print("and future fixtures must be checked before a decision.\\n")
    print("Rival captain choices in the completed GW:")
    for pid, c in captains.most_common():
        print(f"  {players.get(pid, {}).get('web_name', pid)}: {c}/{n}")
    print("\\nYour owned players: rival ownership and heuristic")
    for pid in sorted(my_ids, key=lambda k: counts[k]):
        p = players.get(pid)
        if not p:
            continue
        score = .45*num(p.get("form"))+.35*num(p.get("points_per_game"))+.20*max(num(p.get("ep_next")),0)
        print(f"  {p['web_name']:22} {pos.get(p['element_type'],'?'):3} rivals {counts[pid]:2}/{n} | score {score:5.2f}")
    print("\\nPotential DIFFERENTIALS (not purchase recommendations):")
    print("Only players with >=180 season minutes and non-unavailable status.")
    for position in (2,3,4,1):
        options = []
        for p in players.values():
            if p["element_type"] != position or p["id"] in my_ids:
                continue
            if num(p.get("minutes")) < 180 or p.get("status") in ("u","i","s"):
                continue
            score = .45*num(p.get("form"))+.35*num(p.get("points_per_game"))+.20*max(num(p.get("ep_next")),0)
            options.append((score,p))
        options.sort(key=lambda t:t[0], reverse=True)
        # Show strongest options, including widely owned players as baseline.
        print(f"  {pos[position]}:")
        for score,p in options[:8]:
            print(f"    {p['web_name'][:19]:19} {teams.get(p['team'],'?'):3} "
                  f"£{num(p.get('now_cost'))/10:.1f}m | rivals {counts[p['id']]:2}/{n} | score {score:.2f}")
    print("\\nNEXT: model transfers with current selling prices, free transfers,")
    print("future fixtures, minutes risk, and uncertainty before estimating rank gains.")

if __name__ == "__main__":
    main()
