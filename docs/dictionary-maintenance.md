# 📖 prh 辞書のメンテナンスガイド

## 要約

表記ゆれ辞書 `prh.yml` は **中央リポジトリで一括管理** する．caller が `@main`（既定）を参照していれば，中央へのマージ時点で次回 PR から新辞書が効く．pinning 利用者（`@v1` / `@v1.0.0`）は対象タグが移動されるまで反映されない．個別リポジトリで辞書を独自運用したい場合のみ repo ローカルに `prh.yml` を置く（override）．

## 目次

- 🎯 辞書を更新する場面
- 1️⃣ 中央辞書への追記フロー
- 2️⃣ per-repo の辞書 override
- 3️⃣ prh.yml の書き方
- 4️⃣ バージョニングと影響範囲
- 5️⃣ prh と caller-side allowlist の使い分け

## 🎯 辞書を更新する場面

- 社名・プロダクト名・技術名に表記ゆれがある（`GitHub` vs `github`）
- 新しい用語を組織で統一したい
- 特定 repo 固有の専門用語がある

最初の 2 つは中央追記，最後は per-repo override が向く．

## 1️⃣ 中央辞書への追記フロー

```bash
# OWNER は中央リポジトリのオーナー（fork 運用では自分のユーザー名）
OWNER=tomio2480

# 中央リポジトリをクローン（または既にあれば pull）
gh repo clone "${OWNER}/github-workflows"
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

マージされると `@main` 参照の caller には次回 PR から新辞書が適用される．`@v1` / `@v1.0.0` pinning 利用者には反映されないため，pinning 利用者向けに反映したい場合は別途タグを移動する必要がある（後述）．

## 2️⃣ per-repo の辞書 override

repo 固有の辞書を中央から分離したい場合．

```bash
# OWNER は中央リポジトリのオーナー（fork 運用では自分のユーザー名）
OWNER=tomio2480

# 対象 repo のルートで
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/prh.yml" \
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

表 2: 参照方式と反映タイミング

| caller の参照先 | 辞書変更が反映されるタイミング |
|---|---|
| `@main`（既定） | 中央 main へのマージで次回 PR から即反映 |
| `@v1` | 中央が `v1` タグを移動したときのみ反映 |
| `@v1.0.0` | 原則反映されない（固定） |

pinning 利用者（`@v1` / `@v1.0.0`）への反映が必要な変更を入れた場合はタグ運用を検討する．

```bash
# v1 参照の利用者に最新 main を反映したい場合（要注意・事前通知必須）
git tag -f v1 main
git push -f origin v1
```

表 3: 変更種別ごとの扱い

| 変更種別 | タグ運用 |
|---|---|
| 辞書エントリ追加 | `@main` 利用者には即反映．pinning 利用者に反映したい場合のみ `v1` を移動 |
| 辞書エントリ削除・変更 | `@main` 利用者の指摘が意図せず変わるため事前に影響確認．`v1` 移動は慎重に |
| prh 設定の構造変更 | `v2` など新メジャーを切る．`v1` はそのまま維持 |

破壊的変更の場合は CLAUDE.md のタグ運用規律に従う．

## 5️⃣ prh と caller-side allowlist の使い分け

caller root に `.textlint-allowlist.yml` を置くと，固有の例外を textlint 指摘から外せる．
v2.1〜 の機能で，差分追加方式のため中央設定は変更しない．prh とは目的が異なる．

表 4: prh と caller-side allowlist の使い分け

| 観点 | `templates/prh.yml`（中央） | `.textlint-allowlist.yml`（caller） |
|---|---|---|
| 目的 | 表記ゆれの統一 | 固有名詞・法令名等の例外許容 |
| 対象 | すべての caller | 配置した caller のみ |
| 例 | `github` → `GitHub` | `電波法施行規則` を `max-kanji-continuous-len` から除外 |
| 反映 | 中央 PR 経由で全 caller に反映 | caller 単独で完結．中央 PR 不要 |
| スキーマ | prh 仕様 | [textlint-filter-rule-allowlist 仕様](https://github.com/textlint/textlint-filter-rule-allowlist) |

新しい例外語が出たら，まず「これは表記ゆれか」を確認する．表記ゆれなら中央 prh 追記，固有名詞の特殊事情なら caller 側 allowlist が向く．

caller 側 allowlist の導入手順は次のとおり．

```bash
OWNER=tomio2480

# サンプルを取得して必要部分のコメントを外す
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.textlint-allowlist.yml" \
  > .textlint-allowlist.yml
```

allow / allowRules は次のように使い分ける．

- `allow:` ：対象テキスト（文字列または `/regex/`）を丸ごと指摘から除外する
- `allowRules:` ：特定のルール ID を caller 全体で無効化する
