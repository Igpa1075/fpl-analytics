"""Personal FPL team review based on the latest *completed* gameweek.
Run: python fpl_team.py > data/team_analysis.txt
No third-party packages required.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'data'
POS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}

def load(name):
    with (ROOT / name).open(encoding='utf-8') as f:
        return json.load(f)

def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def main():
    boot, picks, entry = load('bootstrap.json'), load('picks.json'), load('entry.json')
    players = {p['id']: p for p in boot['elements']}
    teams = {t['id']: t['short_name'] for t in boot['teams']}
    event = picks.get('entry_history', {}).get('event', '?')
    bank = num(picks.get('entry_history', {}).get('bank', entry.get('last_deadline_bank'))) / 10
    rows = []
    for pick in picks['picks']:
        p = players.get(pick['element'])
        if p is None:
            print('Warning: unknown player ID:', pick['element'])
            continue
        score = 0.5 * num(p.get('form')) + 0.3 * num(p.get('points_per_game')) + 0.2 * num(p.get('ep_next'))
        if p.get('status') in ('i', 's', 'u'):
            score *= 0.25
        rows.append({'name': p['web_name'], 'team': teams.get(p['team'], '?'),
                     'pos': POS[p['element_type']], 'slot': pick['position'],
                     'captain': pick.get('is_captain', False),
                     'vice': pick.get('is_vice_captain', False),
                     'price': num(p.get('now_cost')) / 10,
                     'form': num(p.get('form')), 'ppg': num(p.get('points_per_game')),
                     'status': p.get('status', '?'), 'score': score})
    print(f'FPL team review | {entry.get("name", "Team")} | last completed GW {event}')
    print(f'Bank at GW{event} deadline: £{bank:.1f}m')
    print('WARNING: picks are from the last completed GW, not confirmed live next-GW transfers.')
    print('Score is a simple heuristic, NOT a calibrated points prediction.\n')
    print(f'{"Slot":>4} {"Player":22} {"Club":5} {"Pos":4} {"£m":>5} {"Form":>5} {"PPG":>5} {"Score":>6} Status')
    print('-' * 81)
    for r in sorted(rows, key=lambda x:x['slot']):
        flag = ' (C)' if r['captain'] else ' (VC)' if r['vice'] else ''
        print(f'{r["slot"]:4} {(r["name"] + flag)[:22]:22} {r["team"]:5} {r["pos"]:4} {r["price"]:5.1f} {r["form"]:5.1f} {r["ppg"]:5.1f} {r["score"]:6.2f} {r["status"]}')
    # Enumerate all valid 11-player combinations, respecting standard FPL formation limits.
    from itertools import combinations
    best = None
    for group in combinations(rows, 11):
        counts = {pos:sum(r['pos']==pos for r in group) for pos in POS.values()}
        if counts['GKP'] != 1 or not 3 <= counts['DEF'] <= 5 or not 2 <= counts['MID'] <= 5 or not 1 <= counts['FWD'] <= 3:
            continue
        total = sum(r['score'] for r in group)
        if best is None or total > best[0]:
            best = (total, group)
    if best:
        lineup = sorted(best[1], key=lambda r:(list(POS.values()).index(r['pos']), -r['score']))
        print('\nSuggested XI based on the heuristic (review injury/news before deadline):')
        print('Formation: ' + '-'.join(str(sum(r['pos']==pos for r in lineup)) for pos in ('DEF','MID','FWD')))
        for r in lineup:
            print(f'  {r["pos"]:3} {r["name"]:22} {r["team"]:4} score {r["score"]:.2f}')
        captain = max((r for r in lineup if r['pos']!='GKP'), key=lambda r:r['score'])
        print(f'Heuristic captain candidate: {captain["name"]} (verify minutes and fixture)')
        starters = {r['name'] for r in lineup}
        print('Bench: ' + ', '.join(r['name'] for r in rows if r['name'] not in starters))
    print('\nTransfer recommendations require live squad, free transfers, selling prices, and current fixtures.')

if __name__ == '__main__':
    main()
