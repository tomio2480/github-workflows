# 📚 github-workflows

## 要約

再利用可能な GitHub Actions ワークフローと，各リポジトリ用の設定テンプレートを集約するリポジトリである．Markdown lint を皮切りに，今後 lint/test 系の共通ワークフローを追加していく想定．

## 目次

- 🎯 このリポジトリの目的
- 🗂 ディレクトリ構成
- 🚀 使い方
- 📝 ライセンス

## 🎯 このリポジトリの目的

複数リポジトリに横断的な CI ルールと設定を一箇所で管理し，各リポジトリからは薄い caller workflow と設定ファイルのコピーだけで利用できる状態を作る．Gemini Code Assist のように「どの repo でも同じ品質チェックが走る」状態を目指す．

## 🗂 ディレクトリ構成

```
github-workflows/
├── .github/
│   └── workflows/
│       └── markdown-lint.yml       # 再利用可能ワークフロー本体
├── templates/                      # 各リポジトリにコピーする設定テンプレート群
│   ├── .markdownlint-cli2.yaml
│   ├── .textlintrc.json
│   ├── prh.yml
│   ├── lefthook.yml
│   └── .github/
│       └── workflows/
│           └── md-lint.yml         # 呼び出し側ワークフロー
└── docs/                           # 導入・運用ガイド
    ├── setup-guide.md
    ├── onboarding-new-repo.md
    ├── onboarding-existing-repo.md
    └── dictionary-maintenance.md
```

## 🚀 使い方

新規リポジトリへの導入は `docs/onboarding-new-repo.md` ，既存リポジトリへの導入は `docs/onboarding-existing-repo.md` を参照する．辞書（`prh.yml` ）のメンテナンスは `docs/dictionary-maintenance.md` に従う．

## 📝 ライセンス

MIT License（ `LICENSE` 参照）．再利用可能ワークフローという性格上，公開・再利用を許容するライセンスを選択している．
