"""Private-use Classic FPL mini-league report for team 5150250.
Run: python fpl_league.py > data/league_analysis.txt
Requires only Python standard library and the existing data/bootstrap.json.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

LEAGUE_ID = 492197
MY_ENTRY_ID = 5150250
BASE = 'https://fantasy.premierleague.com/api'
DATA = Path(__file__).resolve().parent / 'data'
DATA.mkdir(exist_ok=True)


def fetch(path):
    request = urllib.request.Request(BASE + path, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; personal-fpl-analysis/1.0)',
        'Accept': 'application/json',
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def save(filename, obj):
    (DATA / filename).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    bootstrap = json.loads((DATA / 'bootstrap.json').read_text(encoding='utf-8'))
    finished = [e['id'] for e in bootstrap.get('events', []) if e.get('finished')]
    gw = max(finished) if finished else None
    players = {p['id']: p['web_name'] for p in bootstrap.get('elements', [])}
    league_name = ''
    members = []
    page = 1
    while True:
        payload = fetch(f'/leagues-classic/{LEAGUE_ID}/standings/?page_standings={page}')
        league_name = payload.get('league', {}).get('name', league_name)
        standings = payload.get('standings', {})
        members.extend(standings.get('results', []))
        if not standings.get('has_next'):
            break
        page += 1
        if page > 20:
            raise RuntimeError('League has over 1000 entries; pagination safety limit reached')
    if not members:
        raise RuntimeError('League standings are empty or unavailable')
    members.sort(key=lambda m: (-int(m.get('total', 0)), int(m.get('rank', 999999))))
    mine = next((m for m in members if int(m.get('entry', -1)) == MY_ENTRY_ID), None)
    leader = members[0]
    print(f'FPL Classic mini-league: {league_name} | ID {LEAGUE_ID}')
    print(f'Last finished GW: {gw} | Managers: {len(members)}')
    print('Note: league totals and last completed GW picks; not live future transfers.\n')
    print(f'{"Rank":>4} {"Team":28} {"Points":>7} {"Gap to leader":>13} {"Gap to me":>10}')
    print('-' * 72)
    for m in members:
        total = int(m.get('total', 0))
        relative = (total - int(mine['total'])) if mine else None
        print(f'{str(m.get("rank", "?")):>4} {m.get("entry_name", "?")[:28]:28} {total:7} {int(leader["total"])-total:13} {relative if relative is not None else "N/A":>10}')
    if mine:
        print(f'\nMy team: {mine.get("entry_name")} | rank {mine.get("rank")} | {mine.get("total")} pts')
        print(f'Points behind leader: {int(leader["total"])-int(mine["total"])}')
    else:
        print(f'\nWARNING: My entry {MY_ENTRY_ID} not found in standings.')

    # Save standings even if individual rival-picks requests fail.
    save('league_standings.json', {'league_id': LEAGUE_ID, 'league_name': league_name,
                                  'last_finished_gw': gw, 'members': members})
    if gw is None:
        return
    rivals = []
    for m in members:
        entry_id = int(m['entry'])
        try:
            picks = fetch(f'/entry/{entry_id}/event/{gw}/picks/')
            chosen = picks.get('picks', [])
            rivals.append({'entry': entry_id, 'team_name': m.get('entry_name'),
                           'total': m.get('total'), 'rank': m.get('rank'),
                           'captain_id': next((p['element'] for p in chosen if p.get('is_captain')), None),
                           'starting_ids': [p['element'] for p in chosen if int(p.get('position', 99)) <= 11],
                           'all_ids': [p['element'] for p in chosen]})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f'WARNING: Could not fetch picks for entry {entry_id}: {exc}')
        time.sleep(0.12)
    save('league_rivals.json', {'league_id': LEAGUE_ID, 'gw': gw, 'rivals': rivals})
    own = next((r for r in rivals if r['entry'] == MY_ENTRY_ID), None)
    if own:
        own_ids = set(own['all_ids'])
        print('\nRival comparison (latest completed GW):')
        for r in rivals:
            if r['entry'] == MY_ENTRY_ID:
                continue
            overlap = len(own_ids.intersection(r['all_ids']))
            captain = players.get(r['captain_id'], '?')
            print(f'  {r["team_name"]}: {overlap}/15 shared players; captain {captain}')
    print('\nCaution: A low-owned player is not automatically a good transfer. Evaluate expected points first.')


if __name__ == '__main__':
    main()
