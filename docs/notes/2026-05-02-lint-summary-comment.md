# lint summary コメント機構の設計判断と運用知見

## 背景

[Issue #24](https://github.com/tomio2480/github-workflows/issues/24) は reviewdog の `github-pr-review` reporter が findings ゼロのとき何も投稿しない仕様への対応である．
PR を見たユーザは「lint が走ったが指摘なし」 と「workflow 未起動」 を区別できなかった．
[PR #28](https://github.com/tomio2480/github-workflows/pull/28) では件数の summary コメントを hidden marker で 1 件 upsert する機構を導入した．

本ノートは個別の実装そのものではない．
PR #28 を通じて固まった**設計判断とレビュー対応の運用パターン**を再利用可能な知見として残す．

## 判断 1：集計層と表示層の責務分離

機能は次の 2 段に分けて実装した．

- 集計：[scripts/count-lint-findings.py](../../scripts/count-lint-findings.py) は textlint XML と markdownlint テキストを読み件数と findings 一覧を JSON にする
- 投稿：[scripts/post-lint-summary.sh](../../scripts/post-lint-summary.sh) は JSON を Markdown 本文に rendering して PR コメントを upsert する

責務を分けると次の利益が出る．

1. 集計のロジックは pure な Python になり pytest で網羅できる．
   ファイルパス・正規表現・severity 内訳のテストが小さい単位で書ける
2. 表示用の正規化（path 相対化・rule prefix strip・改行畳み込み）は rendering 層に閉じる．
   JSON の生データは「集計の事実」 として汎用に保てる
3. 将来別の出力先（Slack 通知・サマリレポート等）を足すとき，集計層を再利用できる

短期的にはスクリプトを 2 本に増やす分だけ複雑度が上がる．
ただし bats で fake curl + JSON fixture のテストが書きやすくなる利点が勝つ．

## 判断 2：filter-mode と inline コメントのギャップを summary で吸収する

reviewdog の `filter-mode: added`（既定）は PR 差分行に該当しない指摘を inline 化しない．
このため「summary が 13 件と表示するが inline コメントは 0 件」 という見え方が起こりうる．
本 PR の self-PR でもこの差が観測された．

summary 本文を以下の構成にして「件数の意味」 を明示するのが解になる．

- 文言：「差分行に該当する指摘は inline，filter-mode で inline 化されない指摘は下記 details と Actions ログを参照」
- `<details>` 展開：findings 上位 20 件を file:line / severity / rule / message 形式で列挙
- 末尾：Actions workflow run へのリンク

ヒューリスティックは次のとおり．

> **集計件数と表示件数にギャップが出る UI を設計するときは
> 「件数の意味」 と「漏れた分の参照経路」 を本文に組み込む．**
> 数字だけ見せると利用者は「何が見えていないか」 を判断できない．

## 判断 3：upsert + hidden marker の race と単一 job 制約

`<!-- gh-workflows-lint-summary -->` 付きコメントを GET → 既存あり PATCH，無し POST で upsert する．
hidden marker は他 bot（CodeRabbit / Gemini）と衝突しない `gh-workflows-` プレフィックスを採用した．

落とし穴は同一 PR で複数 job が同 marker を使うときの race である．
`integration-action-clean-only` のような job を追加して「指摘ゼロ」 ケースを別 job で目視確認する案は当初の plan に含んでいたが，PR 着手中に race の懸念に気付き drop した．
代替として「指摘ゼロ」 ケースは pytest / bats で網羅した．

> **upsert + 単一 marker は前提として「同一スコープで 1 プロセスだけ書く」 を要求する．
> matrix や複数 job を導入する設計では marker をスコープ別に分けるか upsert を諦める．**

## 判断 4：既存スクリプトのスタイル踏襲でレビュー観点を先回りする

[scripts/add-pr-reaction.sh](../../scripts/add-pr-reaction.sh) と同じ規律を踏襲した．

- 一時ファイルは `mktemp` で作成し `trap 'rm -f ...' EXIT` でクリーンアップ
- curl は `--retry 2 --retry-all-errors --max-time 10`
- 必須 env 不足は execution error．API call 失敗は `::warning::` で fail-open

これらはどれも Gemini が同種コードに毎回出してくる定番指摘である．
最初から踏襲しておけば指摘ゼロでマージできる．
PR #28 の Gemini レビューでも mktemp / trap / retry 系は該当指摘が来なかった．

> **bot レビュー定番の観点は事前に Skill / agent / 既存スクリプトに inline 化しておく．
> 都度の指摘を後から潰すより先回りのほうがレビューサイクルを節約できる．**

PR #28 で観測された機械生成 Markdown 固有の sanitization 規律（改行・パイプ・絶対パス・フレームワーク内部 prefix の正規化）は，本リポジトリ単独では先回りしきれなかった観点である．
[tomio2480/settings#28](https://github.com/tomio2480/settings/issues/28) として meta Issue に起票した．

## 判断 5：bot レビューが古い commit を見るパターンへの返信定型

複数回 push する PR では，bot の指摘が「既に対応済み」 のケースが頻発した．
PR #28 でも 1 件発生した．
返信は次の構造で書くと相手と将来の自分の双方が辿りやすい．

- 冒頭：先行対応済みである旨と該当 commit SHA
- 中段：実装の場所（ファイル + 関数名）と test の場所
- 末尾：「最新 commit 以降を確認してほしい」 旨

定型化すると返信草案を `review-responder` agent で量産できる．

> **指摘が古い commit に対するものか最新かは PR タイムライン上で容易に区別がつかない．
> 採用 / 却下とは別軸の「先行対応済」 という第 3 の返信パターンを定型化する．**

## 判断 6：TDD で正規表現のエッジケースを早期に拾う

`scripts/count-lint-findings.py` の markdownlint 行検出 regex は当初 `^.+:\d+(?::\d+)?\s+\S+/\S+`（greedy）だった．
Gemini レビューで非貪欲化を指摘されたタイミングで，「コロン入りファイル名」 の回帰防止テストを追加した．

```python
"docs/sample:colon.md:12:5 MD012/no-multiple-blanks Multiple consecutive blank lines"
```

greedy だと `line=5` を拾うが non-greedy だと `line=12` を拾う．
本来の行番号は 12 のため non-greedy が正しい．
fixture ベースの TDD では「観測された 1 ケース」 だけでなく「regex の振る舞いとして妥当な代表例」 も pin するのが効く．

> **正規表現の挙動を test で pin するときは「実観測」 だけでなく「regex 設計の正しさ」 を表す代表例を入れる．
> 後者は将来の greedy 化リファクタを機械的に防ぐ．**

## 代替案と棄却理由

1. **markdownlint 件数を reviewdog action から取得する**

   reviewdog action は内部で markdownlint-cli2 を呼ぶが件数を outputs に公開しない．
   action を fork して outputs を足す案もあるが，third-party SHA pin の管理コストが上がる．
   composite 内で markdownlint-cli2 を別途実行する案を採った．
   コストは数秒で軽微である．

2. **summary をやめて GitHub Checks API で表示する**

   Checks の `conclusion: success` で「指摘ゼロ」 の状態は伝わるが，PR タイムラインに残らない．
   利用者が PR を見たときに件数を辿れない．
   PR コメント形式のほうが review 履歴と統合しやすいため採用した．

3. **integration-clean-only job を追加して「指摘ゼロ」 ケースを self-PR で目視確認する**

   plan 段階では入れていたが upsert の race 懸念で drop した．
   pytest / bats で挙動を網羅したため目視確認は不要と判断している．

## 参照

- [Issue #24](https://github.com/tomio2480/github-workflows/issues/24) — 観測された問題
- [Pull Request #28](https://github.com/tomio2480/github-workflows/pull/28) — 実装と Gemini レビュー対応
- [docs/architecture.md](../architecture.md) — summary 投稿の動作と marker 仕様
- [tomio2480/settings#28](https://github.com/tomio2480/settings/issues/28) — 機械生成 Markdown sanitization 規律の meta Issue
