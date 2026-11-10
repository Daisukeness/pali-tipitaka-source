# 1単位ずつ順に訳すときの補助道具

2026-11-09 に U00134〜U00160 を順に訳したときに使った道具。並列の道具（../parallel/）は使わない。

## 手順（1単位）

1. `python3 scripts/make_prompt.py U00xxx --remaining > /tmp/pxxx.md` で依頼文を作り、原文の文を見る。
2. **保存する前に**既訳を照合する：`python3 scripts/sequential/look.py "パーリ語の句" 3`
   （build/pali.sqlite の原文と既訳を LIKE で探す。定型句・品名・経題・術語は必ず既訳に合わせる）。
3. 訳を作る。くりかえしの多い単位は Python で訳文を組み立てる（例：`example_gen_U00160.py`）。
   JSON の形：translator, date, prompt_version "v1", text_uid（範囲の経は "sn46.77-88" のように原文の id）, segments, terms（{パーリ語: {ja, reason}}）, uncertain（[{segment, note}]）。
   怪しい所・初出の訳語・既訳とのゆれは必ず uncertain に書く。
4. `python3 scripts/save_translation.py --repo ../pali-ja-claude <json…>`（追記だけ。一度保存した文は書き換えられない）
5. `python3 scripts/check_translation.py <json…>`（…pe… と〔中略〕の数がそろっているか）
6. `python3 scripts/sequential/finish.py U00xxx "sn…〜sn…" <jsonのフォルダ> "| U00xxx | 範囲 | 留意点 |"`
   → make_glossary、留意点/<部>.md（label の最初の経典の部。dn18 なら dn.md）に1行、build_db、record_work、pali-ja-claude の commit と push。
   （2026-11-11 までは 決定事項.md 第4章の表と第6章に1行ずつ足していた）
   セッションのURLを commit に入れるときは環境変数 CLAUDE_SESSION_URL を設定する。

## 気をつけること

- 照合は保存の前に（U00160 で保存の後に照合して、vīmaṁsā の訳が sn43.12 の「考究」と sn51 の「吟味」にゆれた）。
- 原文の pe と …（pe なし）を区別する。pe は〔中略〕、… は「……」。
- 原文に英語の編集注（On Display: Title of Section Only など）があるときは「（品名のみを示す。）」とし、uncertain に書く。
