# 📖 prh 辞書のメンテナンスガイド

## 要約

表記ゆれ辞書 `prh.yml` は **中央リポジトリで一括管理** する．すべての対象リポジトリは中央の辞書を参照するため，辞書に追記が入れば全 repo の次回 PR から自動で反映される．個別リポジトリで辞書を独自運用したい場合のみ repo ローカルに `prh.yml` を置く（override）．

## 目次

- 🎯 辞書を更新する場面
- 1️⃣ 中央辞書への追記フロー
- 2️⃣ per-repo の辞書 override
- 3️⃣ prh.yml の書き方
- 4️⃣ バージョニングと影響範囲

## 🎯 辞書を更新する場面

- 社名・プロダクト名・技術名に表記ゆれがある（`GitHub` vs `github`）
- 新しい用語を組織で統一したい
- 特定 repo 固有の専門用語がある

最初の 2 つは中央追記，最後は per-repo override が向く．

## 1️⃣ 中央辞書への追記フロー

```bash
# 中央リポジトリをクローン（または既にあれば pull）
gh repo clone tomio2480/github-workflows
cd github-workflows

# ブランチを切って prh.yml を編集
git checkout -b feature/add-dict-entry
# templates/prh.yml を編集…

# Draft PR を作成
git add templates/prh.yml
git commit -m "dict: add XXX entry"
# push・PR 作成はユーザー確認のうえ実施
```

Draft PR で `filter-mode: nofilter` で実際に lint を流し，辞書の想定通りの挙動を確認してから Ready にする．

マージされると `v1` 参照のすべての caller が次回 PR から新辞書を使う．

## 2️⃣ per-repo の辞書 override

repo 固有の辞書を中央から分離したい場合．

```bash
# 対象 repo のルートで
curl -sSL \
  "https://raw.githubusercontent.com/tomio2480/github-workflows/main/templates/prh.yml" \
  > prh.yml
```

取得した `prh.yml` を編集・コミットすれば，その repo だけ override が効く．中央との乖離を許容する運用になる点に注意．

## 3️⃣ prh.yml の書き方

prh は YAML で記述する．最低限必要なのは `version` と `rules`．

```yaml
version: 1
rules:
  - expected: GitHub
    pattern:
      - /github/i
      - Github
      - GITHUB
    prh: github は GitHub と表記する
```

主要フィールド：

表 1: prh 辞書の主要フィールド

| フィールド | 役割 |
|---|---|
| `expected` | 正解の表記 |
| `pattern` | 検出対象．正規表現（`/.../i` 形式）または文字列配列 |
| `prh` | 指摘メッセージ |
| `specs` | 期待する変換結果の例（テスト用） |

詳細仕様は [prh 公式](https://github.com/prh/prh) を参照．

## 4️⃣ バージョニングと影響範囲

中央 `prh.yml` の変更は `v1` タグを動かさずとも全 caller に波及する（caller が `@v1` で参照しているため）．

表 2: 変更種別ごとの扱い

| 変更種別 | タグ運用 |
|---|---|
| 辞書エントリ追加 | `v1` のまま．追記は非破壊なので全 caller に即反映 |
| 辞書エントリ削除・変更 | 原則 `v1` のまま．ただし既存 caller で意図しない指摘が消える可能性あり．影響大なら `v2` 切り出しも検討 |
| prh 設定の構造変更 | `v2` など新メジャー |

破壊的変更の場合は CLAUDE.md のタグ運用規律に従う．
