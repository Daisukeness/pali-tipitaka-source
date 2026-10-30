#!/usr/bin/env python3
"""翻訳台帳を作り直す。

ledger/texts.tsv   経典ごとの基本情報（データベースから毎回作り直す。手で直さない）
                   uid, 部, 階層の道筋, パーリ語の経名, 文の数, パーリ語の字数
進み具合は scripts/progress.py で見る（訳文の有無から自動で数える）。

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


def summary(prefix):
    with open(os.path.join(LEDGER, "texts.tsv"), encoding="utf-8") as f:
        texts = [r for r in csv.DictReader(f, delimiter="\t")
                 if not prefix or r["uid"] == prefix or prefix in r["path"].split("/") or r["uid"].startswith(prefix + ".")]
    print(f"対象 {len(texts):,} 経典 / 文 {sum(int(r['segments']) for r in texts):,} / "
          f"パーリ語 {sum(int(r['pali_chars']) for r in texts):,} 字")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", metavar="UID", help="この uid 以下だけ集計する")
    ap.add_argument("--db", default=os.path.join(REPO, "build", "pali.sqlite"))
    args = ap.parse_args()
    if not args.summary:
        con = sqlite3.connect(args.db)
        rows = write_texts(con)
        print(f"ledger/texts.tsv に {len(rows):,} 経典を書いた")
    summary(args.summary)


if __name__ == "__main__":
    main()
