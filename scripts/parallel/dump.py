import sqlite3,sys
c=sqlite3.connect('/home/claude/pali-tipitaka-source/build/pali.sqlite')
for uid in sys.argv[1:]:
    for sid,p in c.execute('select segment_id,pali from segment where text_uid=? order by seq',(uid,)):
        print(sid,p)
