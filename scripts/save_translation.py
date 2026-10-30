#!/usr/bin/env python3
"""訳文のJSON（依頼文の「出力」の形）を、訳リポジトリの決まった場所に保存する。

  - すでにある訳文ファイルには、新しい文だけを足す（途中から再開したとき用）。
  - すでに訳がある文を別の訳で上書きしようとしたら止める（確定した訳は書き換えない）。
  - 文の順番は原文の順にそろえる。
  - terms と uncertain は足し合わせる。

使い方:
    python3 scripts/save_translation.py --repo ../pali-ja-claude 新しい訳.json [...]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paliwork as pw  # noqa: E402


def merge(con, repo, data):
    tid = data["translator"]
    text_uid = data["text_uid"]
    dest = pw.translation_path(con, repo, tid, text_uid)
    old = {}
    if os.path.exists(dest):
        with open(dest, encoding="utf-8") as f:
            old = json.load(f)
    segs = dict(old.get("segments", {}))
    for sid, ja in data["segments"].items():
        if sid in segs and segs[sid].strip() and segs[sid] != ja:
            raise SystemExit(f"{sid} にはすでに別の訳がある。確定した訳は書き換えない（直すなら新しい依頼文の版で）")
        segs[sid] = ja
    order = [r[0] for r in con.execute("SELECT segment_id FROM segment WHERE text_uid=? ORDER BY seq", (text_uid,))]
    unknown = [s for s in segs if s not in order]
    if unknown:
        raise SystemExit(f"原文にない区切り番号：{', '.join(unknown[:10])}")
    terms = dict(old.get("terms", {}))
    for k, v in (data.get("terms") or {}).items():
        terms.setdefault(k, v)
    uncertain = list(old.get("uncertain", []))
    seen = {(u["segment"], u.get("note")) for u in uncertain}
    for u in data.get("uncertain") or []:
        if (u["segment"], u.get("note")) not in seen:
            uncertain.append(u)
    out = {
        "translator": tid,
        "date": old.get("date") or data["date"],
        "updated": data["date"],
        "prompt_version": data["prompt_version"],
        "text_uid": text_uid,
        "segments": {s: segs[s] for s in order if s in segs},
        "terms": terms,
        "uncertain": uncertain,
    }
    if old and old.get("prompt_version") != data["prompt_version"]:
        raise SystemExit(f"{text_uid} は依頼文 {old.get('prompt_version')} で訳し始めている。版を混ぜない")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    need = sum(1 for r in con.execute("SELECT pali FROM segment WHERE text_uid=?", (text_uid,)) if r[0])
    have = sum(1 for s, ja in out["segments"].items() if ja.strip())
    print(f"{os.path.relpath(dest, repo)}：{have}/{need}文")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="訳リポジトリのフォルダ（例 ../pali-ja-claude）")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    con = pw.connect()
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            merge(con, args.repo, json.load(f))


if __name__ == "__main__":
    main()
