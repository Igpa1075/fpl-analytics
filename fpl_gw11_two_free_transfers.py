"""Explore zero, one, or two GW11 free transfers over GW11-13.

User screenshot (10 Nov) confirms 2 free transfers and a provisional
O'Shea (304) -> Konsa (31) replacement leaving GBP 0.1m.
This is NOT an authenticated selling-price feed. Only that exact first
replacement is confirmed feasible by the screenshot.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fpl_backtest_hold_baseline import D
from fpl_joint_gw11_fixture_aware import GWS, defensive_factors, optimize, player_forecast

OUT = D / "gw11_two_free_transfer_scenarios.json"
FIRST_OUT, FIRST_IN = 304, 31


def main():
    if OUT.exists():
        print("Frozen two-transfer scenarios already exist")
        return
    now = datetime.now(timezone.utc)
    boot = json.loads((D/"bootstrap.json").read_text(encoding="utf-8"))
    picks = json.loads((D/"picks.json").read_text(encoding="utf-8"))
    fixtures = json.loads((D/"fixtures.json").read_text(encoding="utf-8"))
    players = json.loads((D/"historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    event = next(e for e in boot["events"] if int(e["id"]) == 11)
    deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
    if now >= deadline or int(picks["entry_history"]["event"]) != 10:
        print("Not eligible for predeadline GW11 scenarios")
        return
    elements = {int(e["id"]): e for e in boot["elements"]}
    positions = {p: int(e["element_type"]) for p,e in elements.items() if str(p) in players}
    teams = {p: int(elements[p]["team"]) for p in positions}
    names = {p: e["web_name"] for p,e in elements.items()}
    squad = [int(p["element"]) for p in picks["picks"]]
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Invalid published squad")
    if FIRST_OUT not in squad or FIRST_IN in squad:
        raise ValueError("Screenshot-confirmed provisional swap differs from published squad")
    by_gw = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        if f.get("event") not in GWS:
            continue
        h,a = int(f["team_h"]), int(f["team_a"])
        by_gw[int(f["event"])][h].append((a,True))
        by_gw[int(f["event"])][a].append((h,False))
    if any(len(by_gw[gw]) < 20 for gw in GWS):
        raise ValueError("Incomplete fixtures")
    factors = defensive_factors(fixtures)
    bank = int(picks["entry_history"]["bank"])
    baseline = optimize(squad, positions, players, by_gw, teams, factors)
    # Cache the 3-GW individual forecasts; shortlist candidates by gain
    # before expensive lineup optimization. This is a HEURISTIC search.
    forecast = {}
    for pid in positions:
        forecast[pid] = sum(
            sum(player_forecast(pid, players, gw, factors.get(opp, 1.0), home)
                for opp, home in by_gw[gw].get(teams[pid], []))
            for gw in GWS
        )
    counts = Counter(teams[p] for p in squad)

    def legal_clubs(out_ids, in_ids):
        c = counts.copy()
        for p in out_ids:
            c[teams[p]] -= 1
        for p in in_ids:
            c[teams[p]] += 1
        return all(v <= 3 for v in c.values())

    def named(p):
        return {"id": p, "name": names[p], "club_id": teams[p],
                "market_price_tenths": int(elements[p]["now_cost"])}

    def describe(out_ids, in_ids, bank_after, sale_confirmed=False):
        trial = [in_ids[out_ids.index(p)] if p in out_ids else p for p in squad]
        result = optimize(trial, positions, players, by_gw, teams, factors)
        return {"transfers": [{"out": named(a), "in": named(b)}
                              for a,b in zip(out_ids,in_ids)],
                "bank_after_market_proxy_tenths": bank_after,
                "gain_three_gw_proxy": round(result["three_gw_proxy"]-baseline["three_gw_proxy"],3),
                "lineup": result,
                "screenshot_verified_first_transfer": sale_confirmed}

    # A single transfer has no hit. Saving the second free transfer may
    # have option value beyond this GW11-13 horizon; not quantified.
    single = []
    for o in squad:
        for i in positions:
            if i in squad or positions[i] != positions[o] or not legal_clubs([o],[i]):
                continue
            after = bank+int(elements[o]["now_cost"])-int(elements[i]["now_cost"])
            if after < 0:
                continue
            single.append(describe([o],[i],after,o==FIRST_OUT and i==FIRST_IN))
    single.sort(key=lambda x:-x["gain_three_gw_proxy"])

    # Limit each outgoing player's incoming pool to 12 based on
    # independent 3GW forecast gain, while retaining the confirmed Konsa.
    options = {}
    for o in squad:
        opts = [i for i in positions if i not in squad and positions[i]==positions[o]]
        opts.sort(key=lambda i:(-forecast[i],i))
        options[o] = opts[:12]
        if o==FIRST_OUT and FIRST_IN not in options[o]:
            options[o].append(FIRST_IN)

    pair = []
    seen = set()
    for a_idx, o1 in enumerate(squad):
        for o2 in squad[a_idx+1:]:
            for i1 in options[o1]:
                for i2 in options[o2]:
                    if i1==i2 or not legal_clubs([o1,o2],[i1,i2]):
                        continue
                    key=(o1,o2,i1,i2)
                    if key in seen:
                        continue
                    seen.add(key)
                    after=bank+int(elements[o1]["now_cost"])+int(elements[o2]["now_cost"])-int(elements[i1]["now_cost"])-int(elements[i2]["now_cost"])
                    if after < 0:
                        continue
                    pair.append(describe([o1,o2],[i1,i2],after))
    pair.sort(key=lambda x:-x["gain_three_gw_proxy"])

    # Exact screenshot-confirmed first move, with GBP 0.1m left, so
    # second sale must fund second buy. Its sale price is still a proxy.
    fixed_squad=[FIRST_IN if p==FIRST_OUT else p for p in squad]
    fixed_counts=Counter(teams[p] for p in fixed_squad)
    fixed_bank=1
    fixed=[]
    for o in fixed_squad:
        if o==FIRST_IN:
            continue
        for i in positions:
            if i in fixed_squad or positions[i]!=positions[o]:
                continue
            c=fixed_counts.copy()
            c[teams[o]]-=1
            c[teams[i]]+=1
            if any(v>3 for v in c.values()):
                continue
            after=fixed_bank+int(elements[o]["now_cost"])-int(elements[i]["now_cost"])
            if after<0:
                continue
            # The first move is screenshot-verified; second remains proxy.
            fixed.append(describe([FIRST_OUT,o],[FIRST_IN,i],after,True))
    fixed.sort(key=lambda x:-x["gain_three_gw_proxy"])

    result={
        "status":"exploratory_two_free_transfers_not_sale_price_verified",
        "created_at_utc":now.isoformat(),
        "deadline_utc":deadline.isoformat(),
        "screenshot_confirmed_free_transfers":2,
        "screenshot_confirmed_bank_tenths":9,
        "screenshot_confirmed_provisional_transfer":{"out":named(FIRST_OUT),"in":named(FIRST_IN),"bank_after_tenths":1,"not_submitted":True},
        "baseline":baseline,
        "best_one_transfer":single[:10],
        "best_two_transfers_shortlisted":pair[:10],
        "best_second_transfer_after_confirmed_first":fixed[:10],
        "counts":{"single_candidates":len(single),"two_transfer_shortlisted_candidates":len(pair),"second_after_fixed_candidates":len(fixed)},
        "limitations":[
            "Two-transfer combinations are HEURISTIC shortlisted (top 12 incoming forecasts per outgoing), not globally exhaustive.",
            "All sale prices except screenshot-confirmed O'Shea->Konsa are market proxies; combinations are not verified executable.",
            "Second transfer after confirmed first uses current market price as sale proxy.",
            "Screenshot confirms two free transfers at the time, not the number at eventual deadline.",
            "Saving one free transfer has future value not included in three-GW proxy.",
            "Forecasts are uncalibrated heuristics from GW8-10 minutes and points, opponent goals conceded, home/away.",
            "Player injuries and future minutes are not predicted; no authenticated team changes are read.",
            "No transactions have been submitted to FPL."
        ]
    }
    with OUT.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps({"single":len(single),"pairs":len(pair),"fixed":len(fixed),
                      "best_single":single[0]["gain_three_gw_proxy"] if single else None,
                      "best_pair":pair[0]["gain_three_gw_proxy"] if pair else None}))


if __name__=="__main__":
    main()
