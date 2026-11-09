# 完全一致しない定型の照合用：match.py で当たらなかった文について、中部の主な経から似た原文（difflib の比率 0.85 超）を探し、既訳を表示する。
# 使い方: python3 scripts/sequential/near.py <経典> <match.py の出力json> <出力json>（候補の経は中の text_uid の一覧で指定）
import sqlite3,json,re,sys,difflib
c=sqlite3.connect('build/pali.sqlite')
uid=sys.argv[1];m=json.load(open(sys.argv[2]))
norm=lambda s:re.sub(r'[“”‘’"\'—–\s]+',' ',s).strip().lower()
cand=list(c.execute("select s.segment_id,s.pali,t.ja from segment s join translation t using(segment_id) where (s.text_uid in ('mn27','mn38','mn39','mn12','mn36','mn45','mn41','mn4','mn13','mn22','mn26','mn10','mn31','mn25','mn33','mn9','mn5','mn2','mn37'))"))
cn=[(a,norm(b),cc) for a,b,cc in cand]
out={}
for sid,p in c.execute("select segment_id,pali from segment where text_uid=? order by seq",(uid,)):
    if sid in m: continue
    n=norm(p)
    if len(n)<40: continue
    best=max(cn,key=lambda x:difflib.SequenceMatcher(None,n,x[1],autojunk=False).quick_ratio())
    r=difflib.SequenceMatcher(None,n,best[1],autojunk=False).ratio()
    if r>0.85: out[sid]=(best[0],round(r,3),best[2])
json.dump(out,open(sys.argv[3],'w'),ensure_ascii=False)
for k,v in out.items(): print(k,'~',v[0],v[1])
