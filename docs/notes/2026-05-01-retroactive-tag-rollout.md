# retroactive タグ発行と GitHub Release 作成の実行手順

## 背景

PR #25 で SemVer 風 patch tag 運用への移行を決定した．
既存は `v1` `v2` mutable のみだった．
retroactive に v2.0.0/v2.1.0/v2.2.0/v2.2.1 を切り直す作業を 1 セッションで実施した．
あわせて `v2` mutable を最新 patch まで進めた．
本ノートは実行手順と途中で踏んだ落とし穴を残し，今後の patch リリース作業を再現可能にする．
詳細な判断は [2026-05-01-semver-release-operations.md](2026-05-01-semver-release-operations.md) を参照．

## 判断

タグ発行と Release 作成は次の順序で行う．

1. ローカルで全タグを作成しまとめて push する
2. GitHub Release を `gh release create` で 1 タグずつ作る
3. `latest` フラグは最新の patch にのみ付ける

retroactive タグは `git tag <name> <SHA>` で過去 commit を指定する．
mutable major（`v2`）の更新は `git tag -f v2 <new-SHA>` と `git push -f origin v2` で行う．
SHA を移すだけなので caller への破壊性は低いが，force-push のためログには `forced update` と出る．

### 実行コマンド（今回の構成）

```bash
# 1. retroactive タグの作成
git tag v2.0.0 8382b97
git tag v2.1.0 9d82865
git tag v2.2.0 39b56da
git tag v2.2.1 b69f79d

# 2. mutable major の移動
git tag -f v2 b69f79d

# 3. immutable patch をまとめて push
git push origin v2.0.0 v2.1.0 v2.2.0 v2.2.1

# 4. mutable major を force-push
git push -f origin v2

# 5. GitHub Release を 1 タグずつ作成（最新のみ --latest を付ける）
gh release create v2.0.0 --title "v2.0.0" --notes "..."
gh release create v2.1.0 --title "v2.1.0" --notes "..."
gh release create v2.2.0 --title "v2.2.0" --notes "..."
gh release create v2.2.1 --latest --title "v2.2.1" --notes "..."
```

## 代替案と棄却理由

1. **タグ発行と Release 作成を 1 PR で済ませる**
   PR の差分にタグ操作は含められないため不可能．
   タグは git の参照であり PR が扱う木の中身ではない．
   docs PR をマージしてからタグを切る順序になる．

2. **mutable major を動かさない**
   `@v2` pin 利用者は古い実装に固定され続ける．
   caller は SHA pin に切り替えるか opt-in で patch tag を pin する必要が生じる．
   mutable major で簡便に追従できるという SemVer の利点も失われる．
   今回は force-push で進める方針を採用した．

3. **patch tag を間引く**
   v2.0.0 と v2.2.1 のみで間に合わせる発想がある．
   ただし v2.1.0 の caller-side allowlist と v2.2.0 の stage 2 prh も独立した節目である．
   retroactive で位置を残しておくほうが caller のロールバック先として有用．
   間引きは棄却した．

## 落とし穴

### `gh release create --target` は既存タグに対して使えない

`gh release create v2.0.0 --target 8382b97 ...` は次のエラーで失敗する．

```
HTTP 422: Validation Failed
Release.target_commitish is invalid
```

タグが既に存在する場合，Release は当該タグの指す commit を使うため `--target` は不要．
逆にタグがまだ無い場合は `--target` で commit を指定すると同時にタグも作成される．
今回は先に `git push origin v2.0.0` でタグを作成済みのため `--target` を外して実行した．

### note 内で特殊文字を扱う場合の注意

`gh release create --notes "$(cat <<EOF ... EOF)"` の heredoc は開始デリミタが無クォート扱いとなる．
そのため bash が `$` を展開する．
リテラル `$` を入れたい場合は開始デリミタを `'EOF'` または `"EOF"` のようにクォートで囲むと展開を抑止できる．
bash ではシングルクォート・ダブルクォートいずれも同じく展開を抑止する挙動である．
展開有無を制御するのは開始側のクォートで，閉じ側の `EOF` 行はクォート不要である．
バッククォートはコードスパンを示すため Release ノート上でそのまま欲しい場合が多い．
今回は本文に `$GITHUB_ACTION_PATH` 等を書かなかったが，書く場合はクォート付き版に切り替える運用とする．

### `--latest` フラグは最新タグにだけ付ける

`gh release create --latest` は GitHub の "Latest release" バッジを当該リリースに付与する．
複数の Release で `--latest` を指定すると最後に作成したものが上書きで latest になる．
ただし途中の Release が一時的に latest 表示される時間が生じる．
意図せず古いリリースが latest になる事故を避けるため，最後に作成する patch にだけ付ける．

## 参照

- [docs/notes/2026-05-01-semver-release-operations.md](2026-05-01-semver-release-operations.md) — SemVer 移行の判断ログ
- [docs/dictionary-maintenance.md](../dictionary-maintenance.md) — 表 2 / 表 3 の参照方式・変更種別マトリクス
- [CLAUDE.md](../../CLAUDE.md) — タグ運用規律
- [GitHub Releases v2.2.1](https://github.com/tomio2480/github-workflows/releases/tag/v2.2.1) — 今回 latest として発行
- [gh release create docs](https://cli.github.com/manual/gh_release_create)
