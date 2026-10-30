#!/usr/bin/env python3
"""経典を指定して翻訳の依頼文を作る。原文と翻訳ルールだけで作り、訳文は一切入れない。

使い方:
    python3 scripts/make_prompt.py U00001 --remaining          # 作業単位。まだ訳のない文だけ
    python3 scripts/make_prompt.py sn56.11 --translator claude-opus-5.5
    python3 scripts/make_prompt.py sn56 --translator claude-opus-5.5 --out out/
        # sn56 の下にある経典すべてを、1経典1ファイルで out/ に書き出す

先に scripts/build_db.py でデータベースを作っておくこと。
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paliwork as pw  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def texts_under(con, uid):
    """uid が経典ならそれだけ、枝なら下にある経典すべてを木の順に返す。"""
    found = []

    def walk(u):
        row = con.execute("SELECT is_text FROM node WHERE uid=?", (u,)).fetchone()
        if row is None:
            return
        if row[0]:
            found.append(u)
        for (child,) in con.execute("SELECT uid FROM node WHERE parent_uid=? ORDER BY sort", (u,)):
            walk(child)

    walk(uid)
    return found


def load_template(version):
    with open(os.path.join(REPO, "prompts", f"{version}.md"), encoding="utf-8") as f:
        body = f.read()
    marker = "\n---ここから依頼文---\n"
    if marker not in body:
        raise SystemExit(f"prompts/{version}.md に「---ここから依頼文---」だけの行がない")
    return body.split(marker, 1)[1].strip() + "\n"


def make(con, template, text_uid, translator, version, date, rows=None):
    if rows is None:
        rows = con.execute("SELECT segment_id, pali FROM segment WHERE text_uid=? ORDER BY seq", (text_uid,)).fetchall()
    rows = [(r[0], r[1]) for r in rows]
    lines = "\n".join(f"{sid}\t{pali}" for sid, pali in rows)
    return (
        template.replace("{{segments}}", lines)
        .replace("{{text_uid}}", text_uid)
        .replace("{{translator}}", translator)
        .replace("{{version}}", version)
        .replace("{{date}}", date)
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uid", help="作業単位（例 U00001）、経典または枝の uid（例 sn56.11、sn56）")
    ap.add_argument("--translator", default=pw.DEFAULT_TRANSLATOR, help="訳者ID（例 claude-opus-5.5）")
    ap.add_argument("--remaining", action="store_true",
                    help="訳のある文を除く（データベースを --translations 付きで作っておくこと）")
    ap.add_argument("--version", default="v1", help="依頼文の版（prompts/<版>.md）")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out", help="書き出すフォルダ。省略すると画面に出す")
    ap.add_argument("--db", default=os.path.join(REPO, "build", "pali.sqlite"))
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    template = load_template(args.version)
    done = pw.translated_ids(con, args.translator) if args.remaining else set()

    if args.uid.startswith("U"):
        unit = next((u for u in pw.load_units() if u["unit"] == args.uid), None)
        if not unit:
            raise SystemExit(f"{args.uid} が見つからない")
        con.row_factory = sqlite3.Row
        seg_rows = pw.unit_segments(con, unit)
        jobs = []
        for t in unit["texts"]:
            rows = [r for r in seg_rows if r["text_uid"] == t and r["segment_id"] not in done
                    and not (args.remaining and not r["pali"])]
            if rows:
                jobs.append((t, rows))
    else:
        jobs = []
        for t in texts_under(con, args.uid):
            rows = con.execute("SELECT segment_id, pali FROM segment WHERE text_uid=? ORDER BY seq", (t,)).fetchall()
            rows = [r for r in rows if r[0] not in done]
            if rows:
                jobs.append((t, rows))
    if not jobs:
        raise SystemExit(f"{args.uid} に訳すべき文がない（見つからないか、すべて訳済み）")

    for u, rows in jobs:
        prompt = make(con, template, u, args.translator, args.version, args.date, rows)
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            with open(os.path.join(args.out, f"{u}.md"), "w", encoding="utf-8") as f:
                f.write(prompt)
        else:
            print(prompt)
    if args.out:
        print(json.dumps({"texts": len(jobs), "out": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
