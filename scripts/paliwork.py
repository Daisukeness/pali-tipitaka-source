"""翻訳の進捗管理で共通に使う関数。scripts/ の各スクリプトとサイト生成から読み込む。

考え方:
  - 進捗は「文」単位で、訳文があるかどうかから自動で数える。手で状態を書かない。
  - 原文が空の文（見出しの区切りなど）は、最初から訳し終えたものとして数える。
  - 「作業単位」は1回分の目安（ledger/units.tsv）。ledger/plan.json の優先順と字数から作る。
"""
import csv
import json
import os
import re
import sqlite3
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "build", "pali.sqlite")
PLAN = os.path.join(REPO, "ledger", "plan.json")
UNITS = os.path.join(REPO, "ledger", "units.tsv")
DEFAULT_TRANSLATOR = "claude-opus-5.5"

STATE_NONE = "未着手"
STATE_PARTIAL = "翻訳中"
STATE_DONE = "取込済"
STATE_UNCERTAIN = "要確認"
STATE_REVIEWED = "確認済"


def connect(db=DB):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def load_plan():
    with open(PLAN, encoding="utf-8") as f:
        return json.load(f)


def texts_in_order(con, roots):
    """roots の順に、その下にある経典を (uid, どの root の下か) で木の順に返す（重複は除く）。最後に残り全部。"""
    children = defaultdict(list)
    is_text = {}
    for r in con.execute("SELECT uid, parent_uid, is_text FROM node ORDER BY sort"):
        children[r["parent_uid"]].append(r["uid"])
        is_text[r["uid"]] = r["is_text"]
    seen, out = set(), []

    def walk(u, root):
        if is_text.get(u) and u not in seen:
            seen.add(u)
            out.append((u, root))
        for c in children[u]:
            walk(c, root)

    for r in roots:
        walk(r, r)
    for r in children[None]:
        walk(r, r)
    return out


def section_of(segment_id):
    """dn1:1.31.6 → '1.31'、sn56.11:2.3 → '2'（一番細かい段落の番号）。"""
    return segment_id.split(":", 1)[1].rsplit(".", 1)[0]


def load_units():
    with open(UNITS, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        r["texts"] = r["texts"].split(",")
        r["segments"] = int(r["segments"])
        r["pali_chars"] = int(r["pali_chars"])
    return rows


def unit_segments(con, unit):
    """作業単位に含まれる文を (segment_id, text_uid, pali) の並びで返す。"""
    rows = []
    for t in unit["texts"]:
        rows += con.execute(
            "SELECT segment_id, text_uid, pali, seq FROM segment WHERE text_uid=? ORDER BY seq", (t,)
        ).fetchall()
    if unit.get("seg_from"):
        ids = [r["segment_id"] for r in rows]
        a = ids.index(unit["seg_from"])
        b = ids.index(unit["seg_to"]) + 1
        rows = rows[a:b]
    return rows


def translated_ids(con, translator):
    return {
        r[0] for r in con.execute(
            "SELECT segment_id FROM translation WHERE translator_id=? AND TRIM(ja) <> ''", (translator,)
        )
    }


class Progress:
    """訳文の有無から、文・経典・作業単位・木の節ごとの進み具合を数える。"""

    def __init__(self, con, translator=DEFAULT_TRANSLATOR):
        self.con = con
        self.translator = translator
        done_ids = translated_ids(con, translator)
        self.text_total = {}
        self.text_done = {}
        self.text_chars = {}
        self.text_done_chars = {}
        for r in con.execute("SELECT segment_id, text_uid, pali FROM segment"):
            t = r["text_uid"]
            n = len(r["pali"])
            self.text_total[t] = self.text_total.get(t, 0) + 1
            self.text_chars[t] = self.text_chars.get(t, 0) + n
            if not r["pali"] or r["segment_id"] in done_ids:
                self.text_done[t] = self.text_done.get(t, 0) + 1
                self.text_done_chars[t] = self.text_done_chars.get(t, 0) + n
        self.any_done = {t for t in self.text_total
                         if self.text_done.get(t, 0) > self.text_empty(t)}
        self.uncertain = defaultdict(int)
        for r in con.execute(
            "SELECT s.text_uid, COUNT(*) FROM uncertain u JOIN segment s ON s.segment_id = u.segment_id "
            "WHERE u.translator_id=? GROUP BY s.text_uid", (translator,)
        ):
            self.uncertain[r[0]] = r[1]
        self.reviewed = set()  # 将来：review テーブルから

    def text_empty(self, t):
        if not hasattr(self, "_empty"):
            self._empty = defaultdict(int)
            for r in self.con.execute("SELECT text_uid, COUNT(*) FROM segment WHERE pali='' GROUP BY text_uid"):
                self._empty[r[0]] = r[1]
        return self._empty[t]

    def state(self, t):
        if t not in self.any_done:
            return STATE_NONE
        if self.text_done.get(t, 0) < self.text_total[t]:
            return STATE_PARTIAL
        if t in self.reviewed:
            return STATE_REVIEWED
        if self.uncertain.get(t):
            return STATE_UNCERTAIN
        return STATE_DONE

    def unit_status(self, unit, done_ids=None):
        if done_ids is None:
            done_ids = self._done_ids()
        rows = unit_segments(self.con, unit)
        need = [r for r in rows if r["pali"]]
        done = [r for r in need if r["segment_id"] in done_ids]
        return len(done), len(need)

    def _done_ids(self):
        if not hasattr(self, "_ids"):
            self._ids = translated_ids(self.con, self.translator)
        return self._ids

    def next_unit(self, units):
        ids = self._done_ids()
        for u in units:
            d, n = self.unit_status(u, ids)
            if d < n:
                return u, d, n
        return None, 0, 0

    def subtree(self):
        """{node uid: dict(texts, done_texts, chars, done_chars, segments, done_segments)}"""
        children = defaultdict(list)
        for r in self.con.execute("SELECT uid, parent_uid FROM node"):
            children[r["parent_uid"]].append(r["uid"])
        result = {}

        def walk(u):
            acc = dict(texts=0, done_texts=0, partial_texts=0, chars=0, done_chars=0,
                       segments=0, done_segments=0)
            if u in self.text_total:
                acc["texts"] = 1
                st = self.state(u)
                acc["done_texts"] = int(st in (STATE_DONE, STATE_UNCERTAIN, STATE_REVIEWED))
                acc["partial_texts"] = int(st == STATE_PARTIAL)
                acc["chars"] = self.text_chars[u]
                acc["done_chars"] = self.text_done_chars.get(u, 0) if u in self.any_done else 0
                acc["segments"] = self.text_total[u]
                acc["done_segments"] = self.text_done.get(u, 0) if u in self.any_done else 0
            for c in children[u]:
                sub = walk(c)
                for k in acc:
                    acc[k] += sub[k]
            result[u] = acc
            return acc

        for r in children[None]:
            walk(r)
        return result


def translation_path(con, translations_repo, translator, text_uid):
    """訳文ファイルの置き場所：translation/ja/<訳者>/<原文と同じフォルダ>/<uid>.json"""
    path = con.execute("SELECT path FROM text WHERE uid=?", (text_uid,)).fetchone()[0]
    rel_dir = os.path.dirname(os.path.relpath(path, os.path.join("root", "pli", "ms")))
    return os.path.join(translations_repo, "translation", "ja", translator, rel_dir, text_uid + ".json")


def read_work_log(translations_repo):
    path = os.path.join(translations_repo, "log", "work.tsv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def natural_key(uid):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", uid)]
