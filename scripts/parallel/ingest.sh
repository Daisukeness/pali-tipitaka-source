#!/bin/bash
# 使い方: ingest.sh U00013 [U00014 ...]  … 担当の出力を保存・点検・記録・push する
set -e
SRC=/home/claude/pali-tipitaka-source
REPO=/home/claude/pali-ja-claude
cd $SRC
for U in "$@"; do
  OUT=/home/claude/work/agents/$U/out
  ls $OUT/*.json >/dev/null
  python3 scripts/save_translation.py --repo $REPO $OUT/*.json | tail -1
  python3 - "$U" "$OUT" <<'EOF' >> /home/claude/work/agents/stats.tsv
import sys,json,glob,sqlite3
u,out=sys.argv[1:3]
c=sqlite3.connect('/home/claude/pali-tipitaka-source/build/pali.sqlite')
seg=chars=unc=0; uids=[]
for f in sorted(glob.glob(out+'/*.json')):
    d=json.load(open(f)); uids.append(d['text_uid'])
    unc+=len(d['uncertain'])
    for sid in d['segments']:
        r=c.execute('select pali from segment where segment_id=?',(sid,)).fetchone()
        seg+=1; chars+=len(r[0]) if r else 0
import datetime
print('\t'.join(map(str,[u,len(uids),seg,chars,unc,datetime.datetime.now().strftime('%H:%M')])))
EOF
  tail -1 /home/claude/work/agents/stats.tsv
done
python3 scripts/check_translation.py $REPO/translation | tail -1
