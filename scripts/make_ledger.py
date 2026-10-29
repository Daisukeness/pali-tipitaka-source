#!/usr/bin/env python3
"""翻訳台帳を作り直す。

ledger/texts.tsv   経典ごとの基本情報（データベースから毎回作り直す。手で直さない）
                   uid, 部, 階層の道筋, パーリ語の経名, 文の数, パーリ語の字数
ledger/status.tsv  経典×訳者ごとの状態（手で、またはスクリプトで書き足す）
                   uid, 訳者ID, 状態, 日付, メモ
                   状態は 未着手・依頼文作成済・取込済・要確認・確認済 のどれか。
                   台帳にない組み合わせは「未着手」とみなす。

使い方:
    python3 scripts/make_ledger.py                 # texts.tsv を作り直し、集計を表示
    python3 scripts/make_ledger.py --summary sn56  # sn56 以下の集計だけ表示
"""
import argparse
import csv
import os
import sqlite3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "ledger")
STATES = ["未着手", "依頼文作成済", "取込済", "要確認", "確認済"]


def path_of(con, uid):
    parts = []
    node = con.execute("SELECT parent_uid FROM node WHERE uid=?", (uid,)).fetchone()
    while node and node[0]:
        parts.append(node[0])
        node = con.execute("SELECT parent_uid FROM node WHERE uid=?", (node[0],)).fetchone()
    return list(reversed(parts))


def write_texts(con):
    os.makedirs(LEDGER, exist_ok=True)
    rows = con.execute(
        "SELECT n.uid, n.pali_title, t.segments, t.pali_chars, t.path "
        "FROM node n JOIN text t ON t.uid = n.uid ORDER BY n.sort"
    ).fetchall()
    with open(os.path.join(LEDGER, "texts.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["uid", "pitaka", "path", "pali_title", "segments", "pali_chars"])
        for uid, title, segs, chars, path in rows:
            pitaka = path.split("/")[3]
            w.writerow([uid, pitaka, "/".join(path_of(con, uid)), title or "", segs, chars])
    return rows


def ensure_status():
    path = os.path.join(LEDGER, "status.tsv")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("uid\ttranslator\tstate\tdate\tnote\n")
    return path


def summary(prefix):
    with open(os.path.join(LEDGER, "texts.tsv"), encoding="utf-8") as f:
        texts = [r for r in csv.DictReader(f, delimiter="\t")
                 if not prefix or r["uid"] == prefix or prefix in r["path"].split("/") or r["uid"].startswith(prefix + ".")]
    with open(ensure_status(), encoding="utf-8") as f:
        status = {(r["uid"], r["translator"]): r["state"] for r in csv.DictReader(f, delimiter="\t")}
    translators = sorted({t for _, t in status}) or ["(訳者なし)"]
    print(f"対象 {len(texts):,} 経典 / 文 {sum(int(r['segments']) for r in texts):,} / "
          f"パーリ語 {sum(int(r['pali_chars']) for r in texts):,} 字")
    for t in translators:
        counts = {s: [0, 0] for s in STATES}
        for r in texts:
            s = status.get((r["uid"], t), "未着手")
            counts[s][0] += 1
            counts[s][1] += int(r["pali_chars"])
        line = " / ".join(f"{s} {n:,}経 {c:,}字" for s, (n, c) in counts.items() if n)
        print(f"  {t}: {line}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", metavar="UID", help="この uid 以下だけ集計する")
    ap.add_argument("--db", default=os.path.join(REPO, "build", "pali.sqlite"))
    args = ap.parse_args()
    if not args.summary:
        con = sqlite3.connect(args.db)
        rows = write_texts(con)
        ensure_status()
        print(f"ledger/texts.tsv に {len(rows):,} 経典を書いた")
    summary(args.summary)


if __name__ == "__main__":
    main()
