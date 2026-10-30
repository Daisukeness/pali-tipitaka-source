#!/usr/bin/env python3
"""翻訳の進み具合と、次にやる作業単位を表示する。

先に訳文を入れたデータベースを作っておくこと:
    python3 scripts/build_db.py --translations ../pali-ja-claude

使い方:
    python3 scripts/progress.py                  # 全体の進み具合と次の作業単位
    python3 scripts/progress.py --unit U00003    # 作業単位の中身と残り
    python3 scripts/progress.py --translator claude-opus-5.5
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paliwork as pw  # noqa: E402


def pct(a, b):
    return f"{(100.0 * a / b):.1f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--translator", default=pw.DEFAULT_TRANSLATOR)
    ap.add_argument("--unit", help="この作業単位の中身を表示")
    args = ap.parse_args()

    con = pw.connect()
    units = pw.load_units()
    prog = pw.Progress(con, args.translator)

    if args.unit:
        unit = next((u for u in units if u["unit"] == args.unit), None)
        if not unit:
            raise SystemExit(f"{args.unit} がない")
        done_ids = pw.translated_ids(con, args.translator)
        print(f"{unit['unit']}  {unit['pali_chars']:,}字  {unit['segments']:,}文")
        for t in unit["texts"]:
            print(f"  {t}: {prog.state(t)}（{prog.text_done.get(t, 0) if t in prog.any_done else 0}/{prog.text_total[t]}文）")
        if unit["seg_from"]:
            print(f"  範囲 {unit['seg_from']} 〜 {unit['seg_to']}")
        rows = [r for r in pw.unit_segments(con, unit) if r["pali"] and r["segment_id"] not in done_ids]
        print(f"  残り {len(rows):,}文" + (f"（次は {rows[0]['segment_id']} から）" if rows else ""))
        return

    tree = prog.subtree()
    top = [r["uid"] for r in con.execute("SELECT uid FROM node WHERE parent_uid IS NULL ORDER BY sort")]
    all_chars = sum(tree[u]["chars"] for u in top)
    all_done = sum(tree[u]["done_chars"] for u in top)
    print(f"訳者 {args.translator}：全体 {all_done:,} / {all_chars:,} 字（{pct(all_done, all_chars)}）")
    for u in ["dn", "mn", "sn", "an", "kn", "vinaya", "abhidhamma"]:
        s = tree.get(u)
        if s:
            print(f"  {u:<11} {s['done_texts']:>5,} / {s['texts']:>5,} 経  "
                  f"{s['done_chars']:>11,} / {s['chars']:>11,} 字（{pct(s['done_chars'], s['chars'])}）"
                  + (f"  翻訳中 {s['partial_texts']}" if s["partial_texts"] else ""))

    unit, d, n = prog.next_unit(units)
    if unit:
        idx = units.index(unit) + 1
        print(f"\n次の作業単位：{unit['unit']}（{idx:,} / {len(units):,}）"
              f"  {unit['pali_chars']:,}字  残り {n - d:,} / {n:,}文")
        print(f"  経典：{', '.join(unit['texts'])}" + (f"  範囲 {unit['seg_from']}〜{unit['seg_to']}" if unit["seg_from"] else ""))
        print(f"  依頼文：python3 scripts/make_prompt.py {unit['unit']} --remaining")
    else:
        print("\nすべての作業単位が終わっている")


if __name__ == "__main__":
    main()
