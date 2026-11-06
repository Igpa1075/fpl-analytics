"""Provisional, fixture-aware FPL transfer shortlist for Chubais.
Run after fpl_sync.py and fpl_league.py:
    python fpl_transfer_planner.py > data/transfer_plan.txt

This is NOT an executable transfer plan: picks and bank come from the last
completed GW, and current selling prices / free transfers are not public.
"""
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
MY_ID = 5150250
POSITIONS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def load(filename):
    return json.loads((DATA / filename).read_text(encoding='utf-8'))


def num(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def main():
    boot, fixtures = load('bootstrap.json'), load('fixtures.json')
    picks = load('picks.json')
    rivals = load('league_rivals.json')['rivals']
    players = {p['id']: p for p in boot['elements']}
    clubs = {t['id']: t['short_name'] for t in boot['teams']}
    owned = {p['element'] for p in picks['picks']}
    bank = num(picks.get('entry_history', {}).get('bank')) / 10
    last_gw = picks.get('entry_history', {}).get('event', '?')
    events = boot['events']
    next_gw = next((e['id'] for e in events if e.get('is_next')), None)
    if next_gw is None:
        future = [e['id'] for e in events if not e.get('finished')]
        next_gw = min(future) if future else None
    if next_gw is None:
        print('No upcoming gameweek; transfer planning is unavailable.')
        return
    fdr = {}
    for f in fixtures:
        gw = f.get('event')
        if gw is None or not next_gw <= gw < next_gw + 3 or f.get('finished'):
            continue
        for team, difficulty in ((f['team_h'], f.get('team_h_difficulty')),
                                 (f['team_a'], f.get('team_a_difficulty'))):
            fdr.setdefault(team, []).append(num(difficulty, 3))
    ownership = Counter(pid for r in rivals if r['entry'] != MY_ID
                        for pid in set(r['all_ids']))
    club_counts = Counter(players[pid]['team'] for pid in owned if pid in players)

    def score(p):
        base = (.45 * num(p.get('form')) + .35 * num(p.get('points_per_game'))
                + .20 * max(0, num(p.get('ep_next'))))
        ratings = fdr.get(p['team'], [])
        avg = sum(ratings) / len(ratings) if ratings else 3
        return base * max(.70, 1.15 - .07 * avg), avg

    print(f'Chubais provisional transfer watchlist | next GW{next_gw}')
    print(f'Based on last completed GW{last_gw} picks; bank then £{bank:.1f}m.')
    print('IMPORTANT: the purchase budget below is an UPPER-BOUND ESTIMATE,')
    print('using current market price rather than your actual selling price.')
    print('Your current squad, bank, free transfers, selling prices, and')
    print('injury news MUST be confirmed before any real transfer.')
    print('Scores are heuristics, NOT predicted points or rank probabilities.\n')

    for out_id in sorted(owned, key=lambda pid: (players[pid]['element_type'], players[pid]['web_name'])):
        out = players[out_id]
        out_score, _ = score(out)
        ceiling = num(out['now_cost']) / 10 + bank
        options = []
        for candidate in players.values():
            if candidate['id'] in owned or candidate['element_type'] != out['element_type']:
                continue
            if num(candidate.get('now_cost')) / 10 > ceiling + 1e-9:
                continue
            if candidate.get('status') in ('i', 's', 'u') or num(candidate.get('minutes')) < 180:
                continue
            if club_counts[candidate['team']] >= 3 and candidate['team'] != out['team']:
                continue
            candidate_score, avg_fdr = score(candidate)
            gain = candidate_score - out_score
            if gain > 0:
                options.append((gain, candidate_score, avg_fdr, candidate))
        options.sort(key=lambda x: x[0], reverse=True)
        if not options:
            continue
        print(f'OUT? {out["web_name"]} ({POSITIONS[out["element_type"]]}, '
              f'{clubs.get(out["team"], "?")}) | heuristic {out_score:.2f} | '
              f'estimated budget ceiling £{ceiling:.1f}m')
        for gain, value, avg_fdr, p in options[:3]:
            print(f'  -> {p["web_name"]:20} {clubs.get(p["team"], "?"):3} '
                  f'£{num(p["now_cost"])/10:.1f}m | FDR {avg_fdr:.1f} '
                  f'| rivals {ownership[p["id"]]}/12 | score +{gain:.2f}')
    print('\nThese are research candidates only. Do not execute without checking')
    print('actual sale price, available free transfers, current squad and fixtures.')


if __name__ == '__main__':
    main()
