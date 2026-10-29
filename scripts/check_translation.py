#!/usr/bin/env python3
"""訳文のJSONを原文と照らして機械的に確かめる。

確かめること:
  - 必須の項目（translator, date, prompt_version, segments）があるか
  - 区切り番号の過不足（原文にあって訳にない／訳にあって原文にない）
  - 原文があるのに訳が空欄
  - 原文の …pe… と訳の〔中略〕の数が合うか
  - 原文が空なのに訳が入っている

使い方:
    python3 scripts/check_translation.py 訳文.json [訳文.json ...]
    python3 scripts/check_translation.py ../pali-ja-claude/translation   # フォルダごと

問題がなければ終了コード 0、あれば 1。
"""
import glob
import json
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ["translator", "date", "prompt_version", "segments"]


def check_file(con, path):
    problems = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [f"JSONとして読めない: {e}"]

    for key in REQUIRED:
        if key not in data:
            problems.append(f"項目 {key} がない")
    segs = data.get("segments") or {}
    text_uid = data.get("text_uid") or os.path.basename(path)[:-5]

    rows = con.execute("SELECT segment_id, pali FROM segment WHERE text_uid=? ORDER BY seq", (text_uid,)).fetchall()
    if not rows:
        return problems + [f"原文に {text_uid} がない"]
    pali = dict(rows)

    missing = [s for s, _ in rows if s not in segs]
    extra = [s for s in segs if s not in pali]
    if missing:
        problems.append(f"訳がない区切り {len(missing)} 件: {', '.join(missing[:10])}")
    if extra:
        problems.append(f"原文にない区切り {len(extra)} 件: {', '.join(extra[:10])}")

    for sid, src in rows:
        ja = segs.get(sid)
        if ja is None:
            continue
        if src and not ja.strip():
            problems.append(f"{sid}: 訳が空欄")
        if not src and ja.strip():
            problems.append(f"{sid}: 原文は空なのに訳がある")
        n_pe = src.count("…pe…")
        n_ja = ja.count("〔中略〕")
        if n_pe != n_ja:
            problems.append(f"{sid}: …pe… が {n_pe} 個、〔中略〕が {n_ja} 個")
    return problems


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    con = sqlite3.connect(os.path.join(REPO, "build", "pali.sqlite"))
    files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            files += sorted(glob.glob(os.path.join(arg, "**", "*.json"), recursive=True))
        else:
            files.append(arg)
    bad = 0
    for path in files:
        problems = check_file(con, path)
        if problems:
            bad += 1
            print(f"✗ {path}")
            for p in problems:
                print(f"    {p}")
    print(f"{len(files)} 件中 {len(files) - bad} 件問題なし")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
