#!/usr/bin/env python3
"""訳者ごとの用語集と要確認の一覧を、訳文のJSONから作る。

訳文ファイルの terms（訳語と選んだ理由）と uncertain（迷った点）は経典ごとに分かれている。
このスクリプトはそれをすべて集めて、次の3つのファイルを訳リポジトリに書き出す。

  terms/ja/<訳者ID>/用語集.md            訳語のゆれと、同じ訳語の共有の一覧、見出し語の目次
  terms/ja/<訳者ID>/用語集/<頭文字>.md   見出し語ごとの訳語・理由・出てくる経典（a.md、b.md …）
  terms/ja/<訳者ID>/用語集.json          同じ内容を機械で読める形で（Git には入れない。.gitignore）
  terms/ja/<訳者ID>/要確認一覧.md        目次（部ごとの件数）
  terms/ja/<訳者ID>/要確認一覧/<区分>.md uncertain に挙げた箇所を、原文と訳文つきで経典順に
                                         （区分：相応部は相応ごと sn12、増支部は集ごと an4、中部は五十経ごと mn1-50、長部は品ごと dn1-13、ほかは部ごと）
  terms/ja/<訳者ID>/同文異訳一覧.md      目次（部ごとの件数）
  terms/ja/<訳者ID>/同文異訳一覧/<部>.md 原文が同じ文なのに訳が違うもの（最初に出た経典の部に入れる）

全体を探すときは、ファイルを開かずにデータベース（build/pali.sqlite の translation・term・uncertain の表）を使う。
2026-11-11 に、ファイルが大きくなりすぎないよう分けた（それまでは1つのファイル）。

手で直さない（毎回作り直す）。訳語について決めたことは、同じフォルダの 決定事項.md に手で書く。

使い方:
    python3 scripts/make_glossary.py --repo ../pali-ja-claude
    python3 scripts/make_glossary.py --repo ../pali-ja-claude --check   # ゆれの数だけ表示し、書き出さない

原文と照らすため、先に scripts/build_db.py でデータベースを作っておく（なければ原文なしで作る）。
他の訳者の訳は読まない。--repo に指定した訳リポジトリの、指定した訳者の訳だけを読む。
"""
import argparse
import datetime
import glob
import json
import os
import re
import sqlite3
import unicodedata
from collections import OrderedDict, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "build", "pali.sqlite")
DEFAULT_TRANSLATOR = "claude-opus-5.5"
COLLECTION_ORDER = ["dn", "mn", "sn", "an", "kp", "dhp", "ud", "iti", "snp", "vv", "pv",
                    "thag", "thig", "tha-ap", "thi-ap", "bv", "cp", "ja", "mnd", "cnd",
                    "ps", "ne", "pe", "mil", "pli-tv", "ds", "vb", "dt", "pp", "kv", "ya", "patthana"]


def uid_key(uid):
    """sn1.2 < sn1.10 < sn2.1 < sn56.1 となる並び順。"""
    m = re.match(r"([a-z\-]+)(.*)", uid)
    coll, rest = (m.group(1), m.group(2)) if m else (uid, "")
    order = COLLECTION_ORDER.index(coll) if coll in COLLECTION_ORDER else len(COLLECTION_ORDER)
    nums = [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", rest) if x not in ("", ".", "-")]
    return (order, coll, [(0, n) if isinstance(n, int) else (1, n) for n in nums])


def seg_key(seg):
    uid, _, num = seg.partition(":")
    return (uid_key(uid), [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", num)])


def coll_of(uid):
    """経典 id から部の名前を取り出す（sn12.1 → sn、pli-tv-bu-vb-pj1 → pli-tv-bu-vb-pj）。"""
    m = re.match(r"([a-z\-]+?)(\d|$)", uid)
    return m.group(1) if m else uid


def part_of(uid):
    """要確認一覧の区分。相応部は相応ごと、増支部は集ごと、ほかは部ごと。"""
    m = re.match(r"([a-z\-]+?)(\d+)", uid)
    if m and m.group(1) in ("sn", "an"):
        return m.group(1) + m.group(2)
    if m and m.group(1) in PART_RANGES:
        n = int(m.group(2))
        for a, b in PART_RANGES[m.group(1)]:
            if a <= n <= b:
                return f"{m.group(1)}{a}-{b}"
    return coll_of(uid)


# 中部は三つの五十経、長部は三つの品で分ける
PART_RANGES = {"mn": [(1, 50), (51, 100), (101, 152)], "dn": [(1, 13), (14, 23), (24, 34)]}


def part_sort(name):
    return uid_key(name if re.search(r"\d", name) else name + "0")


def clear_dir(d):
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(os.path.join(d, "*.md")):
        os.remove(f)


def pali_sort(term):
    s = unicodedata.normalize("NFD", term.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def norm_key(term):
    """「chanda（韻律）」「agha（苦悩）」の（ ）を外して、同じ語として比べる。"""
    return re.sub(r"[（(].*?[）)]", "", term).strip()


def split_pairs(term, ja):
    """「a / b」と「x／y」の組を、数が合えば一語ずつに分ける。"""
    ps = [p.strip() for p in re.split(r"\s*/\s*", term)]
    js = [j.strip() for j in re.split(r"\s*／\s*", ja)]
    if len(ps) > 1 and len(ps) == len(js):
        return list(zip(ps, js))
    return [(term, ja)]


def load_translations(repo, translator):
    base = os.path.join(repo, "translation", "ja", translator)
    files = glob.glob(os.path.join(base, "**", "*.json"), recursive=True)
    docs = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        d["_uid"] = d.get("text_uid") or os.path.splitext(os.path.basename(f))[0]
        docs.append(d)
    docs.sort(key=lambda d: uid_key(d["_uid"]))
    return docs


def build(docs):
    # entries[term] = {ja: {reasons: OrderedDict(reason -> [uid...]), texts: [uid...]}}
    entries = OrderedDict()
    for d in docs:
        uid = d["_uid"]
        for term, v in (d.get("terms") or {}).items():
            ja = (v.get("ja") or "").strip()
            reason = (v.get("reason") or "").strip()
            e = entries.setdefault(term, OrderedDict())
            j = e.setdefault(ja, {"reasons": OrderedDict(), "texts": []})
            j["texts"].append(uid)
            j["reasons"].setdefault(reason, []).append(uid)
    # 訳語のゆれ：（ ）を外し、組を一語ずつに分けたうえで、同じパーリ語に違う訳語があるもの
    words = defaultdict(lambda: OrderedDict())
    for term, e in entries.items():
        for ja, j in e.items():
            for p, jj in split_pairs(term, ja):
                words[norm_key(p)].setdefault(jj, []).append((term, j["texts"][0]))
    variants = OrderedDict((w, v) for w, v in sorted(words.items(), key=lambda x: pali_sort(x[0])) if len(v) > 1)
    # 同じ訳語を違うパーリ語に付けたもの（例 kodha と dosa をどちらも「怒り」）
    by_ja = defaultdict(lambda: OrderedDict())
    for w, v in words.items():
        for jj, occ in v.items():
            by_ja[jj].setdefault(w, occ[0][1])
    shared = OrderedDict((ja, v) for ja, v in sorted(by_ja.items()) if len(v) > 1)
    return entries, variants, shared


def write_entry(term, e):
    lines = [f"### {term}", ""]
    for ja, j in e.items():
        texts = list(OrderedDict.fromkeys(j["texts"]))
        lines.append(f"- **{ja}**")
        for reason, uids in j["reasons"].items():
            u = list(OrderedDict.fromkeys(uids))
            lines.append(f"  - 理由（{u[0]}" + (f" ほか{len(u) - 1}" if len(u) > 1 else "") + f"）：{reason or '（記載なし）'}")
        lines.append(f"  - 出てくる経典（{len(texts)}）：" + "、".join(texts))
    lines.append("")
    return lines


def write_index(path, title, translator, intro, counts, sub, unit):
    today = datetime.date.today().isoformat()
    lines = [f"# {title}（{translator}）", "",
             f"作成日：{today}（scripts/make_glossary.py が自動で作る。手で直さない）", ""] + intro + [
             "", f"| 区分 | {unit} |", "| --- | --- |"]
    for k, n in counts.items():
        lines.append(f"| [{k}]({sub}/{k}.md) | {n} |")
    lines.append(f"| 計 | {sum(counts.values())} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def write_glossary(path_md, path_json, translator, docs, entries, variants, shared):
    today = datetime.date.today().isoformat()
    n_texts = len(docs)
    lines = [
        f"# 用語集（{translator}）",
        "",
        f"作成日：{today}（scripts/make_glossary.py が訳文から自動で作る。手で直さない）",
        "",
        f"訳した経典 {n_texts} 本の訳文ファイルにある terms（訳語と選んだ理由）をすべて集めたもの。"
        f"見出し語 {len(entries)} 語、訳語のゆれ {len(variants)} 語、同じ訳語を共有するもの {len(shared)} 組。",
        "",
        "- 並びはパーリ語のローマ字順（長音記号などを外して並べる）。",
        "- 「出てくる経典」は、その訳語を terms に書いた経典。本文中でその語が出る箇所すべてではない。",
        "- 同じ語に理由が複数あるときは、書いた経典ごとに並べる。",
        "- 訳語について決めたこと・保留していることは、同じフォルダの 決定事項.md にある。",
        "",
        "## 1. 訳語のゆれ（同じパーリ語に違う訳語を付けたもの）",
        "",
        "文脈によって意図して訳し分けたものと、そろえるべきものとが混じっている。判断は 決定事項.md に記録する。",
        "",
    ]
    if variants:
        lines += ["| パーリ語 | 訳語（最初に付けた経典） |", "| --- | --- |"]
        for w, v in variants.items():
            cells = "<br>".join(f"{ja}（{occ[0][1]}" + (f"、見出し「{occ[0][0]}」" if occ[0][0] != w else "") + "）"
                                for ja, occ in v.items())
            lines.append(f"| {w} | {cells} |")
    else:
        lines.append("なし。")
    lines += ["", "## 2. 同じ訳語を違うパーリ語に付けたもの", "",
              "原語の違いが日本語では見えなくなる箇所。意図したものかどうかは 決定事項.md に記録する。", ""]
    if shared:
        lines += ["| 訳語 | パーリ語（最初に付けた経典） |", "| --- | --- |"]
        for ja, v in shared.items():
            lines.append(f"| {ja} | " + "<br>".join(f"{w}（{u}）" for w, u in v.items()) + " |")
    else:
        lines.append("なし。")
    letters = OrderedDict()
    for term in sorted(entries, key=pali_sort):
        k = pali_sort(term)[:1]
        letters.setdefault(k if k.isascii() and k.isalpha() else "その他", []).append(term)
    lines += ["", "## 3. 見出し語", "",
              "見出し語は頭文字ごとのファイル（用語集/a.md など）にある。長音記号などは外して並べる。", ""]
    lines += ["| 頭文字 | 語の数 |", "| --- | --- |"]
    for k, ts in letters.items():
        lines.append(f"| [{k}](用語集/{k}.md) | {len(ts)} |")
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    sub = os.path.join(os.path.dirname(path_md), "用語集")
    clear_dir(sub)
    for k, ts in letters.items():
        lines = [f"# 用語集 {k}（{translator}）", "",
                 f"作成日：{today}（scripts/make_glossary.py が訳文から自動で作る。手で直さない）。目次とゆれの一覧は ../用語集.md", ""]
        for term in ts:
            lines += write_entry(term, entries[term])
        with open(os.path.join(sub, f"{k}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")

    data = {
        "translator": translator,
        "generated": today,
        "texts": n_texts,
        "terms": {t: [{"ja": ja,
                       "reasons": [{"reason": r, "texts": list(OrderedDict.fromkeys(u))} for r, u in j["reasons"].items()],
                       "texts": list(OrderedDict.fromkeys(j["texts"]))}
                      for ja, j in entries[t].items()]
                  for t in sorted(entries, key=pali_sort)},
        "shared": {ja: [{"pali": w, "first": u} for w, u in v.items()] for ja, v in shared.items()},
        "variants": {w: [{"ja": ja, "first": occ[0][1], "heading": occ[0][0]} for ja, occ in v.items()]
                     for w, v in variants.items()},
    }
    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def write_uncertain(path, translator, docs, con):
    today = datetime.date.today().isoformat()
    items = []
    for d in docs:
        for u in d.get("uncertain") or []:
            items.append((d, u))
    items.sort(key=lambda x: seg_key(x[1].get("segment", x[0]["_uid"] + ":0")))
    sub = os.path.join(os.path.dirname(path), "要確認一覧")
    clear_dir(sub)
    parts = OrderedDict()
    for d, u in items:
        parts.setdefault(part_of(d["_uid"]), []).append((d, u))
    parts = OrderedDict(sorted(parts.items(), key=lambda kv: part_sort(kv[0])))
    write_index(path, "要確認の一覧", translator, [
        f"訳者が自信のない点として挙げた箇所 {len(items)} 件。パーリ語の読める人に確認してもらうときの手がかりにする。",
        "確認の結果は将来 review に記録する（方針とルール 第3章）。",
        "区分ごとのファイル（要確認一覧/sn12.md など）に、原文・訳文つきで経典順に並べてある。"
        "相応部は相応ごと、増支部は集ごと、中部は五十経ごと、長部は品ごと、ほかは部ごと。全体を探すときはデータベースの uncertain の表を使う。"],
        OrderedDict((k, len(v)) for k, v in parts.items()), "要確認一覧", "件数")
    for part, its in parts.items():
        write_uncertain_part(os.path.join(sub, f"{part}.md"), part, translator, today, its, con)
    return len(items)


def write_uncertain_part(path, part, translator, today, items, con):
    lines = [
        f"# 要確認の一覧 {part}（{translator}）",
        "",
        f"作成日：{today}（scripts/make_glossary.py が訳文の uncertain から自動で作る。手で直さない）。目次は ../要確認一覧.md",
        "",
        f"{len(items)} 件。",
        "",
    ]
    cur = None
    for d, u in items:
        uid = d["_uid"]
        if uid != cur:
            cur = uid
            lines += [f"## {uid}", ""]
        seg = u.get("segment", "")
        lines.append(f"### {seg}")
        lines.append("")
        if con is not None and seg:
            row = con.execute("select pali from segment where segment_id=?", (seg,)).fetchone()
            if row:
                lines.append(f"- 原文：{row[0]}")
        ja = (d.get("segments") or {}).get(seg)
        if ja is not None:
            lines.append(f"- 訳文：{ja}")
        lines.append(f"- 迷った点：{u.get('note', '')}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def write_same_text(path, translator, docs, con):
    """原文が同じ（句読点と大小文字を除いて一致する）文で、訳が違うものを一覧にする。"""
    today = datetime.date.today().isoformat()
    tr = {}
    for d in docs:
        tr.update(d.get("segments") or {})
    groups = defaultdict(lambda: OrderedDict())
    for sid in sorted(tr, key=seg_key):
        if ":0." in sid:  # 経典番号・品名・経名の見出しは除く
            continue
        row = con.execute("select pali from segment where segment_id=?", (sid,)).fetchone()
        if not row or not row[0].strip():
            continue
        key = re.sub(r"[“”‘’\"'—;:,.?!()]", "", row[0]).lower().strip()
        ja = re.sub(r"[「」『』。、\s]", "", tr[sid])
        ja = re.sub(r"と$", "", ja)  # 引用の終わりの「と」だけの違いは同じとみなす
        g = groups[key]
        g.setdefault(ja, {"pali": row[0], "segs": [], "text": tr[sid]})["segs"].append(sid)
    diff = [(k, v) for k, v in groups.items() if len(v) > 1]
    diff.sort(key=lambda kv: seg_key(next(iter(kv[1].values()))["segs"][0]))
    parts = OrderedDict()
    for k, v in diff:
        first = next(iter(v.values()))
        parts.setdefault(coll_of(first["segs"][0].partition(":")[0]), []).append(v)
    parts = OrderedDict(sorted(parts.items(), key=lambda kv: part_sort(kv[0])))
    sub = os.path.join(os.path.dirname(path), "同文異訳一覧")
    clear_dir(sub)
    write_index(path, "同文異訳の一覧", translator, [
        f"原文が同じ文（句読点・大文字小文字・引用符を除いて一致）なのに、訳が違うもの {len(diff)} 件。",
        "問いと答えで語尾が変わるなど文脈による違いも含む。そろえるべきものかどうかは 決定事項.md に記録する。",
        "引用の終わりの「と」と、句読点・かぎかっこだけの違いは、同じ訳とみなして除いた。",
        "部ごとのファイル（同文異訳一覧/mn.md など）にある。どの部に入れるかは、その原文の訳が最初に出た経典で決める。"],
        OrderedDict((k, len(v)) for k, v in parts.items()), "同文異訳一覧", "件数")
    for part, vs in parts.items():
        lines = [
            f"# 同文異訳の一覧 {part}（{translator}）",
            "",
            f"作成日：{today}（scripts/make_glossary.py が自動で作る。手で直さない）。目次と説明は ../同文異訳一覧.md",
            "",
            f"{len(vs)} 件。",
            "",
        ]
        for v in vs:
            first = next(iter(v.values()))
            lines += [f"## {first['pali']}", ""]
            for ja, x in v.items():
                lines.append(f"- {x['text']}（{'、'.join(x['segs'])}）")
            lines.append("")
        with open(os.path.join(sub, f"{part}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
    return len(diff)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="訳リポジトリのフォルダ（例 ../pali-ja-claude）")
    ap.add_argument("--translator", default=DEFAULT_TRANSLATOR)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--check", action="store_true", help="書き出さずに件数とゆれだけ表示する")
    args = ap.parse_args()

    docs = load_translations(args.repo, args.translator)
    entries, variants, shared = build(docs)
    print(f"経典 {len(docs)} 本 / 見出し語 {len(entries)} / 訳語のゆれ {len(variants)} / 同じ訳語の共有 {len(shared)}")
    if args.check:
        for w, v in variants.items():
            print(f"  {w}: " + " ／ ".join(f"{ja}（{occ[0][1]}）" for ja, occ in v.items()))
        for ja, v in shared.items():
            print(f"  「{ja}」: " + " ／ ".join(f"{w}（{u}）" for w, u in v.items()))
        return
    out = os.path.join(args.repo, "terms", "ja", args.translator)
    os.makedirs(out, exist_ok=True)
    write_glossary(os.path.join(out, "用語集.md"), os.path.join(out, "用語集.json"),
                   args.translator, docs, entries, variants, shared)
    con = sqlite3.connect(args.db) if os.path.exists(args.db) else None
    n = write_uncertain(os.path.join(out, "要確認一覧.md"), args.translator, docs, con)
    m = write_same_text(os.path.join(out, "同文異訳一覧.md"), args.translator, docs, con) if con is not None else 0
    print(f"書き出しました：{out}/用語集（.md・/・.json）・要確認一覧（.md・/。要確認 {n} 件）・同文異訳一覧（.md・/。{m} 件）")


if __name__ == "__main__":
    main()
