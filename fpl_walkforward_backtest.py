"""Forward-only GW1-9 retrospective replay on fixed elite cohort.

IMPORTANT: This is a conditional strategy test: each manager's actual GW1 squad
is the starting point. It does NOT claim to reconstruct an independently
optimized GW1 draft. Each next decision sees only earlier GW results.
Historical current market prices are approximated by the earliest available
player-history value; actual personal sale prices are unavailable.
"""
import json
import urllib.request
import urllib.error
import time
from collections import Counter
from pathlib import Path

ROOT = Path("data")
API = "https://fantasy.premierleague.com/api"
CACHE = ROOT / "historical_player_summaries.json"
OUT = ROOT / "walkforward_elite100_gw1_9.json"
END = 9


def get(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(API + url, headers={"User-Agent": "FPL-walkforward/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_history(ids):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for index, pid in enumerate(sorted(ids), 1):
        if str(pid) not in cache:
            cache[str(pid)] = get(f"/element-summary/{pid}/")
            if index % 10 == 0:
                save(CACHE, cache)
    save(CACHE, cache)
    return cache


def histories(cache):
    return {int(pid): {int(r["round"]): r for r in doc.get("history", [])
                       if r.get("round") is not None}
            for pid, doc in cache.items()}


def price_before(rows, gw, fallback):
    # GW's own 'value' is an observed matchweek value and may be post-deadline;
    # only previous GW price can safely be used for transfers.
    prior = [r for week, r in rows.items() if week < gw]
    return int(max(prior, key=lambda r: r["round"]).get("value", fallback)) if prior else fallback


def predict(pid, gw, hist, players, fixtures):
    past = [r for week, r in hist.get(pid, {}).items() if week < gw]
    past.sort(key=lambda r: r["round"])
    p = players[pid]
    if past:
        recent = past[-5:]
        points = sum(float(x.get("total_points", 0)) for x in recent)
        appearances = sum(float(x.get("minutes", 0)) for x in recent) / 90
        ppg = points / max(1, len(recent))
        reliability = min(1, appearances / 5)
        base = reliability * ppg + (1 - reliability) * 2
        # Conservative actual-minutes trend, not today's status.
        starts = sum(int(x.get("starts", 0) or 0) > 0 or int(x.get("minutes", 0)) >= 60 for x in recent)
        base *= 0.85 + 0.15 * starts / len(recent)
    else:
        # GW1: no form/minutes from this season; neutral prior, NOT GW1 result.
        base = 2.0
    games = fixtures.get((gw, p["team"]), [])
    return round(base * sum(max(.75, min(1.25, 1 + (3 - difficulty) * .08))
                            for difficulty in games), 4)


def best_xi(ids, scores, players):
    import itertools
    best = None
    for combo in itertools.combinations(ids, 11):
        c = Counter(players[i]["element_type"] for i in combo)
        if not (c[1] == 1 and 3 <= c[2] <= 5 and 2 <= c[3] <= 5 and 1 <= c[4] <= 3):
            continue
        cap = max(combo, key=lambda i: (scores[i], -i))
        value = sum(scores[i] for i in combo) + scores[cap]
        if best is None or value > best[0]:
            best = (value, tuple(combo), cap)
    return best


def simulate(start, hist, players, fixtures, gw1_actual):
    owned = list(start)
    bank = int(gw1_actual.get("entry_history", {}).get("bank", 0))
    free = 1
    results = []
    for gw in range(1, END + 1):
        scores = {pid: predict(pid, gw, hist, players, fixtures) for pid in players}
        decision = None
        if gw > 1:
            before = best_xi(owned, scores, players)[0]
            best = (before, None)
            clubs = Counter(players[i]["team"] for i in owned)
            # Bounded shortlist: highest projected candidates by FPL position.
            shortlist = {}
            for pos in (1, 2, 3, 4):
                shortlist[pos] = sorted((i for i in players if players[i]["element_type"] == pos
                                          and i not in owned), key=lambda i: (-scores[i], i))[:8]
            for old in owned:
                selling = price_before(hist.get(old, {}), gw, players[old]["now_cost"])
                for new in shortlist[players[old]["element_type"]]:
                    if new in owned or players[new]["element_type"] != players[old]["element_type"]:
                        continue
                    if clubs[players[new]["team"]] >= 3 and players[new]["team"] != players[old]["team"]:
                        continue
                    cost = price_before(hist.get(new, {}), gw, players[new]["now_cost"])
                    if cost > selling + bank:
                        continue
                    trial = [new if i == old else i for i in owned]
                    score = best_xi(trial, scores, players)[0]
                    if score > best[0] + 0.00001:
                        best = (score, (old, new, selling, cost))
            # No paid transfers; choose only if expected XI strictly improves.
            if best[1]:
                old, new, sell, buy = best[1]
                owned = [new if i == old else i for i in owned]
                bank += sell - buy
                decision = {"out": old, "in": new, "expected_gain": round(best[0] - before, 3),
                            "price_proxy_out": sell, "price_proxy_in": buy}
        selection = best_xi(owned, scores, players)
        if selection is None:
            raise ValueError("No valid XI")
        _, xi, cap = selection
        # Actual points only read AFTER decisions are finalized for this GW.
        # This ignores autosubs/chips; compare against chip-free manager baseline.
        actual = sum(int(hist.get(i, {}).get(gw, {}).get("total_points", 0)) for i in xi)
        actual += int(hist.get(cap, {}).get(gw, {}).get("total_points", 0))
        results.append({"gw": gw, "squad": owned.copy(), "xi": list(xi), "captain": cap,
                        "transfer": decision, "model_actual_points_no_chips": actual,
                        "projected_points": round(selection[0], 3)})
    return results


def main():
    cohort = json.loads((ROOT / "elite100_cohort.json").read_text(encoding="utf-8"))["manager_ids"]
    picks = json.loads((ROOT / "elite100_cache.json").read_text(encoding="utf-8"))
    # Bootstrap metadata is current, so historical team/position transfers
    # may invalidate replay; record limitation explicitly.
    boot = get("/bootstrap-static/")
    players = {p["id"]: p for p in boot["elements"]}
    fixtures_raw = get("/fixtures/")
    fixtures = {}
    for f in fixtures_raw:
        gw = f.get("event")
        if gw is None or gw > END:
            continue
        fixtures.setdefault((gw, f["team_h"]), []).append(3)
        fixtures.setdefault((gw, f["team_a"]), []).append(3)
    initial = {}
    for manager in cohort:
        entry = picks.get(str(manager), {}).get("1")
        if entry and len(entry.get("players", [])) == 15:
            initial[str(manager)] = entry
    if len(initial) != 100:
        raise ValueError(f"Expected 100 complete GW1 squads, got {len(initial)}")
    # Every current player + all GW1 cohort players: allows an open transfer market.
    cache = load_history(set(players) | {i for x in initial.values() for i in x["players"]})
    hist = histories(cache)
    output = {"method": "forward_only_conditional_gw1_squad_replay_v1",
              "managers": {}, "limitations": [
                  "Initial GW1 squads are actual elite manager choices, not model-generated drafts.",
                  "Current team/position metadata can differ from historical GW1-9.",
                  "Historical GW price approximated by prior GW value; personal selling prices unavailable.",
                  "Historical fixture difficulty is intentionally neutral (3) to prevent revised difficulty leakage.",
                  "GW1-9 ESPN role and elite ownership signals excluded: no dated predeadline archives.",
                  "No autosubs, bench boost, triple captain, free hit or wildcard simulated.",
                  "Comparing to actual elite total points with chips is NOT apples-to-apples.",
                  "Top100 selected after GW9 is survivorship-biased."
              ]}
    for index, (manager, entry) in enumerate(initial.items(), 1):
        result = simulate(entry["players"], hist, players, fixtures, entry)
        output["managers"][manager] = {"weeks": result,
                                       "model_points": sum(x["model_actual_points_no_chips"] for x in result)}
        if index % 10 == 0:
            save(OUT, output)
            print(f"Replayed {index}/100 managers")
    totals = [v["model_points"] for v in output["managers"].values()]
    output["summary"] = {"managers": len(totals), "model_total": sum(totals),
                         "model_average": round(sum(totals) / len(totals), 2),
                         "comparison_status": "NOT_COMPARABLE_UNTIL_CHIP_FREE_ELITE_ACTUALS_RECONSTRUCTED"}
    save(OUT, output)


if __name__ == "__main__":
    main()
