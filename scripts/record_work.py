#!/usr/bin/env python3
"""1回の作業を、訳リポジトリの log/work.tsv に1行記録する。

記録すること：日付、作業単位、この回に訳した文の数と原文の字数、要確認の数、作業単位の残り、メモ。
使用量と見比べて、1回分の字数（ledger/plan.json の unit_chars）を決めるのに使う。

使い方（訳を保存したあと、データベースを作り直してから）:
    python3 scripts/build_db.py --translations ../pali-ja-claude
    python3 scripts/record_work.py --repo ../pali-ja-claude --unit U00001 \
        --segments 210 --chars 14800 --note "途中で終了"
"""
import argparse
import csv
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paliwork as pw  # noqa: E402

FIELDS = ["date", "translator", "unit", "segments", "pali_chars", "uncertain", "unit_remaining", "note"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--segments", type=int, required=True, help="この回に訳した文の数")
    ap.add_argument("--chars", type=int, required=True, help="この回に訳した原文の字数")
    ap.add_argument("--uncertain", type=int, default=0, help="この回に挙げた要確認の数")
    ap.add_argument("--translator", default=pw.DEFAULT_TRANSLATOR)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    con = pw.connect()
    unit = next((u for u in pw.load_units() if u["unit"] == args.unit), None)
    if not unit:
        raise SystemExit(f"{args.unit} がない")
    d, n = pw.Progress(con, args.translator).unit_status(unit)

    path = os.path.join(args.repo, "log", "work.tsv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        if new:
            w.writerow(FIELDS)
        w.writerow([args.date, args.translator, args.unit, args.segments, args.chars,
                    args.uncertain, n - d, args.note])
    print(f"記録しました：{args.unit} {args.segments}文 {args.chars:,}字（作業単位の残り {n - d}文）")


if __name__ == "__main__":
    main()
