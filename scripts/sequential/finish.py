import sys,json,glob,subprocess,re,os,datetime
TODAY=datetime.date.today().isoformat()
SESSION=os.environ.get("CLAUDE_SESSION_URL","")
unit,label,workdir,row=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
SRC=os.path.abspath(os.path.join(os.path.dirname(__file__),"..",".."));REPO=os.path.abspath(os.path.join(SRC,"..","pali-ja-claude"))
def run(c): return subprocess.run(c,shell=True,cwd=SRC,capture_output=True,text=True).stdout
run("python3 scripts/make_glossary.py --repo ../pali-ja-claude")
# 単位ごとの留意点は 留意点/<部>.md に1行足す（2026-11-11 から。それまでは 決定事項.md 第4章の表）
m=re.search(r"\b([a-z]+(?:-[a-z]+)*?)\d",label) or re.search(r"\b([a-z]+(?:-[a-z]+)*?)\d",row)
coll=m.group(1) if m else "その他"
d=REPO+"/terms/ja/claude-opus-5.5/留意点";os.makedirs(d,exist_ok=True)
p=f"{d}/{coll}.md"
if not os.path.exists(p):
    open(p,"w").write(f"# 順に訳す回で増えた留意点：{coll}\n\n1単位ずつ順に訳したときの、そろえたうえでなお残る留意点と、初めて決めた訳（仮）。単位ごとに1行（訳した順）。決まりは ../決定事項.md。\n\n| 単位 | 箇所 | 留意点・仮に決めた訳 |\n| --- | --- | --- |\n")
s=open(p).read().rstrip("\n")+"\n"+row.strip()+"\n"
open(p,"w").write(s)
print("留意点を足しました：",p)
segs=0;unc=0
for f in glob.glob(workdir+"/*.json"):
    d=json.load(open(f))
    if "segments" not in d: continue
    segs+=len(d["segments"]);unc+=len(d["uncertain"])
units=open(SRC+"/ledger/units.tsv").read().splitlines()
chars=[l.split("\t") for l in units if l.startswith(unit+"\t")][0]
run("python3 scripts/build_db.py --translations ../pali-ja-claude")
ch=[x for x in chars if x.isdigit()]
print(run(f"python3 scripts/record_work.py --repo ../pali-ja-claude --unit {unit} --segments {segs} --chars {chars[5] if len(chars)>5 else ch[-1]} --uncertain {unc} --note '順に訳す（並列なし）。{label}'"))
msg=f"{label} を訳し、{unit} を完了。用語集・留意点を更新\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"+(f"\nClaude-Session: {SESSION}" if SESSION else "")
print(subprocess.run(["bash","-c",f"cd {REPO} && git add -A && git commit -qm \"$M\" && git push -q 2>&1|tail -1; git status -sb|head -1"],env={**__import__("os").environ,"M":msg},capture_output=True,text=True).stdout)
print(run("python3 scripts/progress.py 2>/dev/null | sed -n '4p;/次の作業単位/,+1p'"),"segs",segs,"unc",unc)
