# Issue #121・#122 対応の設計判断と学び

## 要約

`markdownlint-cli2` の lockfile 管理移行（#121，PR #126，v2.12.2）と，
caller config の `outputFormatters` 除去（#122，PR #129，v2.12.3）の記録．
後者は Codex レビュー 5 ラウンド計 8 件の指摘をすべて採用した．
構造化テキスト加工の難所と，再発防止の起票先をまとめる．

## 目次

- 背景
- 判断
- 代替案と棄却理由
- レビューの学び（Codex 5 ラウンド 8 件）
- 再発防止の起票
- 参照

## 背景

- #121: composite action の `markdownlint-cli2` 実行が floating semver の
  `npx` であり，未レビューの新版が caller の runner で走りうる．
  `npx` 内の版指定は Dependabot の追随対象にもならない．
- #122: caller config が `outputFormatters` を定義すると既定 formatter が
  置き換えられ，違反があっても inline・summary とも 0 件になる．
  サイレント故障であり caller は気づけない．

## 判断

### #121: lockfile 管理へ移行

- `package.json` へ 0.13.0 を追加した．0.13 系の公開版は 0.13.0 のみで，
  従来の `^0.13.0` の解決結果と同一のため挙動は変わらない．
- install ステップを `markdownlint` 実行前へ移し，textlint と共通の
  lint 依存インストールへ統合した（`install-lint-deps.sh` へ改名）．
- Dependabot の group は `textlint` と `markdownlint` に分け，
  片系統の挙動変化を他方の更新と切り離してレビューできるようにした．
- `npm audit` は cli2 0.13.0 のツリーに既知指摘を出すが，従来 `npx` が
  実行時に取得していた同一物であり露出は増えない．解消は Dependabot の
  更新 PR（0.23 系）で扱い，設定互換の確認は当該 PR で行う．

### #122: runtime config 生成でキーを除去

最終形は次のとおり．初版から Codex レビューで大きく変わった．

- `generate-mdlint-runtime.py` が解決済み config を検査する．
  キーがあるときだけ除去済み runtime config を生成し，`::warning::` で
  caller に知らせる．無ければ何も生成しないパススルーとし，
  既存 caller の挙動を完全に不変へ保つ．
- 生成先は src と同じディレクトリ．cli2 は `customRules` 等の相対パスを
  config ファイルのディレクトリ基準で解決するためである．
- ファイル名は `tempfile.mkstemp` の一意名とし，caller 所有ファイルを
  上書きしない．suffix は `--config` が受理する規約名に合わせる．
- 除去はトップレベルキーのテキスト除去とし，他の行をバイト単位で保持する．
  root インデント検出・indentationless sequence・コメント行・BOM に対応した．
- 生成物は re-parse し，キー集合が「元 − 除去キー」と一致しなければ
  fail-closed にする．
- 削除は composite 末尾の `if: always()` ステップが担い，
  中間ステップの失敗でも残置しない．
- 採用パスの分岐は script が `GITHUB_OUTPUT` へ書く．bash 側へ分岐を
  残さず，全経路を pytest で検証できるようにした．

## 代替案と棄却理由

- **docs へ「非対応」と明記するだけの案（#122 の Issue 記載）**:
  指摘 0 件化はサイレント故障で caller が気づけないため棄却した．
- **`RUNNER_TEMP` への退避**: 初版で採用したが，config 基準の相対パス
  （`customRules` / `markdownItPlugins`）が壊れるため同ディレクトリ生成へ
  転換した．
- **相対パスの絶対パス変換**: 書き換え対象キーの網羅（`extends` 含む）が
  必要で壊れやすいため棄却した．
- **PyYAML の往復再シリアライズ**: YAML 1.1 のスカラー解釈で，引用符なしの
  `on` / `yes` が bool へ化ける．cli2 側の `js-yaml` 4 と型がずれ lint
  挙動が変わるため，テキスト除去へ転換した．
- **loader schema を `js-yaml` 4 へ合わせる案**: bool 以外の差分
  （sexagesimal・timestamp 等）まで揃える必要があり脆いため棄却した．

## レビューの学び（Codex 5 ラウンド 8 件）

指摘はすべて P2 で，すべて採用した．内訳は次のとおり．

1. config 相対パスの解決基準（生成先の同居が必要）
2. 固定名による caller 所有ファイルの上書き
3. YAML 1.1 往復のスカラー型崩れ
4. indentationless sequence（列 0 の `- ` エントリ）
5. sequence 内の列 0 コメント行
6. UTF-8 BOM 付き config
7. 一様にインデントされた root mapping
8. 失敗・キャンセル時の生成物残置

メタな学びは次の 3 点である．

- 構造化テキストの部分加工は style 変種が多く，場当たり実装では正当な
  入力を壊すか拒否する．実装前に変種の網羅表を作りテストへ翻訳すべきである．
- 「生成物を re-parse して期待構造と突合する」検証は最後の砦として有効
  だった．検証がなければ 4〜7 は壊れた出力を黙って cli2 へ渡していた．
- 一時生成物はライフサイクル（名前の衝突・残置・削除経路）まで設計対象で
  ある．正常系の削除だけでは失敗経路で漏れる．

## 再発防止の起票

- `github-workflows` #130: 除去経路の統合テスト（CI fixture）
- `github-workflows` #131: templates 版コメントのドリフト検知 CI
- `github-workflows` #132: 定例リリースの `release-patch` スクリプト化
- `github-workflows` #133: checks 登録待ち付き `watch-pr-checks`
- `github-workflows` #134: 中央 lockfile を直接実行するローカル事前 lint．
  各リポジトリへ個別配置せず，中央チェックアウトの共有で drift を避ける
- `settings` #289: `code-quality` Skill へ構造化テキスト加工の規律を追加
- `settings` #290: `bash-guard` hook の誤検知 3 件の緩和

## 参照

- Issue: [#121](https://github.com/tomio2480/github-workflows/issues/121)，
  [#122](https://github.com/tomio2480/github-workflows/issues/122)
- PR: [#126](https://github.com/tomio2480/github-workflows/pull/126)（v2.12.2），
  [#129](https://github.com/tomio2480/github-workflows/pull/129)（v2.12.3）
- 先行整備の記録:
  [2026-08-28-issue117-119-markdownlint-unification.md](2026-08-28-issue117-119-markdownlint-unification.md)
