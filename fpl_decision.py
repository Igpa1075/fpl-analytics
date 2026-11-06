"""Conservative FPL transfer decision support for Chubais.
Run after fpl_sync.py and fpl_league.py:
    python fpl_decision.py > data/transfer_decision.txt
No dependencies beyond Python standard library.
"""
import json
from collections import Counter
from pathlib import Path

D = Path(__file__).resolve().parent / 'data'
MY_ID = 5150250
FREE_TRANSFERS = 1  # User-confirmed for GW10; update manually in later weeks.
CONFIRMED_UNCHANGED_AFTER_GW9 = True  # User-confirmed; must re-check in later weeks.
REFERENCE_GW = 9
POSITION = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def read(name):
    return json.loads((D / name).read_text(encoding='utf-8'))


def number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    boot, fixtures, picks, league = (read(f) for f in
        ('bootstrap.json', 'fixtures.json', 'picks.json', 'league_rivals.json'))
    players = {p['id']: p for p in boot['elements']}
    clubs = {t['id']: t['short_name'] for t in boot['teams']}
    owned = {p['element'] for p in picks['picks']}
    last_gw = picks.get('entry_history', {}).get('event')
    next_gw = next((e['id'] for e in boot['events'] if e.get('is_next')), None)
    if next_gw is None:
        next_gw = min((e['id'] for e in boot['events'] if not e.get('finished')), default=None)
    if next_gw is None:
        print('No upcoming gameweek; cannot make a decision.')
        return
    bank = number(picks.get('entry_history', {}).get('bank')) / 10
    current_verified = (last_gw == REFERENCE_GW and next_gw == REFERENCE_GW + 1
                        and CONFIRMED_UNCHANGED_AFTER_GW9)
    rivals = [r for r in league['rivals'] if r['entry'] != MY_ID]
    ownership = Counter(pid for r in rivals for pid in set(r['all_ids']))
    club_counts = Counter(players[pid]['team'] for pid in owned if pid in players)
    schedule = {}
    for f in fixtures:
        gw = f.get('event')
        if gw is None or not next_gw <= gw < next_gw + 5 or f.get('finished'):
            continue
        schedule.setdefault(f['team_h'], []).append((gw, number(f.get('team_h_difficulty')) or 3))
        schedule.setdefault(f['team_a'], []).append((gw, number(f.get('team_a_difficulty')) or 3))

    def estimate(p):
        # Heuristic units, not forecast FPL points; do not call it expected points.
        base = (.45 * number(p.get('form')) + .35 * number(p.get('points_per_game'))
                + .20 * max(0, number(p.get('ep_next'))))
        upcoming = schedule.get(p['team'], [])
        ratings = [difficulty for _, difficulty in upcoming]
        if not ratings:
            return 0, 0, 0
        avg = sum(ratings) / len(ratings)
        return base * max(.7, 1.15 - .07 * avg), avg, len(ratings)

    print(f'Chubais | GW{next_gw} decision support | {FREE_TRANSFERS} free transfer(s) confirmed for GW10')
    print(f'Latest saved squad: GW{last_gw}; user confirmed unchanged since GW9: {CONFIRMED_UNCHANGED_AFTER_GW9}')
    print(f'Last saved bank: £{bank:.1f}m (NOT verified current balance).')
    print('All numerical ratings are HEURISTICS, NOT predicted FPL points.')
    print('No validated future-point model or rival rank-win probabilities yet.')
    print('Actual selling prices and future transfer counts are NOT available in public data.\n')
    if not current_verified:
        print('DECISION: HOLD / VERIFY LIVE SQUAD. GW9 confirmation is stale for this gameweek.')
        return
    print('DEFAULT DECISION: HOLD the free transfer until a candidate passes')
    print('selling-price, injury, starting-XI, and lineup-value checks.')
    print('Holding one FT yields two FTs next GW, subject to FPL rules.\n')
    options = []
    for out_id in owned:
        out = players.get(out_id)
        if not out:
            continue
        out_rating, _, _ = estimate(out)
        ceiling = number(out.get('now_cost')) / 10 + bank
        for p in players.values():
            if p['id'] in owned or p['element_type'] != out['element_type']:
                continue
            if number(p.get('now_cost')) / 10 > ceiling:
                continue
            if number(p.get('minutes')) < 180 or p.get('status') in ('i', 's', 'u'):
                continue
            if club_counts[p['team']] >= 3 and p['team'] != out['team']:
                continue
            rating, fdr, matches = estimate(p)
            gain = rating - out_rating
            if gain <= 0:
                continue
            options.append((gain, out, p, fdr, matches, ceiling))
    options.sort(key=lambda r: r[0], reverse=True)
    print('WATCHLIST: possible one-for-one replacements (NOT approved transfers)')
    print('Budget ceiling assumes full current market price for outgoing player;')
    print('real sale price may be lower, so some options can be unaffordable.')
    for gain, out, p, fdr, matches, ceiling in options[:12]:
        print(f'  {out["web_name"]:17} -> {p["web_name"]:17} '
              f'{POSITION[p["element_type"]]} {clubs.get(p["team"], "?"):3} '
              f'£{number(p["now_cost"])/10:.1f}m | '
              f'{matches} fixtures / avg FDR {fdr:.1f} | '
              f'{ownership[p["id"]]}/{len(rivals)} rivals | '
              f'heuristic +{gain:.2f}')
    print('\nTO APPROVE A TRANSFER: verify live sale price, minutes and injury news;')
    print('compare starting-XI improvement over 3-5 GWs and value of banking FT.')
    print('Do NOT take -4 hits or sell a captaincy anchor based on these ratings.')


if __name__ == '__main__':
    main()
