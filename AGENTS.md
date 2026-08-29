# AGENTS.md

本リポジトリで Codex が作業・レビューする際の指示である．

## リポジトリの役割

- 複数 repo から再利用する GitHub Actions と caller template を管理する．
- repo 固有の lint・test ロジックは caller 側へ置き，本リポジトリは setup と呼び出しを担う．
- 既存の設計判断は `docs/architecture.md` と `docs/notes/` を正とする．

## 変更と検証

- reusable workflow と third-party action は full commit SHA で pin する．
- caller から受け取る path と値は quoting し，command string として評価しない．
- `pull_request_target` と `secrets: inherit` は使わない．
- reusable workflow の変更は local caller による self-test job を追加・更新する．
- `scripts/` のロジック変更は `tests/` で test-first に進める．
- Markdown の書式は既存の Markdown lint・textlint CI を正とする．

## GitHub 運用

- push，tag，release，Ready 化，merge はユーザーの指示を得てから行う．
- PR を作る場合は Draft とする．
- caller template の既定は中央 repo の full commit SHA pin とする．
