"""FPL standard bench auto-substitution and captain fallback.

Inputs are a pre-deadline ordered 15-player lineup and actual GW minutes.
No chip handling (bench boost, triple captain), transfers or price modeling.
"""
from collections import Counter


def valid_formation(xi, positions):
    counts = Counter(positions[p] for p in xi)
    return (len(xi) == 11 and counts[1] == 1
            and 3 <= counts[2] <= 5 and 2 <= counts[3] <= 5
            and 1 <= counts[4] <= 3)


def resolve(lineup, positions, minutes, points, captain, vice):
    """lineup: 11 starters followed by ordered bench (GK then three outfield)."""
    if len(lineup) != 15 or len(set(lineup)) != 15:
        raise ValueError("Expected 15 unique players")
    xi = list(lineup[:11])
    bench = list(lineup[11:])
    if not valid_formation(xi, positions):
        raise ValueError("Invalid initial formation")
    if positions[bench[0]] != 1 or any(positions[p] == 1 for p in bench[1:]):
        raise ValueError("Bench must be goalkeeper followed by three outfield players")
    if captain not in xi or vice not in lineup or captain == vice:
        raise ValueError("Captain must start; vice must be a distinct squad player")
    swaps = []
    # GK replacement, if GK did not play.
    absent_gk = next((p for p in xi if positions[p] == 1 and minutes.get(p, 0) == 0), None)
    if absent_gk is not None and minutes.get(bench[0], 0) > 0:
        xi.remove(absent_gk)
        xi.append(bench[0])
        swaps.append((absent_gk, bench[0]))
    # Process bench players in priority order, respecting valid formation.
    for substitute in bench[1:]:
        if minutes.get(substitute, 0) <= 0:
            continue
        for absent in list(xi):
            if positions[absent] == 1 or minutes.get(absent, 0) > 0:
                continue
            candidate = [p for p in xi if p != absent] + [substitute]
            if valid_formation(candidate, positions):
                xi = candidate
                swaps.append((absent, substitute))
                break
    base = sum(int(points.get(p, 0)) for p in xi)
    active_captain = captain if minutes.get(captain, 0) > 0 else (
        vice if vice in xi and minutes.get(vice, 0) > 0 else None)
    return {"points": base + (int(points.get(active_captain, 0)) if active_captain else 0),
            "base_points": base, "captain_scoring": active_captain,
            "autosubs": [{"out": a, "in": b} for a, b in swaps], "final_xi": xi}
