"""Compare best legal starting XI before/after one transfer.
Uses FPL ep_next as a *one-GW estimate*, not a calibrated 3-5 GW forecast.
Run: python fpl_lineup_value.py > data/lineup_value.txt
"""
import itertools
import json
from pathlib import Path

D = Path(__file__).resolve().parent / 'data'
POS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
REFERENCE_GW = 9
CONFIRMED_NO_TRANSFERS_SINCE_GW9 = True  # Confirm again after GW10.
FREE_TRANSFERS_GW10 = 1


def load(name):
    return json.loads((D / name).read_text(encoding='utf-8'))


def val(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def projected(p):
    # ep_next is supplied by FPL; status adjustment is only a screening rule.
    x = max(0, val(p.get('ep_next')))
    chance = p.get('chance_of_playing_next_round')
    if chance is not None:
        x *= max(0, min(100, val(chance))) / 100
    elif p.get('status') in ('i', 's', 'u'):
        x *= .15
    return x


def best_xi(ids, players):
    pool = [players[i] for i in ids]
    best = None
    for group in itertools.combinations(pool, 11):
        n = {k: sum(p['element_type'] == k for p in group) for k in POS}
        if n[1] != 1 or not (3 <= n[2] <= 5 and 2 <= n[3] <= 5 and 1 <= n[4] <= 3):
            continue
        total = sum(projected(p) for p in group)
        if best is None or total > best[0]:
            best = total, group
    return best


def main():
    boot, picks = load('bootstrap.json'), load('picks.json')
    players = {p['id']: p for p in boot['elements']}
    clubs = {t['id']: t['short_name'] for t in boot['teams']}
    owned = {p['element'] for p in picks['picks']}
    last = picks.get('entry_history', {}).get('event')
    next_gw = next((e['id'] for e in boot['events'] if e.get('is_next')), None)
    print('CHUBAIS | Starting-XI transfer impact (one upcoming GW only)')
    print('Data: official FPL ep_next, adjusted for chance of playing where supplied.')
    print('These estimates are NOT calibrated or guaranteed future points.')
    print('No validated 3-5 GW forecast, rival-win probability or sale prices.\n')
    if next_gw != REFERENCE_GW + 1 or last != REFERENCE_GW or not CONFIRMED_NO_TRANSFERS_SINCE_GW9:
        print('STOP: GW9 squad confirmation is stale. Verify current squad and free transfers.')
        return
    bank = val(picks['entry_history'].get('bank')) / 10
    original = best_xi(owned, players)
    if not original:
        print('ERROR: no valid starting XI from saved squad.')
        return
    baseline, lineup = original
    print(f'GW{next_gw} | 1 confirmed free transfer | last saved bank £{bank:.1f}m')
    print(f'Best legal XI (estimated): {baseline:.2f} points before captain multiplier')
    for p in sorted(lineup, key=lambda p: (p['element_type'], -projected(p))):
        print(f'  {POS[p["element_type"]]:3} {p["web_name"]:20} {clubs[p["team"]]:4} {projected(p):5.2f}')
    print('\nPotential single transfers, ranked by impact on the *whole XI*:')
    print('CAUTION: price eligibility uses current market price as sale-price upper bound.')
    print('Any option must be checked against your actual FPL selling price.')
    club_counts = {t['id']: sum(players[i]['team'] == t['id'] for i in owned) for t in boot['teams']}
    candidates = []
    for out_id in owned:
        outgoing = players[out_id]
        ceiling = val(outgoing.get('now_cost')) / 10 + bank
        for incoming in players.values():
            if incoming['id'] in owned or incoming['element_type'] != outgoing['element_type']:
                continue
            if val(incoming.get('now_cost')) / 10 > ceiling + 1e-8:
                continue
            if club_counts[incoming['team']] >= 3 and incoming['team'] != outgoing['team']:
                continue
            if incoming.get('status') in ('i', 's', 'u') or val(incoming.get('minutes')) < 180:
                continue
            result = best_xi((owned - {out_id}) | {incoming['id']}, players)
            if not result:
                continue
            gain = result[0] - baseline
            if gain > 0.01:
                candidates.append((gain, outgoing, incoming, incoming['id'] in {p['id'] for p in result[1]}))
    candidates.sort(key=lambda x: x[0], reverse=True)
    for gain, outgoing, incoming, starts in candidates[:12]:
        print(f'  {outgoing["web_name"]:18} -> {incoming["web_name"]:18} '
              f'+{gain:.2f} estimated XI pts | £{val(incoming["now_cost"])/10:.1f}m '
              f'| new player starts: {starts}')
    if not candidates:
        print('  No positive one-GW XI changes found under approximate budget.')
    print('\nDECISION: WATCHLIST ONLY. No automatic transfer approval.')
    print('Compare 3-5 GW outlook, verified sale prices, availability, and value of saving FT.')
    print('Do not take -4 hits based on this report.')


if __name__ == '__main__':
    main()
