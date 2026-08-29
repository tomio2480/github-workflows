# npm パッケージ完全 pin と package-lock.json 導入

## 背景

- composite action の install step は `npm install --no-save --no-package-lock` だった．registry の実行時状態に依存する状態だった．
- 同一 SHA でも npm install の結果が変わりうる問題を解消するため，完全 pin + lockfile 方式に切り替えた（Issue #7）．

## 判断

- Option B を採用．`.github/actions/markdown-lint/` に `package.json` と `package-lock.json` をコミットする．install は `npm ci` で行い，更新は Dependabot で追跡する．
- install step の tmpdir 作成は `mktemp -d "${RUNNER_TEMP}/XXXXXX"` へ変更した．他ステップとの一貫性を持たせるためである（gemini-code-assist 指摘に対応）．

## 代替案と棄却理由

- **Option A（現状維持・メジャー固定のみ）**: `textlint@^14` のメジャー固定で ESM 互換性問題を回避できる．ただし registry 状態への依存が残り，再現性は低い．棄却．
- **Option C（renovate / dependabot config 拡張のみ）**: lockfile なしでは install 時の再現性が改善しない．Dependabot の追跡だけ追加しても効果は薄い．Option B で lockfile と Dependabot を両立できるため棄却．

## reviewer 誤検知のパターン

- gemini-code-assist が `package-lock.json` を「PR に含まれていない」と誤検知した．
- 実際には 1 コミット目（`b7c4bd6`）に `create mode 100644` で含まれていた．大きなファイル（5994 行）であり，reviewer の diff 表示が省略されたためと推測する．
- 今後 lockfile など大きな自動生成ファイルを含む PR では，PR 説明へ「ファイル X を含む」と明記すれば誤検知を防ぎやすい．

## スクリプト外出しの保留

- gemini-code-assist から install step の inline bash を `scripts/` に外出しする提案があった．
- 本リポジトリでは `scripts/` 追加に `tests/` での test-first が必須である．そのため今回の PR スコープから切り離し，Issue #38 で扱う．

## 参照

- Issue #7: <https://github.com/tomio2480/github-workflows/issues/7>
- PR #37: <https://github.com/tomio2480/github-workflows/pull/37>
- Issue #38（スクリプト外出し）: <https://github.com/tomio2480/github-workflows/issues/38>
