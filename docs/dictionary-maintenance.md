# 📖 prh 辞書のメンテナンスガイド

## 要約

表記ゆれ辞書 `prh.yml` は **中央リポジトリで一括管理** する．caller が `@main`（既定）を参照していれば，中央へのマージ時点で次回 PR から新辞書が効く．pinning 利用者（`@v2` major mutable・patch immutable・SHA pin）は対象タグが動くまで反映されない．個別リポジトリだけの規則は repo ローカルに `.prh-extra.yml` を置いて中央辞書へ加算する（v2.7〜）．中央辞書を丸ごと差し替えたい場合のみ repo ローカルに `prh.yml` を置く（override）．

## 目次

- 🎯 辞書を更新する場面
- 1️⃣ 中央辞書への追記フロー
- 2️⃣ per-repo の辞書追加と override
- 3️⃣ prh.yml の書き方
- 4️⃣ バージョニングと影響範囲
- 5️⃣ prh・caller 追加辞書・allowlist の使い分け

## 🎯 辞書を更新する場面

- 社名・プロダクト名・技術名に表記ゆれがある（`GitHub` vs `github`）
- 新しい用語を組織で統一したい
- 特定 repo 固有の専門用語や書式規則がある

最初の 2 つは中央追記，最後は per-repo の `.prh-extra.yml` が向く．

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

マージされると `@main` 参照の caller には次回 PR から新辞書が適用される．`@v2` major mutable 利用者には patch tag を切って major mutable を進めたタイミングで反映される．`@v2.2.0` のような patch immutable 利用者は固定のため，新 patch（例: `@v2.2.1`）への明示的な切り替えが必要．SHA pin 利用者には Dependabot が更新 PR を起票する．詳細は後述．

## 2️⃣ per-repo の辞書追加と override

repo 固有の規則を扱う手段は 2 つある．まず追加方式を検討し，足りない場合だけ override を選ぶ．

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）．以降の表も同様． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: caller 側で辞書を調整する 2 方式

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 方式 | 置くファイル | 中央辞書との関係 | 向く場面 |
|---|---|---|---|
| 追加（v2.7〜） | `.prh-extra.yml` | 中央に加算．中央更新へ追随できる | 読点の流儀など repo 固有の規則を足す |
| override | `prh.yml` | 中央を無視して全置換 | 中央規則を変えたい・減らしたい |

### 追加方式（`.prh-extra.yml`）

caller root に `.prh-extra.yml` を置くと，composite action が追加辞書として拾う．
textlint には `rulePaths` を `[中央 prh.yml, .prh-extra.yml]` の 2 本にして渡す．
中央辞書はそのまま効くため，中央の更新に取り残されない．

```bash
# OWNER は中央リポジトリのオーナー（fork 運用では自分のユーザー名）
OWNER=tomio2480

# 対象 repo のルートで雛形を取得し，rules に規則を書く
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.prh-extra.yml" \
  > .prh-extra.yml
```

同じパターンを中央辞書と `.prh-extra.yml` の両方に書くこともできる．
その場合 `textlint-rule-prh` は先に並べた中央辞書の `expected` を採用する（v6.1.0 で実測）．
追加辞書で中央規則は上書きできない．
中央の指摘を外したい語は `.textlint-allowlist.yml` の `allow` で除外する．
中央規則そのものを変えたい場合は次の override 方式を使う．

`prh.yml`（override）と `.prh-extra.yml`（追加）は両方置ける．
その場合 `rulePaths` は `[caller prh.yml, .prh-extra.yml]` になる．
つまり置き換え辞書を基点に追加辞書が加算される．

### override 方式（`prh.yml`）

repo 固有の辞書を中央から分離したい場合．

```bash
# OWNER は中央リポジトリのオーナー（fork 運用では自分のユーザー名）
OWNER=tomio2480

# 対象 repo のルートで
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/prh.yml" \
  > prh.yml
```

取得した `prh.yml` を編集・コミットすれば，その repo だけ override が効く．中央との乖離を許容する運用となる点に注意．

## 3️⃣ prh.yml の書き方

prh は YAML で記述する．最低限必要なのは `version` と `rules`．

```yaml
version: 1
rules:
  - expected: GitHub
    patterns:
      - /github/i
      - Github
      - GITHUB
    prh: github は GitHub と表記する
```

主要フィールドは次のとおり．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: prh 辞書の主要フィールド

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| フィールド | 役割 |
|---|---|
| `expected` | 正解の表記 |
| `patterns` | 検出対象．正規表現（`/.../i` 形式）または文字列配列 |
| `prh` | 指摘メッセージ |
| `specs` | 期待する変換結果の例（テスト用） |

詳細仕様は [prh 公式](https://github.com/prh/prh) を参照．

### 正規表現で前後スペースを拾うパターン

文字の前後にある半角スペースを検出したいとき，`/ +X +| +X|X +/` の形式を使う．
以下は `・` 1 シンボルの例である．

```yaml
- expected: ・
  patterns:
    - / +・ +| +・|・ +/
  prh: 全角中黒「・」の前後に半角スペースを入れない（JTF スタイル）
  specs:
    - from: CI ・ cron
      to: CI・cron
    - from: 日本語 ・英語
      to: 日本語・英語
    - from: a・ b
      to: a・b
```

prh は同一 rule 内の複数 pattern を alternation に合成して `/g` 適用する．
leading と trailing を別 pattern に分割すると合成後が `/(?: +・|・ +)/gmu` になる．
両側スペース入力で後続スペースを取りこぼして spec が落ちる点に注意が必要である．
長い順 alternation `/ +X +| +X|X +/` を 1 本書くことで leftmost-longest が機能する．
両側スペースを 1 マッチで処理できる点がこの記法の利点である．
量指定子 `+` を使うことでシングルスペース・ダブルスペース等の typo も一括して扱える．

`JS` の word boundary 例（`/\bJS\b/`）と同様に，plain string では拾えない場合がある．
空白コンテキストを正規表現で解決する事例として並べて参照されたい．

lint 上は両側スペース行で 1 件の diagnostic が出る．
`--fix` を 1 回適用すると両端が同時に解消される動作になる．

### substring match を避けるパターン

prh の plain string パターンは substring match で動く．
`ユーザ` を裸で書くと正しい表記の `ユーザー` 内の `ユーザ` にもヒットして誤検出する．
否定先読み `/ユーザ(?!ー)/` で次に `ー` が続かないケースに絞る（Issue #33 で観測．[notes/2026-05-03-prh-user-negative-lookahead.md](notes/2026-05-03-prh-user-negative-lookahead.md)）．

```yaml
- expected: ユーザー
  patterns:
    - /ユーザ(?!ー)/
  specs:
    - from: ユーザ登録
      to: ユーザー登録
    - from: ユーザー登録
      to: ユーザー登録
```

`from === to` の spec は「変換されないことの assert」として機能する．
否定先読みの効きを YAML 内自己テストで担保するために配置する．

`JS` の word boundary 例（`/\bJS\b/`）も同根の対処である．
plain string で書くと `JSON Lines` 等の語に誤マッチするため `\bJS\b` で囲んで境界を明示する．
日本語には word boundary が効かないため，否定先読み・後読みで境界を作る形になる．

## 4️⃣ バージョニングと影響範囲

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 3: 参照方式と反映タイミング

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| caller の参照先 | 辞書変更が反映されるタイミング |
|---|---|
| `@main` | 中央 main へのマージで次回 PR から即反映．即時性重視の利用者向け |
| `@v2` major mutable | patch リリースごとに最新 patch へ進められる．caller の介入なしで追従 |
| `@v2.2.0` patch immutable | 原則反映されない（固定）．新 patch へ切り替える明示的な操作が必要 |
| `@<SHA> # v2.2.0`（既定） | SHA pin．Dependabot がタグの更新を検知して caller に PR を起票 |

patch リリースは PR マージごとに切る運用とする．major mutable は同時に最新 patch へ進める．

```bash
# PR マージ後の定例リリース（タグ発行 → Release 作成 → major mutable 追従）
bash bin/release-patch.sh v2.2.1 <merge-sha-full> --notes-file notes.md
# PowerShell 環境の場合
# powershell -ExecutionPolicy Bypass -File bin\release-patch.ps1 `
#   -Version v2.2.1 -MergeSha <merge-sha-full> -NotesFile notes.md
```

スクリプトが実行する手順は次の手動コマンドに相当する．
手動で行う場合もこの順序を守る（タグを先に push し，
`gh release create` に `--target` を付けない）．
スクリプトはこれに加えて 2 点を担う．
1 点目は途中失敗後の再実行であり，作成済みのタグと Release をスキップする．
2 点目は major mutable の push を `--force-with-lease` で保護することである．

```bash
git tag v2.2.1 <merge-sha>
git push origin v2.2.1
gh release create v2.2.1 --title "v2.2.1" --notes "..."
git tag -f v2 v2.2.1
# 直前に観測した remote の値を期待値に置き，並行実行時の巻き戻りを防ぐ
git push --force-with-lease=refs/tags/v2:<observed-sha> origin v2
```

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 4: 変更種別ごとの扱い

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 変更種別 | タグ運用 |
|---|---|
| 辞書エントリ追加 | patch リリース（`vX.Y.Z+1`）として切る．major mutable も同時に進める |
| 辞書エントリ削除・変更 | 既存 caller の指摘が意図せず変わるため事前に影響確認．破壊性に応じて patch / minor のどちらで切るかを判断 |
| prh.yml スキーマへの非破壊的追加 | minor リリース（`vX.Y+1.0`）として切る．major mutable も進める |
| prh.yml スキーマの破壊的変更 / `action.yml` inputs の意味変更・required 化 | 後方非互換のため新 major（`vX+1`）を切る．旧 major は据え置き |

破壊的変更の場合は CLAUDE.md のタグ運用規律に従う．

## 5️⃣ prh・caller 追加辞書・allowlist の使い分け

caller root に `.textlint-allowlist.yml` を置くと，固有の例外を textlint 指摘から外せる．
v2.1 以降の機能で，差分追加方式のため中央設定は変更しない．prh とは目的が異なる．
v2.7 以降は `.prh-extra.yml` で caller だけの表記ゆれ規則を足せる（2️⃣ 参照）．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 5: 中央 prh・caller 追加辞書・caller-side allowlist の使い分け

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 観点 | `templates/prh.yml`（中央） | `.prh-extra.yml`（caller） | `.textlint-allowlist.yml`（caller） |
|---|---|---|---|
| 目的 | 全 caller 共通の表記ゆれ統一 | caller 固有の表記ゆれ統一 | 固有名詞・法令名等の例外許容 |
| 対象 | すべての caller | 配置した caller のみ | 配置した caller のみ |
| 例 | `github` → `GitHub` | 読点 `、` → `，` | `電波法施行規則` を `max-kanji-continuous-len` から除外 |
| 反映 | 中央 PR 経由で全 caller に反映 | caller 単独で完結．中央 PR 不要 | caller 単独で完結．中央 PR 不要 |
| スキーマ | prh 仕様 | prh 仕様 | [textlint-filter-rule-allowlist 仕様](https://github.com/textlint/textlint-filter-rule-allowlist) |

新しい例外語が出たら，まず「これは表記ゆれか」を確認する．
表記ゆれなら，全 caller に共通する語は中央 prh へ追記し，caller 単独の規則は `.prh-extra.yml` に書く．
固有名詞の特殊事情なら caller 側 allowlist が向く．

caller 側 allowlist の導入手順は次のとおり．

```bash
OWNER=tomio2480

# サンプルを取得して必要部分のコメントを外す
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.textlint-allowlist.yml" \
  > .textlint-allowlist.yml
```

allowlist の書式は次のとおり．

- `allow:`：文字列または `/regex/` の配列．マッチ範囲に入る指摘を除外する．
- ルール単位の無効化オプションは存在しない（Issue #97）．
  `allowRules` は `textlint-filter-rule-allowlist` に無い鍵で，フィルタは解釈しない．
  `allow` と `allowlistConfigPaths` 以外の鍵を書くと，
  実行時に `::warning::` アノテーションで無視される旨を知らせる（Issue #98）．
  ルールを丸ごと外したいときは `<!-- textlint-disable ルール名 -->` を使う．
  `.textlintignore` はファイル全体の除外であり，全ルールが効かなくなる．
  文体だけを理由に使わない．
  帰結は [Issue #85 の記録](notes/2026-08-16-issue85-textlint-overrides-unsupported.md) を参照．

`allow` の正規表現は範囲マッチである．マッチした範囲に入る指摘だけが消える．
図表キャプションの句点指摘を外す実測済みの書き方を次に示す．

```yaml
allow:
  - '/(?<=^[表図] [0-9]+[.] .*)[^．。.]$/m'
```

後読みでキャプション行に限定し，マッチは末尾 1 文字に絞る．
行全体に当てると，同じ行の他ルールの指摘まで道連れに消えるため避ける．
終端の文字クラスは「．」に加え「。」「.」も除いている．
誤った句点で終わるキャプションを例外化せず，指摘対象に残すためである．
番号の区切り記号（`.` や `:`）は caller のキャプション書式に合わせて調整する．
