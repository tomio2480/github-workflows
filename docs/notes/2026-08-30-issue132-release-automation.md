# 定例リリースのスクリプト化とレビュー 4 ラウンドの知見

## 背景

Issue #132 として，PR マージ後の定例リリースを
`bin/release-patch.{sh,ps1}` へまとめた．
対象は patch タグ発行・Release 作成・major mutable 追従である．
手順自体は既に文書化されていたが，毎マージで LLM が手組みしており，
番号ミスとタグ発行スキップの実績があった．

本ノートは実装そのものより，Codex レビュー 4 ラウンドで露見した
「動くが壊れる」設計の穴と，検証手順の教訓を残す．

## 判断

### 決定論的な手順でも，自動化は冪等性まで含めて設計する

初版は素直な 5 コマンドの直列実行だった．
レビューで「途中失敗後に再実行すると，作成済みタグのガードで止まり
残り手順を完走できない」と指摘された．
決定論的な手順を写しただけでは，失敗経路が設計から抜け落ちる．

採った方針は再開（resume）である．
既存タグが要求 SHA を指す場合は作成をスキップし，
作成済み Release も `gh release view` で検出してスキップする．
クリーンアップ（作成済みタグの削除）は採らなかった．
push 済みタグの削除は caller へ影響しうるためである．

### `--force-with-lease` は「順序」を保証しない

major mutable の force push を lease 付きへ変えたが，これだけでは不足だった．
lease が保証するのは「観測値から動いていないこと」だけである．
古いリリースが遅れて走り，新しい値を観測してから push すれば，
lease を満たしたまま `v2` を巻き戻せる．

対策として単調性検査を足した．
push 前に remote の現在値を `git merge-base --is-ancestor` で検査する．
新 patch commit の祖先でなければ中止する．
版の順序は commit の祖先関係で強制し，lease は検査から push までの
競合検知に使う．二段構えである．

### 値必須オプションは後続オプションを吸わせない

`--notes --dry-run` のように値を書き忘れると，`--dry-run` が
ノート本文として消費され，dry-run のつもりが本実行になる．
影響が「実行するつもりのなかったリリース」であるため P1 相当だった．
値必須オプションではハイフン始まりトークンと空値を拒否する．

PowerShell 版は同種の実装を足していない．
パラメーターバインダーが `-Notes -DryRun` を拒否することを実機で確認した．
エラーは `Missing an argument for parameter 'Notes'` である．
言語機能で担保される場合は重ねない．

### 破壊的操作の対象は ref 種別まで絞る

`git push --delete <name>` はブランチ専用ではない．
`refs/tags/v2.13.1` を渡せば，直前に作成したリリースタグを消せる．
削除 refspec を `refs/heads/<name>` 明示で組み，
`refs/` 始まりの入力は検証で拒否する形にした．

## 検証の教訓

### shallow クローンの誤判定は再現してから直す

「shallow クローンでは祖先関係を判定できない」という指摘に対し，
`--depth 1` のクローンを作って再現を取った．
素の `git fetch origin refs/tags/v2` では履歴が埋まらない．
その後の `git merge-base --is-ancestor <古い SHA> HEAD` は失敗する．
`fatal: Not a valid commit name` を返し exit 128 となる．
本当は祖先である場合でも中止側へ倒れる．

`git fetch --unshallow origin refs/tags/v2` を挟めば解消する．
`--is-shallow-repository` が `false` になり判定が通る．
完全クローンへ `--unshallow` を渡すとエラーになる．
そのため `git rev-parse --is-shallow-repository` で分岐する．

副次的な観察を 1 点残す．Windows では fetch 後に
`failed to write commit-graph` と表示される場合がある．
これはメンテナンス処理由来で終了コードは 0 のままであり，
`set -e` の中断には影響しない．

### bats の `! grep` は検査にならない

否定アサーションを `! grep -q ...` と書くと，
`set -e` は `!` で否定した文の失敗を検出しない．
ただし常に素通りするわけではない．
当該行がテストの最終コマンドなら，返り値 1 がテストの失敗として残る．
素通りするのは，後ろに成功するコマンドが続いて終了ステータスを
上書きする場合である．

実例がある．PR #136 の Red 実行では，次のテストだけが実装前に成功した．
「skips release creation when release already exists」である．
`! grep -q "gh release create"` の後ろに別の `grep` が続いており，
そちらの成功が終了ステータスを上書きしていた．
テストが並ぶほど否定アサーションは中間行になりやすく，素通りしやすい．
`run grep ...` の後に `[ "${status}" -ne 0 ]` を置く形へ統一した．

### CI のチェック名を「検査された」と読み替えない

PR に「Reusable Shell quality workflow / Shell / CLI quality」が
pass と表示された．
ログを読むと，実行対象は fixture
（`tests/fixtures/shell-quality/verify-shell.py`）であった．
reusable workflow の toolchain と契約を検証する自己テストであり，
本リポジトリのシェルスクリプトは対象外である．

そこで CI と同一版の ShellCheck 0.11.0 をローカルで実行した．
`bin/release-patch.sh` は指摘 0 件であった．
shfmt と PSScriptAnalyzer はローカル未導入のため未実行とし，
「未検証」と明示した．検査対象の取り違えは Issue #138 として起票した．

## 代替案と棄却理由

1. **リリース手順を GitHub Actions 化する**
   マージ時に自動でタグと Release を発行する案．
   版番号の決定には patch と minor を見分ける判断が要る．
   自動化すると誤った番号で発行される．
   Issue #132 の方針どおり，版番号の決定はスクリプト外に残した．

2. **PowerShell 版に Pester テストを用意する**
   リポジトリに Pester 基盤がなく，導入自体が別スコープになる．
   dry-run と異常系の実機確認で代替し，PR 本文へ検証範囲を明記した．
   `bin/` を検査対象へ含める仕組みは Issue #138 で扱う．

3. **`git push -f` のまま運用注意で回避する**
   並行実行は本リポジトリで現実的である（複数セッションが worktree で走る）．
   運用規律より機械的な防止を選んだ．

## 参照

- Issue #132 — 定例リリースの release-patch スクリプト化
- PR #136 — 本実装．Codex レビュー 4 ラウンド計 8 件の指摘
- Issue #138 — 中央リポジトリ自身のシェル資産を検査する repo-local gate
- [docs/notes/2026-05-01-retroactive-tag-rollout.md](2026-05-01-retroactive-tag-rollout.md) — 実行順序の原典
- [docs/notes/2026-08-09-tag-drift-and-version-comment-lessons.md](2026-08-09-tag-drift-and-version-comment-lessons.md) — 版コメントドリフトの経緯
