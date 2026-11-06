"""Audit real match roles against FPL positions.

Optional input data/match_roles.csv with columns:
fpl_id,match_date,minutes,actual_role,source_url
actual_role: GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LW, RW, ST.
Use match-by-match observed roles, not generic player profile positions.
Run: python fpl_roles_audit.py > data/roles_audit.txt
No third-party packages or unofficial scraping.
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).resolve().parent / 'data'
ROLES = {'GK','CB','LB','RB','LWB','RWB','DM','CM','AM','LW','RW','ST'}
ATTACKING = {'LWB','RWB','AM','LW','RW','ST'}
FPL = {1:'GKP',2:'DEF',3:'MID',4:'FWD'}


def main():
    boot = json.loads((DATA/'bootstrap.json').read_text(encoding='utf-8'))
    players = {int(p['id']):p for p in boot['elements']}
    print('FPL REAL MATCH ROLE AUDIT | observational only')
    print('FPL position determines scoring and legal squad structure; real role is a separate signal.')
    path = DATA/'match_roles.csv'
    if not path.exists():
        print('NO MATCH DATA: data/match_roles.csv not found.')
        print('Create a CSV with columns: fpl_id,match_date,minutes,actual_role,source_url')
        print('Use an authorized match-lineups provider or manually verified match reports.')
        print('Do not assume player profile position = actual position in every match.')
        return
    rows = defaultdict(list)
    rejected = 0
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'fpl_id','match_date','minutes','actual_role','source_url'}
        if not required.issubset(set(reader.fieldnames or [])):
            print('STOP: CSV missing columns: '+', '.join(sorted(required-set(reader.fieldnames or []))))
            return
        seen = set()
        for r in reader:
            try:
                pid = int(r['fpl_id'])
                minutes = int(r['minutes'])
                when = date.fromisoformat(r['match_date'])
                role = r['actual_role'].strip().upper()
                source = r['source_url'].strip()
                host = urlparse(source)
                if pid not in players or role not in ROLES or not 0 <= minutes <= 130 or when > date.today() or host.scheme != 'https' or not host.netloc:
                    raise ValueError('Invalid row')
                key = (pid,when)
                if key in seen:
                    raise ValueError('Duplicate player/match')
                seen.add(key)
                if minutes >= 30:
                    rows[pid].append((when,minutes,role,source))
            except (KeyError, ValueError, TypeError):
                rejected += 1
    print(f'Valid player-match records (>=30 minutes): {sum(map(len,rows.values()))}; rejected rows: {rejected}')
    print('Sample: last 5 dated appearances per player; minimum 3 to describe a tendency.')
    flags = []
    for pid, all_matches in rows.items():
        p = players[pid]
        recent = sorted(all_matches,reverse=True)[:5]
        if len(recent) < 3:
            continue
        minutes = sum(m for _,m,_,_ in recent)
        attack = sum(m for _,m,r,_ in recent if r in ATTACKING)
        ratio = attack/minutes if minutes else 0
        counts = Counter(r for _,_,r,_ in recent)
        common = ', '.join(f'{r}:{n}' for r,n in counts.most_common(3))
        desc = f'{p["web_name"]} | FPL {FPL[p["element_type"]]} | observed {common} | attacking-role minutes {ratio:.0%} | n={len(recent)}'
        print(desc)
        if p['element_type']==2 and ratio >= .6:
            flags.append((ratio,p['web_name'],pid))
    print('\nDEFENDERS FREQUENTLY IN ADVANCED ROLES (>=60% of sampled minutes):')
    if not flags:
        print('  None confirmed from supplied match data.')
    for ratio,name,pid in sorted(flags,reverse=True):
        print(f'  {name} (FPL ID {pid}): {ratio:.0%} — investigate attacking opportunity, do NOT auto-add points')
    print('\nWARNING: positional tags are simplified; a lineup role is not a heatmap or touch-location measurement.')
    print('No forecast adjustment until backtesting validates a role-based predictive benefit.')

if __name__=='__main__':
    main()
