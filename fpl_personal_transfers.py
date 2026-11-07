
import csv
import json
import itertools
from collections import Counter, defaultdict
from pathlib import Path

D = Path("data")

def read(name):
    with (D / name).open(encoding="utf-8") as f:
        return json.load(f)

def csvread(name):
    with (D / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def number(x, default=0):
    try:
        return float(x)
    except (ValueError, TypeError):
        return default

boot = read("bootstrap.json")
picks = read("picks.json")
fixtures = read("fixtures.json")
ranking = csvread("value_ranking_all.csv")

players = {
    p["id"]: p for p in boot["elements"]
}
scores = {
    int(r["fpl_id"]): r for r in ranking
}
owned = {
    p["element"] for p in picks["picks"]
}
teams = {
    t["id"]: t["short_name"]
    for t in boot["teams"]
}

weeks = sorted(
    e["id"] for e in boot["events"]
    if not e.get("finished")
    and not e.get("is_current")
)[:3]

schedule = defaultdict(list)

for f in fixtures:
    if f.get("event") not in weeks:
        continue
    if f.get("finished"):
        continue
    for team, fdr in (
        (f["team_h"], f.get("team_h_difficulty")),
        (f["team_a"], f.get("team_a_difficulty"))
    ):
        schedule[(team, f["event"])].append(
            number(fdr, 3)
        )

def availability(p, first):
    if p.get("status") in ("i", "s", "u"):
        return 0.15
    chance = (
        p.get("chance_of_playing_next_round")
        if first else None
    )
    if chance is not None:
        return max(0, min(1, number(chance) / 100))
    if p.get("status") == "d":
        return 0.65
    return 1.0

def expected_proxy(pid, week):
    p = players[pid]
    r = scores.get(pid, {})
    games = schedule.get((p["team"], week), [])
    if not games:
        return 0.0

    # Historical performance and attacking involvement.
    base = (
        0.50 * number(r.get("points90"))
        + 0.30 * number(r.get("form"))
        + 0.20 * (
            4 * number(r.get("xg90"))
            + 3 * number(r.get("xa90"))
        )
    )

    # Starting reliability: conservative shrinkage.
    starts = number(r.get("starts"))
    matches = number(r.get("matches_checked"))
    reliability = (
        (starts + 2) / (matches + 4)
        if matches else 0.5
    )
    factor = 0.75 + 0.25 * reliability

    total = 0.0
    for fdr in games:
        adjustment = max(
            0.8,
            min(1.2, 1 + 0.08 * (3 - fdr))
        )
        total += (
            base * adjustment * factor
        )

    return total * availability(
        p, week == weeks[0]
    )

values = {
    (pid, week): expected_proxy(pid, week)
    for pid in players
    for week in weeks
}

def best_xi(ids, week):
    pool = list(ids)
    best = 0.0

    for group in itertools.combinations(pool, 11):
        counts = Counter(
            players[pid]["element_type"]
            for pid in group
        )
        if not (
            counts[1] == 1
            and 3 <= counts[2] <= 5
            and 2 <= counts[3] <= 5
            and 1 <= counts[4] <= 3
        ):
            continue

        subtotal = sum(
            values[(pid, week)]
            for pid in group
        )

        captain = max(
            (
                values[(pid, week)]
                for pid in group
                if players[pid]["element_type"] != 1
            ),
            default=0
        )

        best = max(best, subtotal + captain)

    return best

def squad_total(ids):
    return sum(best_xi(ids, w) for w in weeks)

def valid_squad(ids):
    counts = Counter(
        players[pid]["team"] for pid in ids
    )
    return (
        len(ids) == 15
        and max(counts.values()) <= 3
    )

def write_csv(name, rows, fields):
    with (D / name).open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)

if len(owned) != 15 or len(weeks) != 3:
    raise RuntimeError(
        "Missing complete squad or 3 future GWs"
    )

if not valid_squad(owned):
    raise RuntimeError("Saved squad is invalid")

baseline = squad_total(owned)
bank = number(
    picks.get("entry_history", {}).get("bank")
) / 10

# This bank belongs to the saved picks GW.
saved_gw = picks.get(
    "entry_history", {}
).get("event")

results = []
position_names = {
    1: "GK", 2: "DEF",
    3: "MID", 4: "FWD"
}

for out_id in owned:
    outgoing = players[out_id]
    out_price = number(
        outgoing.get("now_cost")
    ) / 10

    # This is an optimistic ceiling, not actual
    # buying power based on selling price.
    ceiling = out_price + bank

    preliminary = []

    for incoming in players.values():
        in_id = incoming["id"]

        if in_id in owned:
            continue
        if (
            incoming["element_type"]
            != outgoing["element_type"]
        ):
            continue
        if incoming.get("status") in ("i", "s", "u"):
            continue
        if number(incoming.get("minutes")) < 450:
            continue

        price = number(
            incoming.get("now_cost")
        ) / 10

        if price > ceiling:
            continue

        new_squad = (owned - {out_id}) | {in_id}
        if not valid_squad(new_squad):
            continue

        rough = sum(
            values[(in_id, w)]
            - values[(out_id, w)]
            for w in weeks
        )
        preliminary.append((rough, in_id))

    preliminary.sort(reverse=True)

    # Limit full XI optimization to the strongest
    # preliminary alternatives per outgoing player.
    for _, in_id in preliminary[:10]:
        incoming = players[in_id]
        new_squad = (owned - {out_id}) | {in_id}
        total = squad_total(new_squad)
        gain = total - baseline

        if gain <= 0.05:
            continue

        results.append({
            "out": outgoing["web_name"],
            "out_id": out_id,
            "out_team": teams[outgoing["team"]],
            "in": incoming["web_name"],
            "in_id": in_id,
            "in_team": teams[incoming["team"]],
            "position": position_names[
                outgoing["element_type"]
            ],
            "out_market_price": round(
                number(outgoing["now_cost"]) / 10, 1
            ),
            "in_price": round(
                number(incoming["now_cost"]) / 10, 1
            ),
            "gain_3gw_proxy": round(gain, 2),
            "budget_status": "UNVERIFIED",
        })

results.sort(
    key=lambda r: r["gain_3gw_proxy"],
    reverse=True
)

fields = [
    "out", "out_id", "out_team",
    "in", "in_id", "in_team",
    "position", "out_market_price",
    "in_price", "gain_3gw_proxy",
    "budget_status"
]

write_csv(
    "personal_transfer_candidates.csv",
    results, fields
)

best_by_out = {}
for r in results:
    best_by_out.setdefault(r["out_id"], r)

write_csv(
    "personal_transfer_priorities.csv",
    sorted(
        best_by_out.values(),
        key=lambda r: r["gain_3gw_proxy"],
        reverse=True
    ),
    fields
)

summary = {
    "saved_squad_gw": saved_gw,
    "future_gws": weeks,
    "saved_bank_m": bank,
    "baseline_3gw_proxy": round(baseline, 2),
    "positive_candidates": len(results),
    "outgoing_players_with_options": len(best_by_out),
    "best_candidate": results[0] if results else None,
    "limitations": [
        "Proxy scores are not calibrated expected points.",
        "Saved squad and bank may be outdated.",
        "Selling prices are not available.",
        "Free transfer count is unknown.",
        "Budget is an optimistic upper bound.",
        "No transfer should be executed automatically.",
        "One-transfer scenarios only.",
        "No bonus for nominal tactical positions.",
        "Bench autosubs and chip strategies omitted."
    ]
}

with (
    D / "personal_transfer_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f,
        indent=2,
        ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
