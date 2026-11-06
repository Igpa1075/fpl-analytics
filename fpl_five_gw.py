"""Five-GW scenario comparison for Chubais. Heuristic, not calibrated xP.
Run after fpl_sync.py: python fpl_five_gw.py > data/five_gw_plan.txt
Standard library only. Assumes GW9 squad unchanged for GW10 ONLY.
"""
import itertools
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
REFERENCE_GW = 9
CONFIRMED_UNCHANGED = True  # User confirmed only for GW10; do not carry forward.
FREE_TRANSFERS = 1          # User confirmed only for GW10.
POSITIONS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def load(filename):
    return json.loads((DATA / filename).read_text(encoding='utf-8'))


def num(x, default=0.0):
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def availability(p, first):
    chance = p.get('chance_of_playing_next_round') if first else None
    if chance is not None:
        return max(0.0, min(1.0, num(chance) / 100))
    return 0.15 if p.get('status') in ('i', 's', 'u') else (0.65 if p.get('status') == 'd' else 1.0)


def main():
    boot, picks, fixtures = load('bootstrap.json'), load('picks.json'), load('fixtures.json')
    players = {p['id']: p for p in boot['elements']}
    teams = {t['id']: t['short_name'] for t in boot['teams']}
    owned = {p['element'] for p in picks['picks']}
    gw = next((e['id'] for e in boot['events'] if e.get('is_next')), None)
    last = picks.get('entry_history', {}).get('event')
    print('CHUBAIS | Five-gameweek scenario model | NOT calibrated predictions')
    print('FPL ep_next anchors GW1; later GWs use a form/PPG proxy adjusted by FDR.')
    print('Captain is optimized each GW. No vice-captain, autosubs, chips, bonus projections,')
    print('future transfers, rotation forecasting, or rival-rank probabilities are modeled.')
    if gw != REFERENCE_GW + 1 or last != REFERENCE_GW or not CONFIRMED_UNCHANGED or FREE_TRANSFERS != 1:
        print('STOP: GW9 confirmation/1 free transfer applies to GW10 only.')
        print('Verify current picks, bank, selling prices and free transfers before running for another GW.')
        return
    if len(owned) != 15 or any(i not in players for i in owned):
        print('STOP: invalid saved squad or missing player data.')
        return
    bank = num(picks['entry_history'].get('bank')) / 10
    weeks = list(range(gw, min(gw + 5, 39)))
    schedule = {}
    for f in fixtures:
        event = f.get('event')
        if event not in weeks or f.get('finished'):
            continue
        for team, difficulty in ((f['team_h'], f.get('team_h_difficulty')),
                                 (f['team_a'], f.get('team_a_difficulty'))):
            schedule.setdefault((team, event), []).append(num(difficulty, 3))
    if any(not any(k[1] == week for k in schedule) for week in weeks):
        print('STOP: missing fixtures for one or more upcoming GWs; cannot compare five-week scenarios.')
        return

    def points(p, week):
        matches = schedule.get((p['team'], week), [])
        if not matches:
            return 0.0  # Blank GW
        base_next = num(p.get('ep_next'))
        longer = 0.55 * num(p.get('points_per_game')) + 0.45 * num(p.get('form'))
        base = max(0.0, base_next if week == gw else longer)
        # FDR is an ordinal difficulty scale, not a fitted numerical predictor.
        # Treat adjustment as a conservative heuristic; double GWs sum two fixtures.
        factor = sum(max(0.75, min(1.25, 1 + (3 - fdr) * 0.08)) for fdr in matches)
        return base * factor * availability(p, week == gw)

    # Cache scores to keep search fast.
    values = {(p['id'], w): points(p, w) for p in players.values() for w in weeks}

    def lineup(ids, week):
        pool = [players[i] for i in ids]
        best = None
        for group in itertools.combinations(pool, 11):
            counts = Counter(p['element_type'] for p in group)
            if not (counts[1] == 1 and 3 <= counts[2] <= 5 and 2 <= counts[3] <= 5 and 1 <= counts[4] <= 3):
                continue
            subtotal = sum(values[p['id'], week] for p in group)
            captain = max((p for p in group if p['element_type'] != 1),
                          key=lambda p: values[p['id'], week])
            total = subtotal + values[captain['id'], week]
            if best is None or total > best[0]:
                best = (total, captain['web_name'], tuple(p['id'] for p in group))
        return best

    def scenario(ids):
        return [lineup(ids, w) for w in weeks]

    baseline = scenario(owned)
    if any(x is None for x in baseline):
        print('STOP: no legal XI from saved squad.')
        return
    base_total = sum(x[0] for x in baseline)
    print(f'GW{gw}–GW{weeks[-1]} | 1 free transfer | GW9 bank £{bank:.1f}m (unverified today)')
    print(f'HOLD scenario total: {base_total:.1f} heuristic points (includes captain bonus)')
    for week, result in zip(weeks, baseline):
        print(f'  GW{week}: {result[0]:5.1f} | captain {result[1]}')

    counts = Counter(players[i]['team'] for i in owned)
    candidates = []
    for out_id in owned:
        out = players[out_id]
        # Upper bound only: real sale value may be lower than now_cost.
        ceiling = num(out.get('now_cost')) / 10 + bank
        replacements = []
        for incoming in players.values():
            if incoming['id'] in owned or incoming['element_type'] != out['element_type']:
                continue
            if num(incoming.get('now_cost')) / 10 > ceiling + 1e-8:
                continue
            if counts[incoming['team']] >= 3 and incoming['team'] != out['team']:
                continue
            if incoming.get('status') in ('i', 's', 'u') or num(incoming.get('minutes')) < 180:
                continue
            potential = sum(values[incoming['id'], w] - values[out_id, w] for w in weeks)
            if potential > 0:
                replacements.append((potential, incoming))
        # Pre-filter candidates for performance; not an exhaustive global search.
        replacements.sort(key=lambda x: x[0], reverse=True)
        for _, incoming in replacements[:8]:
            projected = scenario((owned - {out_id}) | {incoming['id']})
            if any(x is None for x in projected):
                continue
            gain = sum(x[0] for x in projected) - base_total
            if gain > 0.05:
                candidates.append((gain, out, incoming, projected))
    candidates.sort(key=lambda x: x[0], reverse=True)
    print('\nTRANSFER WATCHLIST: five-GW scenario gain vs HOLD (no future transfers)')
    print('NOT a recommendation: selling prices, actual minutes, news and FT rollover value unverified.')
    print('The HOLD scenario assumes no transfer in any of five GWs; this is NOT a fair')
    print('full comparison to a strategy that banks a transfer and uses two next GW.')
    for gain, out, incoming, scenario_results in candidates[:12]:
        captain_changes = sum(a[1] != b[1] for a, b in zip(baseline, scenario_results))
        print(f'  {out["web_name"]:17} -> {incoming["web_name"]:17} '
              f'{POSITIONS[incoming["element_type"]]} {teams[incoming["team"]]:3} '
              f'£{num(incoming["now_cost"])/10:.1f}m | '
              f'5GW heuristic +{gain:.1f} | captain changes {captain_changes}')
    if not candidates:
        print('  No positive candidates after preliminary filtering.')
    print('\nDECISION: REVIEW ONLY; no automatic approval or -4 hit.')
    print('Check real sale prices, starting probability, fixture changes, injury news,')
    print('and value of having two free transfers next GW before acting.')
    print('Reconfirm squad and FT after GW10; never reuse GW9 confirmation indefinitely.')


if __name__ == '__main__':
    main()
