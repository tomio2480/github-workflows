# 📖 prh 辞書のメンテナンスガイド

## 要約

`prh.yml` の表記ゆれ辞書を育てていくためのガイドラインをまとめる．辞書は一度作って終わりではなく，執筆・レビューを通じて継続的に追記していくものとして扱う．

## 目次

- 🎯 辞書の位置づけ
- 🔁 追記のトリガー
- ✏️ エントリの書き方
- 🌐 中央辞書と個別辞書
- 🔧 辞書更新時の動作確認

## 🎯 辞書の位置づけ

辞書は以下を目的とする．

- 用語の表記を統一し，文章全体の一貫性を保つ
- プロジェクト固有の用語（製品名・コミュニティ名など）を正しい綴りに矯正する
- 「サーバ／サーバー」のような長期論争系のゆれを，プロジェクトとして決着させる

一方で，辞書は **ルールブックではなく語彙集** である．規約的な判断（敬体／常体の使い分けなど）は textlint の他のルールに委ねる．

## 🔁 追記のトリガー

以下のタイミングで追記を検討する．

1. textlint が辞書に載っていない表記ゆれを見逃したとき
2. レビューで「表記を揃えましょう」と指摘されたとき
3. 新しい固有名詞（カンファレンス名・OSS 名・サービス名）を最初に登場させたとき
4. 社外公開予定のドキュメントを書き始める前（ブログ・登壇資料・同人誌）

## ✏️ エントリの書き方

基本形は以下である．

```yaml
- expected: GitHub
  patterns:
    - Github
    - github
    - GITHUB
```

`expected` は「あるべき表記」， `patterns` は「矯正対象の表記」．正規表現も使える．

```yaml
- expected: Node.js
  patterns:
    - /[Nn]ode\.JS/
    - NodeJS
    - nodejs
```

置換先をパターンごとに変えたい場合は `specs` を使う．

```yaml
- expected: JavaScript
  patterns:
    - Javascript
    - javascript
  prh:
    - specs:
        - from: JS
          to: JavaScript
```

### エントリ追加時のチェックリスト

- [ ] `expected` が実際に「あるべき表記」になっているか（大文字小文字含む）
- [ ] `patterns` に過剰なマッチが含まれていないか（コードブロック内に影響しないか）
- [ ] 日本語カタカナ系（サーバー／ユーザー）の場合，プロジェクト全体で統一意思があるか

## 🌐 中央辞書と個別辞書

中央リポジトリ `github-workflows` の `templates/prh.yml` は **共通ベース辞書** として扱う．各リポジトリは初期導入時にこれをコピーし，そのリポジトリ固有の用語を追記していく．

共通ベース辞書に追加すべき語（全プロジェクトで使う用語）を見つけたら，中央リポジトリに PR を出す．

```bash
# 中央リポジトリで作業
cd ~/workspace/github-workflows
git checkout -b dict/add-new-terms
# templates/prh.yml を編集
git add templates/prh.yml
git commit -m "dict: add new terms to shared dictionary"
# gh pr create --draft ...
```

プロジェクト固有の語は，そのプロジェクトの `prh.yml` にだけ追記する．

## 🔧 辞書更新時の動作確認

辞書を編集したら，既存ドキュメントで確認する．

```bash
# 既存ドキュメント全体に対して lint をかけ直す
npx textlint "**/*.md"

# 特定のファイルだけ確認する場合
npx textlint README.md
```

過剰マッチ（意図しない箇所での矯正）が発生していないかを diff で確認する．

```bash
npx textlint --fix "**/*.md"
git diff
```

問題があれば辞書の `patterns` を絞り込む．
