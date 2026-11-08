"""Convert compact translation text into per-sutta JSON files (prompt v1 output form).

Format of input file:
  #T key|ja|reason        term (attached to current sutta)
  #U segid|note           uncertain
  segid<TAB>translation   segment
"""
import json, sqlite3, sys, os, re

DB = '/home/claude/pali-tipitaka-source/build/pali.sqlite'
c = sqlite3.connect(DB)
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
data = {}
cur = None
for line in open(sys.argv[1], encoding='utf-8'):
    line = line.rstrip('\n')
    if not line.strip():
        continue
    if line.startswith('#T '):
        k, ja, reason = line[3:].split('|', 2)
        data[cur]['terms'][k] = {'ja': ja, 'reason': reason}
    elif line.startswith('#U '):
        s, note = line[3:].split('|', 1)
        r = c.execute('select text_uid from segment where segment_id=?', (s,)).fetchone()
        data[r[0] if r else s.split(':')[0]]['uncertain'].append({'segment': s, 'note': note})
    else:
        sid, ja = line.split('\t', 1)
        r = c.execute('select text_uid from segment where segment_id=?', (sid,)).fetchone()
        cur = r[0] if r else sid.split(':')[0]
        data.setdefault(cur, {'segments': {}, 'terms': {}, 'uncertain': []})
        data[cur]['segments'][sid] = ja
err = 0
for uid, d in data.items():
    ids = [r[0] for r in c.execute('select segment_id from segment where text_uid=? order by seq', (uid,))]
    got = d['segments']
    missing = [i for i in ids if i not in got]
    extra = [i for i in got if i not in ids]
    if missing or extra:
        print(uid, 'missing', missing, 'extra', extra); err += 1
    obj = {'translator': 'claude-opus-5.5', 'date': '2026-11-08', 'prompt_version': 'v1',
           'text_uid': uid, 'segments': {i: got[i] for i in ids if i in got},
           'terms': d['terms'], 'uncertain': d['uncertain']}
    json.dump(obj, open(f'{out_dir}/{uid}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(len(data), 'texts', 'errors', err)
