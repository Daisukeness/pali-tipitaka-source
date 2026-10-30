# パーリ三蔵 原文リポジトリ

パーリ三蔵の原文（SuttaCentral Mahāsaṅgīti 版）と、翻訳の依頼文・スクリプト・翻訳台帳を置くリポジトリ。
訳文はここに置かない。訳文は訳者ごとのリポジトリ（Claude訳は pali-ja-claude）に置く。

## 中身

```
root/pli/ms/           パーリ語原文（取り込んだまま。編集禁止）
reference/pli/ms/      PTS版などのページ番号
variant/pli/ms/        写本の異読
root/misc/site/name/   部・品・経のパーリ語名
sc-data/               経典の階層構造、漢訳阿含経などとの対応
prompts/<版>.md        翻訳の依頼文（版ごとに保存。書き換えず新しい版を作る）
scripts/               スクリプト（Python 3 の標準ライブラリだけで動く）
ledger/                翻訳台帳
SOURCES.md             取り込んだデータの出どころとコミット番号
```

## 使い方

```sh
# 1. データベースを作る（build/pali.sqlite。Gitには入れない）
python3 scripts/build_db.py
python3 scripts/build_db.py --translations ../pali-ja-claude   # 訳文も入れる

# 2. 翻訳台帳を作り直し、集計を見る
python3 scripts/make_ledger.py
python3 scripts/make_ledger.py --summary sn56

# 3. 依頼文を作る（原文と翻訳ルールだけで作る）
python3 scripts/make_prompt.py sn56.11 --translator claude-opus-5.5
python3 scripts/make_prompt.py sn56 --translator claude-opus-5.5 --out out/

# 4. 訳文を確かめる（区切り番号の過不足、空欄、…pe… と〔中略〕の対応）
python3 scripts/check_translation.py ../pali-ja-claude/translation
```

## 翻訳の進め方（1回分ずつ）

進捗は訳文の有無から自動で数える。手で状態を書かない。

```sh
python3 scripts/build_db.py --translations ../pali-ja-claude   # 訳文を入れてDBを作る
python3 scripts/progress.py                                     # 全体の進み具合と次の作業単位
python3 scripts/make_prompt.py U00001 --remaining               # 次の作業単位の依頼文（訳のない文だけ）
#   … 依頼文どおりに訳し、出力のJSONを保存 …
python3 scripts/save_translation.py --repo ../pali-ja-claude 訳.json   # 決まった場所へ追記保存
python3 scripts/check_translation.py ../pali-ja-claude/translation
python3 scripts/build_db.py --translations ../pali-ja-claude
python3 scripts/record_work.py --repo ../pali-ja-claude --unit U00001 --segments 188 --chars 14661
```

- `ledger/plan.json`：優先順と1回分の字数（unit_chars）。変えたら `make_units.py` で作業単位を作り直す。
- `ledger/units.tsv`：作業単位の一覧。進捗は文ごとに数えるので、作り直しても訳した分は失われない。
- 途中で止めてよい。経典1つごと（長い経典は数千字ごと）に保存し、次回は `--remaining` で続きから。
- 状態：未着手／翻訳中（一部の文だけ訳あり）／取込済／要確認（uncertain あり）／確認済（将来）。

## 訳文ファイルの置き場所（訳リポジトリ側）

`translation/ja/<訳者ID>/<原文と同じフォルダ>/<経典uid>.json`
例：`translation/ja/claude-opus-5.5/sutta/sn/sn56/sn56.11.json`

形式は prompts/v1.md の「出力」のとおり。

## 翻訳台帳

- `ledger/texts.tsv`：経典ごとの文の数・字数。スクリプトが作り直すので手で直さない。
- 状態は訳文から自動で判定する（上の「翻訳の進め方」）。

## 守ること

- 原文のファイルを編集しない。
- 依頼文に他のAIの訳を入れない。
- 確定した訳は書き換えない。直すときは新しい依頼文の版で別の訳として登録する。
