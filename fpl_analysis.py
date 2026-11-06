"""FPL player shortlist from data downloaded by fpl_sync.py.

Run: python fpl_analysis.py
Optional: python fpl_analysis.py --position MID --budget 8.5 --top 15
"""
import argparse
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
POSITIONS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def read_json(name):
    with (DATA / name).open(encoding='utf-8') as file:
        return json.load(file)


def number(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def main():
    parser = argparse.ArgumentParser(description='FPL player and transfer shortlist')
    parser.add_argument('--position', choices=list(POSITIONS.values()))
    parser.add_argument('--budget', type=float, help='Maximum player price in GBP millions')
    parser.add_argument('--top', type=int, default=20)
    args = parser.parse_args()
    bootstrap = read_json('bootstrap.json')
    fixtures = read_json('fixtures.json')
    players = bootstrap.get('elements', [])
    teams = {t['id']: t['short_name'] for t in bootstrap.get('teams', [])}
    events = bootstrap.get('events', [])
    upcoming = next((e['id'] for e in events if e.get('is_next')), None)
    if upcoming is None:
        unfinished = [e['id'] for e in events if not e.get('finished')]
        upcoming = min(unfinished) if unfinished else None
    if upcoming is None:
        print('No upcoming gameweek. Using season-to-date stats only.')
    upcoming_fixtures = {}
    if upcoming is not None:
        for fixture in fixtures:
            gw = fixture.get('event')
            if gw is None or not (upcoming <= gw < upcoming + 3) or fixture.get('finished'):
                continue
            for team_id, difficulty in ((fixture['team_h'], fixture['team_h_difficulty']),
                                        (fixture['team_a'], fixture['team_a_difficulty'])):
                upcoming_fixtures.setdefault(team_id, []).append(number(difficulty, 3))
    rows = []
    for p in players:
        position = POSITIONS.get(p.get('element_type'))
        if args.position and position != args.position:
            continue
        price = number(p.get('now_cost')) / 10
        if args.budget is not None and price > args.budget:
            continue
        minutes = number(p.get('minutes'))
        if minutes < 180 or p.get('status') == 'u':
            continue
        form = number(p.get('form'))
        points_per_game = number(p.get('points_per_game'))
        expected = number(p.get('ep_next'), -1)
        fixture_ratings = upcoming_fixtures.get(p.get('team'), [])
        avg_difficulty = sum(fixture_ratings) / len(fixture_ratings) if fixture_ratings else None
        # Transparent heuristic, not a trained model or a calibrated points prediction.
        score = (0.45 * form + 0.35 * points_per_game +
                 0.20 * max(expected, 0))
        if avg_difficulty is not None:
            score *= max(0.7, 1.15 - 0.07 * avg_difficulty)
        rows.append((score, p, position, price, form, points_per_game, avg_difficulty))
    rows.sort(key=lambda r: r[0], reverse=True)
    print(f'FPL shortlist | next GW: {upcoming if upcoming else "N/A"} | '
          f'players: {len(rows)}')
    print('Score is a ranking heuristic, NOT a predicted points value.\n')
    print(f'{"Player":24} {"Team":5} {"Pos":4} {"£m":>5} {"Form":>6} {"PPG":>6} {"FDR":>5} {"Score":>7}')
    print('-' * 72)
    for score, p, pos, price, form, ppg, fdr in rows[:max(0, args.top)]:
        name = p.get('web_name', 'Unknown')[:24]
        print(f'{name:24} {teams.get(p.get("team"), "?"):5} {pos:4} '
              f'{price:5.1f} {form:6.1f} {ppg:6.1f} '
              f'{fdr if fdr is not None else "-":>5} {score:7.2f}'
              if fdr is None else
              f'{name:24} {teams.get(p.get("team"), "?"):5} {pos:4} '
              f'{price:5.1f} {form:6.1f} {ppg:6.1f} {fdr:5.1f} {score:7.2f}')


if __name__ == '__main__':
    main()
