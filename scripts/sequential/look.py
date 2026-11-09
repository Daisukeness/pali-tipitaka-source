import sqlite3,sys
import os
c=sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','build','pali.sqlite'))
n=int(sys.argv[2]) if len(sys.argv)>2 else 4
for sid,p,ja in c.execute("select s.segment_id,s.pali,t.ja from segment s join translation t on t.segment_id=s.segment_id where s.pali like ? limit ?",('%'+sys.argv[1]+'%',n)):
    print(sid,'|',p,'\n   ->',ja)
