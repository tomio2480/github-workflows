# reviewdog の削除処理が同一 push 内の複数 job で競合する

## 背景

PR #84 で，同一 push に対して 2 job が失敗した．
対象は「Markdown Lint」と「Self test」の
`Composite action integration on fixtures` である．
いずれも `fail-on-error: false` を設定していた．

## 事象

両 job のログに共通して次のエラーが出ていた．

```text
reviewdog: failed to delete comment (id=...): DELETE
  https://api.github.com/repos/.../pulls/comments/...: 404 Not Found []
##[error]Process completed with exit code 1.
```

`-fail-on-error=false` は textlint の **指摘件数** による失敗のみを
抑制する．reviewdog 内部の GitHub API 呼び出しエラー（今回は
古いレビューコメントの削除失敗）は対象外で，job 自体が失敗する．

## 原因

両 job は同じ PR（#84）に対して `github-pr-review` reporter で
reviewdog を実行する．reviewdog は再実行のたびに，自分が過去に
投稿したコメントをクリーンアップしてから新規コメントを投稿する．

2 job はほぼ同時刻（実測で数秒差）に同じ PR へ向けて動いた．
一方の job が既に削除したコメントを，もう一方の job も
削除しようとして 404 になった．

## 対応

原因は一過性の競合であり，PR の差分内容とは無関係だった．
失敗した 2 job を `gh run rerun --failed` で再実行し，成功した．

## 今後の対応方針

[docs/architecture.md](../architecture.md) には既存の記載がある．
「複数 job が同じ marker で upsert すると race する」旨である．
ただしこれは summary コメントの競合についての記載である．
今回の delete-comment 404 は reviewdog 内部のクリーンアップ処理の
競合であり，別の現象として整理しておく．

恒久対応（job 分割の廃止や `post-summary` 制御の拡張）は行わない．
発生頻度が低く，再実行で解消するため，現時点ではコストに見合わない．
再発が頻発するようであれば，本リポジトリ自身の CI 構成の見直しを
検討する．対象は `md-lint.yml` と `test-self-lint.yml` が同一 push で
並走する構成である．

## 参照

- [PR #84](https://github.com/tomio2480/github-workflows/pull/84)
- [docs/architecture.md](../architecture.md) の「lint summary コメントの
  投稿」節（同種の race に関する既存の記載）
