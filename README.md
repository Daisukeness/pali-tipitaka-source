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

## 訳文ファイルの置き場所（訳リポジトリ側）

`translation/ja/<訳者ID>/<原文と同じフォルダ>/<経典uid>.json`
例：`translation/ja/claude-opus-5.5/sutta/sn/sn56/sn56.11.json`

形式は prompts/v1.md の「出力」のとおり。

## 翻訳台帳

- `ledger/texts.tsv`：経典ごとの文の数・字数。スクリプトが作り直すので手で直さない。
- `ledger/status.tsv`：経典×訳者ごとの状態（未着手・依頼文作成済・取込済・要確認・確認済）。載っていなければ未着手。

## 守ること

- 原文のファイルを編集しない。
- 依頼文に他のAIの訳を入れない。
- 確定した訳は書き換えない。直すときは新しい依頼文の版で別の訳として登録する。
