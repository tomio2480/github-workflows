# npm パッケージ完全 pin と package-lock.json 導入

## 背景

- composite action の install step が `npm install --no-save --no-package-lock` で実行しており，registry の実行時状態に依存していた．
- 同一 SHA でも npm install の結果が変わりうる問題を解消するため，完全 pin + lockfile 方式に切り替えた（Issue #7）．

## 判断

- Option B（`.github/actions/markdown-lint/package.json` + `package-lock.json` をコミット，`npm ci` で install，Dependabot で追跡）を採用．
- install step の tmpdir 作成を `mktemp -d` から `mktemp -d "${RUNNER_TEMP}/XXXXXX"` に変更し，他ステップとの一貫性を持たせた（gemini-code-assist 指摘に対応）．

## 代替案と棄却理由

- **Option A（現状維持・メジャー固定のみ）**: `textlint@^14` のメジャー固定で ESM 互換性問題を回避できるが，registry 状態への依存が残り再現性が低い．棄却．
- **Option C（renovate / dependabot config 拡張のみ）**: lockfile なしで Dependabot の追跡だけ追加しても，install 時の再現性は改善しない．Option B で lockfile + Dependabot を両立できるため棄却．

## reviewer 誤検知のパターン

- gemini-code-assist が `package-lock.json` を「PR に含まれていない」と誤検知した．
- 実際には 1 コミット目（`b7c4bd6`）に `create mode 100644` で含まれていた．大きなファイル（5994 行）であり，reviewer の diff 表示が省略されたことが原因と推測する．
- 今後 lockfile など大きな自動生成ファイルを含む PR では，PR 説明に「ファイル X を含む」と明記すると誤検知を防ぎやすい．

## スクリプト外出しの保留

- gemini-code-assist から install step の inline bash を `scripts/` に外出しする提案があった．
- 本リポジトリでは `scripts/` 追加に `tests/` での test-first が必須のため，今回の PR スコープから切り離して Issue #38 で扱う．

## 参照

- Issue #7: https://github.com/tomio2480/github-workflows/issues/7
- PR #37: https://github.com/tomio2480/github-workflows/pull/37
- Issue #38（スクリプト外出し）: https://github.com/tomio2480/github-workflows/issues/38
