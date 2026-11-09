import sys,json,glob,subprocess,re,os,datetime
TODAY=datetime.date.today().isoformat()
SESSION=os.environ.get("CLAUDE_SESSION_URL","")
unit,label,workdir,row=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
SRC=os.path.abspath(os.path.join(os.path.dirname(__file__),"..",".."));REPO=os.path.abspath(os.path.join(SRC,"..","pali-ja-claude"))
def run(c): return subprocess.run(c,shell=True,cwd=SRC,capture_output=True,text=True).stdout
run("python3 scripts/make_glossary.py --repo ../pali-ja-claude")
p=REPO+"/terms/ja/claude-opus-5.5/決定事項.md"
s=open(p).read()
i=s.index("\n\n\n\n## 5. 保留")
s=s[:i]+"\n"+row.rstrip("\n")+s[i:]
logs=re.findall(r"\| \d{4}-\d\d-\d\d \| U\d+.*\n",s)
last=logs[-1]
s=s.replace(last,last+f"| {TODAY} | {unit}（{label}）を順に訳す。留意点を第4章「順に訳す回で増えた留意点」に記録 |\n",1)
open(p,"w").write(s)
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
msg=f"{label} を訳し、{unit} を完了。用語集・決定事項を更新\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"+(f"\nClaude-Session: {SESSION}" if SESSION else "")
print(subprocess.run(["bash","-c",f"cd {REPO} && git add -A && git commit -qm \"$M\" && git push -q 2>&1|tail -1; git status -sb|head -1"],env={**__import__("os").environ,"M":msg},capture_output=True,text=True).stdout)
print(run("python3 scripts/progress.py 2>/dev/null | sed -n '4p;/次の作業単位/,+1p'"),"segs",segs,"unc",unc)
