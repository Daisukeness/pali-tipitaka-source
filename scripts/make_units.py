#!/usr/bin/env python3
"""作業単位（1回分の目安）の一覧 ledger/units.tsv を作り直す。

ledger/plan.json の優先順に経典を並べ、unit_chars（パーリ語の字数）ごとに区切る。
  - 短い経典は、続けてまとめる（plan.json の優先順の区切りはまたがない）。
  - unit_chars を超える経典は、段落の切れ目で分ける（seg_from〜seg_to）。

進捗は文ごとに数えるので、作り直しても訳した分の記録は失われない。

使い方:
    python3 scripts/make_units.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paliwork as pw  # noqa: E402


def split_long(con, uid, limit):
    rows = con.execute("SELECT segment_id, pali FROM segment WHERE text_uid=? ORDER BY seq", (uid,)).fetchall()
    chunks, cur, chars = [], [], 0
    for i, r in enumerate(rows):
        n = len(r["pali"])
        boundary = cur and pw.section_of(r["segment_id"]) != pw.section_of(cur[-1]["segment_id"])
        if cur and ((chars >= limit * 0.85 and boundary) or chars + n > limit * 1.3):
            chunks.append((cur, chars))
            cur, chars = [], 0
        cur.append(r)
        chars += n
    if cur:
        # 最後が小さすぎるときは前とつなげる
        if chunks and chars < limit * 0.3:
            prev, pc = chunks.pop()
            cur, chars = prev + cur, pc + chars
        chunks.append((cur, chars))
    return chunks


def main():
    plan = pw.load_plan()
    limit = int(plan["unit_chars"])
    con = pw.connect()
    order = pw.texts_in_order(con, plan["order"])
    info = {r["uid"]: r for r in con.execute(
        "SELECT t.uid, t.segments, t.pali_chars, n.parent_uid FROM text t JOIN node n ON n.uid=t.uid")}

    units = []
    group, gchars, gsegs, groot = [], 0, 0, None

    def flush():
        nonlocal group, gchars, gsegs
        if group:
            parents = []
            for g in group:
                p = info[g]["parent_uid"] or ""
                if p not in parents:
                    parents.append(p)
            units.append(dict(texts=group, seg_from="", seg_to="", segments=gsegs, pali_chars=gchars,
                              parent=",".join(parents)))
        group, gchars, gsegs = [], 0, 0

    for uid, root in order:
        t = info[uid]
        if t["pali_chars"] > limit * 1.3:
            flush()
            for rows, chars in split_long(con, uid, limit):
                units.append(dict(texts=[uid], seg_from=rows[0]["segment_id"], seg_to=rows[-1]["segment_id"],
                                  segments=len(rows), pali_chars=chars, parent=t["parent_uid"]))
            continue
        if group and (root != groot or gchars + t["pali_chars"] > limit):
            flush()
        groot = root
        group.append(uid)
        gchars += t["pali_chars"]
        gsegs += t["segments"]
    flush()

    with open(pw.UNITS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["unit", "texts", "seg_from", "seg_to", "segments", "pali_chars", "parent"])
        for i, u in enumerate(units, 1):
            w.writerow([f"U{i:05d}", ",".join(u["texts"]), u["seg_from"], u["seg_to"],
                        u["segments"], u["pali_chars"], u["parent"] or ""])
    total = sum(u["pali_chars"] for u in units)
    print(f"作業単位 {len(units):,} 件（1回分の目安 {limit:,} 字、合計 {total:,} 字）→ ledger/units.tsv")


if __name__ == "__main__":
    main()
