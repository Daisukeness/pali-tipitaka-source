# 同じ原文の既訳を探して当てる道具（保存前の照合用）。
# 使い方: python3 scripts/sequential/match.py <経典> <開始の通し番号> <終わりの通し番号> <出力json>
# 出力は {区切り番号: [既訳の区切り番号, 訳文]}。中部を優先して探す。出力は作業フォルダの外に置く（finish.py が読み込まないように）。
import sqlite3,json,re,sys
c=sqlite3.connect('/home/claude/pali-tipitaka-source/build/pali.sqlite')
uid,lo,hi=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
segs=list(c.execute("select segment_id,pali from segment where text_uid=? order by seq",(uid,)))[lo:hi]
norm=lambda s:re.sub(r'[“”‘’"\'—–\s]+',' ',s).strip().lower()
idx={}
for sid,p,ja in c.execute("select s.segment_id,s.pali,t.ja from segment s join translation t using(segment_id) where s.text_uid like 'mn%' or s.text_uid like 'sn%' order by (s.text_uid like 'mn%') desc"):
    idx.setdefault(norm(p),(sid,ja))
out={};miss=[]
for sid,p in segs:
    r=idx.get(norm(p))
    if r and not r[0].startswith(uid+':'): out[sid]=r
    else: miss.append(sid)
json.dump({k:v for k,v in out.items()},open(sys.argv[4],'w'),ensure_ascii=False,indent=0)
print('matched',len(out),'miss',len(miss))
for k,v in out.items(): print(k,'<=',v[0],v[1][:70])
