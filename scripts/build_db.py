#!/usr/bin/env python3
"""パーリ語原文から SQLite データベース（build/pali.sqlite）を作り直す。

使い方:
    python3 scripts/build_db.py                      # 原文だけ
    python3 scripts/build_db.py --translations ../pali-ja-claude
                                                      # 訳リポジトリも取り込む（複数可）

データベースは毎回ゼロから作る。直接編集しない。
標準ライブラリだけで動く。
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.join(REPO, "root", "pli", "ms")
REF_DIR = os.path.join(REPO, "reference", "pli", "ms")
VAR_DIR = os.path.join(REPO, "variant", "pli", "ms")
NAME_DIR = os.path.join(REPO, "root", "misc", "site", "name")
TREE_DIR = os.path.join(REPO, "sc-data", "structure", "tree")
PARALLELS = os.path.join(REPO, "sc-data", "relationship", "parallels.json")

SCHEMA = """
CREATE TABLE node (
    uid TEXT PRIMARY KEY,
    parent_uid TEXT,
    depth INTEGER NOT NULL,
    sort INTEGER NOT NULL,
    pali_title TEXT,
    is_text INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE text (
    uid TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    segments INTEGER NOT NULL,
    pali_chars INTEGER NOT NULL
);
CREATE TABLE segment (
    segment_id TEXT PRIMARY KEY,
    text_uid TEXT NOT NULL,
    seq INTEGER NOT NULL,
    pali TEXT NOT NULL,
    reference TEXT,
    variant TEXT
);
CREATE INDEX segment_text ON segment(text_uid, seq);
CREATE TABLE parallel (
    text_uid TEXT NOT NULL,
    other TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE INDEX parallel_text ON parallel(text_uid);
CREATE TABLE translator (
    id TEXT PRIMARY KEY,
    name TEXT,
    vendor TEXT,
    model TEXT
);
CREATE TABLE prompt (
    id TEXT PRIMARY KEY,
    version TEXT,
    body TEXT
);
CREATE TABLE translation (
    segment_id TEXT NOT NULL,
    translator_id TEXT NOT NULL,
    prompt_id TEXT,
    ja TEXT NOT NULL,
    created_at TEXT,
    PRIMARY KEY (segment_id, translator_id)
);
CREATE TABLE term_choice (
    text_uid TEXT NOT NULL,
    translator_id TEXT NOT NULL,
    pali_term TEXT NOT NULL,
    ja_term TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE uncertain (
    segment_id TEXT NOT NULL,
    translator_id TEXT NOT NULL,
    note TEXT
);
CREATE TABLE review (
    segment_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    verdict TEXT,
    note TEXT
);
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def uid_from_file(path, suffix):
    return os.path.basename(path)[: -len(suffix)]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_names():
    names = {}
    for path in glob.glob(os.path.join(NAME_DIR, "**", "*.json"), recursive=True):
        for key, value in load_json(path).items():
            # 例 "sn-name:4.sn1.1": "Oghataraṇasutta"
            uid = key.split(":", 1)[1].split(".", 1)[1]
            names[uid] = value.strip()
    return names


def load_texts():
    """{text_uid: ファイルパス} を返す。"""
    texts = {}
    for path in glob.glob(os.path.join(ROOT_DIR, "**", "*_root-pli-ms.json"), recursive=True):
        texts[uid_from_file(path, "_root-pli-ms.json")] = path
    return texts


def side_file(base_dir, rel_dir, uid, suffix):
    path = os.path.join(base_dir, rel_dir, uid + suffix)
    return load_json(path) if os.path.exists(path) else {}


def walk_tree(obj, parent, depth, out):
    """sc-data の入れ子構造を (uid, parent, depth) の並びにする。"""
    if isinstance(obj, str):
        out.append((obj, parent, depth))
    elif isinstance(obj, list):
        for item in obj:
            walk_tree(item, parent, depth, out)
    elif isinstance(obj, dict):
        for uid, children in obj.items():
            out.append((uid, parent, depth))
            walk_tree(children, uid, depth + 1, out)


def load_tree():
    """super-tree と各コレクションの木をつないで一本の木にする。"""
    super_rows = []
    walk_tree(load_json(os.path.join(TREE_DIR, "super-tree.json")), None, 0, super_rows)
    rows = []
    for uid, parent, depth in super_rows:
        rows.append((uid, parent, depth))
        for path in glob.glob(os.path.join(TREE_DIR, "*", uid + "-tree.json")):
            sub = []
            walk_tree(load_json(path), parent, depth, sub)
            # 先頭はコレクション自身（uid）なので重複させない
            rows.extend(r for r in sub if r[0] != uid or r[1] != parent)
    return rows


def build(db_path, translation_dirs):
    names = load_names()
    texts = load_texts()

    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    # --- 木（パーリ語の原文がある枝だけ残す） ---
    rows = load_tree()
    parent_of, depth_of, order = {}, {}, []
    for uid, parent, depth in rows:
        if uid in parent_of:
            continue  # dhp など複数の場所に出るものは最初の位置を使う
        parent_of[uid] = parent
        depth_of[uid] = depth
        order.append(uid)
    keep = set()
    for uid in texts:
        node = uid
        while node is not None and node not in keep:
            keep.add(node)
            node = parent_of.get(node)
    orphans = sorted(u for u in texts if u not in parent_of)
    sort = 0
    for uid in order:
        if uid in keep:
            sort += 1
            con.execute(
                "INSERT INTO node VALUES (?,?,?,?,?,?)",
                (uid, parent_of[uid], depth_of[uid], sort, names.get(uid), int(uid in texts)),
            )
    for uid in orphans:
        sort += 1
        con.execute("INSERT INTO node VALUES (?,?,?,?,?,1)", (uid, None, 0, sort, names.get(uid)))

    # --- 原文の一文ずつ ---
    total_segments = 0
    for uid, path in sorted(texts.items()):
        rel_dir = os.path.relpath(os.path.dirname(path), ROOT_DIR)
        root = load_json(path)
        ref = side_file(REF_DIR, rel_dir, uid, "_reference.json")
        var = side_file(VAR_DIR, rel_dir, uid, "_variant-pli-ms.json")
        chars = 0
        for seq, (sid, pali) in enumerate(root.items(), 1):
            pali = pali.strip()
            chars += len(pali)
            con.execute(
                "INSERT INTO segment VALUES (?,?,?,?,?,?)",
                (sid, uid, seq, pali, ref.get(sid) or None, (var.get(sid) or "").strip() or None),
            )
        con.execute(
            "INSERT INTO text VALUES (?,?,?,?)",
            (uid, os.path.relpath(path, REPO), len(root), chars),
        )
        total_segments += len(root)

    # --- 対応経典（漢訳阿含経など） ---
    for entry in load_json(PARALLELS):
        for kind, items in entry.items():
            uids = [re.sub(r"^~", "", i).split("#", 1)[0] for i in items]
            for a in set(uids):
                if a in texts:
                    for i, b in zip(items, uids):
                        if b != a:
                            con.execute("INSERT INTO parallel VALUES (?,?,?)", (a, i, kind))

    # --- 訳文 ---
    n_trans = 0
    for tdir in translation_dirs:
        n_trans += load_translations(con, tdir)

    con.execute("INSERT INTO meta VALUES ('source_commits', ?)", (read_commits(),))
    con.commit()

    n_texts = len(texts)
    n_nodes = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    print(f"経典 {n_texts:,} / 文 {total_segments:,} / 木の節 {n_nodes:,} / 訳文 {n_trans:,}")
    if orphans:
        print(f"木に載っていない経典 {len(orphans)} 件（最上位に置いた）: {', '.join(orphans[:10])}")
    con.close()


def load_translations(con, tdir):
    """訳リポジトリの translation/ja/<訳者ID>/**/*.json を取り込む。"""
    count = 0
    for path in sorted(glob.glob(os.path.join(tdir, "translation", "ja", "*", "**", "*.json"), recursive=True)):
        data = load_json(path)
        tid = data["translator"]
        con.execute(
            "INSERT OR IGNORE INTO translator VALUES (?,?,?,?)",
            (tid, data.get("translator_name", tid), data.get("vendor"), data.get("model", tid)),
        )
        text_uid = data.get("text_uid") or os.path.basename(path)[:-5]
        for sid, ja in data["segments"].items():
            con.execute(
                "INSERT OR REPLACE INTO translation VALUES (?,?,?,?,?)",
                (sid, tid, data.get("prompt_version"), ja, data.get("date")),
            )
            count += 1
        for term, t in (data.get("terms") or {}).items():
            con.execute(
                "INSERT INTO term_choice VALUES (?,?,?,?,?)",
                (text_uid, tid, term, t.get("ja", ""), t.get("reason")),
            )
        for u in data.get("uncertain") or []:
            con.execute("INSERT INTO uncertain VALUES (?,?,?)", (u["segment"], tid, u.get("note")))
    return count


def read_commits():
    path = os.path.join(REPO, "SOURCES.md")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return " ".join(re.findall(r"\b[0-9a-f]{40}\b", f.read()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.path.join(REPO, "build", "pali.sqlite"))
    ap.add_argument("--translations", action="append", default=[], help="訳リポジトリのフォルダ（複数指定可）")
    args = ap.parse_args()
    build(args.db, args.translations)
    sys.exit(0)
