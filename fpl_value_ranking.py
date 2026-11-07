
import csv
import json
from pathlib import Path
from collections import defaultdict

DATA = Path("data")

def load_json(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return json.load(f)

def load_csv(name):
    with (DATA / name).open(
        encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))

def num(value, default=0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

boot = load_json("bootstrap.json")
fixtures = load_json("fixtures.json")
picks = load_json("picks.json")
stability = load_csv("starter_stability.csv")

players = boot["elements"]
teams = {
    t["id"]: t["short_name"]
    for t in boot["teams"]
}

stable = {
    int(r["fpl_id"]): r
    for r in stability
}

owned = {
    p["element"]
    for p in picks["picks"]
}

future_gws = [
    e["id"]
    for e in boot["events"]
    if not e.get("finished")
    and not e.get("is_current")
]
future_gws = sorted(future_gws)[:3]

schedule = defaultdict(list)

for f in fixtures:
    if (
        f.get("event") not in future_gws
        or f.get("finished")
    ):
        continue

    schedule[f["team_h"]].append(
        num(f.get("team_h_difficulty"), 3)
    )
    schedule[f["team_a"]].append(
        num(f.get("team_a_difficulty"), 3)
    )

positions = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}

results = []

for p in players:
    pid = p["id"]
    minutes = num(p.get("minutes"))
    price = num(p.get("now_cost")) / 10

    if price <= 0:
        continue

    xg = num(p.get("expected_goals"))
    xa = num(p.get("expected_assists"))
    points = num(p.get("total_points"))
    form = num(p.get("form"))

    # Per-90 rates are capped for small samples.
    denominator = max(minutes, 450)

    xg90 = xg * 90 / denominator
    xa90 = xa * 90 / denominator
    points90 = points * 90 / denominator

    st = stable.get(pid, {})
    matches = int(
        num(st.get("matches_available"))
    )
    starts = int(num(st.get("starts")))

    if matches:
        start_rate = starts / matches
        # Shrink small samples toward neutral.
        start_factor = (
            starts + 2
        ) / (matches + 4)
    else:
        start_rate = None
        start_factor = 0.5

    difficulties = schedule.get(p["team"], [])

    if difficulties:
        avg_fdr = (
            sum(difficulties)
            / len(difficulties)
        )
        fixture_factor = max(
            0.8,
            min(1.2, 1 + (3 - avg_fdr) * 0.08)
        )
    else:
        avg_fdr = None
        fixture_factor = 1.0

    status = p.get("status", "a")
    chance = p.get(
        "chance_of_playing_next_round"
    )

    if status in ("i", "s", "u"):
        availability = 0.15
    elif chance is not None:
        availability = max(
            0, min(1, num(chance) / 100)
        )
    elif status == "d":
        availability = 0.65
    else:
        availability = 1.0

    # Heuristic, NOT predicted FPL points.
    attack = 4 * xg90 + 3 * xa90
    performance = (
        0.5 * points90
        + 0.5 * form
    )

    raw_score = (
        0.55 * attack
        + 0.45 * performance
    )

    # Avoid extreme penalties for 4-match samples.
    stability_factor = (
        0.7 + 0.3 * start_factor
    )

    score = (
        raw_score
        * fixture_factor
        * stability_factor
        * availability
    )

    value_score = score / price

    results.append({
        "fpl_id": pid,
        "player": p["web_name"],
        "team": teams.get(p["team"], ""),
        "position": positions.get(
            p["element_type"], ""
        ),
        "owned": "YES" if pid in owned else "NO",
        "price_m": round(price, 1),
        "minutes": int(minutes),
        "points": int(points),
        "form": round(form, 2),
        "xg90": round(xg90, 3),
        "xa90": round(xa90, 3),
        "points90": round(points90, 2),
        "starts": starts,
        "matches_checked": matches,
        "start_rate_pct": (
            round(100 * start_rate, 1)
            if start_rate is not None
            else ""
        ),
        "avg_fdr": (
            round(avg_fdr, 2)
            if avg_fdr is not None
            else ""
        ),
        "fixtures_found": len(difficulties),
        "status": status,
        "score": round(score, 3),
        "value_score": round(value_score, 4),
    })

results.sort(
    key=lambda r: r["value_score"],
    reverse=True
)

fields = list(results[0])

def save(name, rows):
    with (DATA / name).open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)

save("value_ranking_all.csv", results)

eligible = [
    r for r in results
    if r["minutes"] >= 450
    and r["status"] not in ("i", "s", "u")
    and r["fixtures_found"] > 0
]

save("value_ranking_eligible.csv", eligible)

my_team = [
    r for r in results
    if r["owned"] == "YES"
]

save("my_value_ranking.csv", my_team)

summary = {
    "players": len(results),
    "eligible_players": len(eligible),
    "my_players": len(my_team),
    "future_gameweeks": future_gws,
    "ranking_type": "heuristic",
    "notes": [
        "Not calibrated expected points.",
        "Uses FPL xG, xA, form, points and minutes.",
        "Uses ESPN starting XI stability.",
        "Fixture difficulty is an ordinal proxy.",
        "No bonus is assigned for tactical roles.",
        "Current selling prices and free transfers are unknown.",
        "Saved picks may be from an earlier gameweek."
    ]
}

with (
    DATA / "value_ranking_summary.json"
).open("w", encoding="utf-8") as f:
    json.dump(
        summary, f,
        indent=2,
        ensure_ascii=False
    )

print(json.dumps(summary, indent=2))
print("Value ranking generated successfully.")
