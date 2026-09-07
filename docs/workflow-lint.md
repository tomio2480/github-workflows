# 🧪 Workflow 検査 composite action

caller の workflow ファイル自身を検査する composite action の導入と契約をまとめる．
`actionlint` で構文を検査し，`uses:` の SHA pin を上流と突き合わせる．
pin の突合は 3 段に分かれ，古いだけの pin は警告にとどめる．

## 目次

- 🎯 何を解決するか
- 🚀 導入
- ⚙️ 入力
- 🔍 検査の内容
- 📐 pin 突合の判定
- 🚫 検査の対象外
- 🔒 権限と supply chain
- 🧪 中央自身への自己適用

## 🎯 何を解決するか

`.github/workflows/*.yml` だけを変更する PR では，`paths` を持つ caller が
1 つも起動しない．結果として次が起きる．

- SHA ピンの更新で，参照先が実在するか，YAML が壊れていないかすら検査されない．
- Dependabot の Actions 更新 PR が無検証のままマージ可能になる．

実測では `gh pr checks` が `no checks reported` を返した．
経緯は `tomio2480/settings` の Issue #304 にある．

本 action はこの穴を塞ぐ．caller は `paths` へ
`.github/workflows/**` と `.github/actions/**` を含める．

## 🚀 導入

caller template を対象リポジトリへコピーする．

```bash
OWNER=tomio2480
SHA=$(gh api "repos/${OWNER}/github-workflows/git/refs/tags/v2" --jq '.object.sha')
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/workflow-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/workflow-lint.yml
```

置換はヘッダーコメント中の `@<SHA>` にも及ぶ．
配置後にコメントを読み，テンプレ向けの置換手順が残っていれば
自リポジトリ向けの説明へ書き換える．

caller 側で `actions/checkout` が要る．`session-url-check` と違い，
API の読み取りだけでは完結しないためである．

## ⚙️ 入力

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: composite action の入力

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 入力 | 既定 | 説明 |
| --- | --- | --- |
| `github-token` | 必須 | 上流突合に使う．`secrets.GITHUB_TOKEN` を渡す |
| `pin-globs` | 空 | pin を走査する glob．改行区切り．空なら既定を使う |
| `allow-empty` | `false` | pin を 1 件も持たない repo を成功として扱うか |
| `verify-upstream` | `true` | SHA の実在と版コメントの系譜を上流へ問い合わせるか |

`pin-globs` の既定は次の 4 つである．

```text
.github/workflows/*.yml
.github/workflows/*.yaml
.github/actions/**/action.yml
.github/actions/**/action.yaml
```

拡張子は双方を見る．GitHub は workflow を `.yml` と `.yaml` の双方で認識する．
composite action の定義も `action.yaml` が有効である．
composite action は `**` で受ける．`.github/actions/<group>/<name>/action.yml` の
ような入れ子も有効な構成であり，`*` では漏れる．

## 🔍 検査の内容

### actionlint

`.github/workflows` 直下の `.yml` と `.yaml` を検査する．
版を固定し `sha256sum --check --strict` で検証してから使う．
検査対象は実行の冒頭でログへ列挙する．対象 0 件は失敗させる．

`actionlint` は指摘が無いと何も出さないため，対象を出さないと
走査が空振りした結果と成功が区別できない．

### action pins

`uses:` の SHA pin を収集し，リポジトリ内部の整合と上流との突合を行う．
内部整合は次の 4 つである．

- 同じ action が複数の SHA へ pin されていないこと．
- すべての pin が行末に版コメントを持つこと．
- 版コメントが `vX`〜`vX.Y.Z` の形であること．
- 同じ SHA へ 2 通りの版表記が書かれていないこと．

加えて，SHA で pin されていない remote 参照を失敗として報告する．

さらに，**収集できる形になっていない `uses` も失敗として報告する** ．
Issue #211 の対応である．収集は `uses: <action>@<SHA> # vX.Y.Z` の 1 行を対象とする．

表 1 に，YAML としては成立するが収集できない書き方を示す．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 収集できない `uses` の書き方

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 書き方 | 例 |
|---|---|
| 値を次行へ置く | `uses:` の下の行へ値を書く |
| flow mapping | `- {uses: owner/repo@<SHA>}` |
| コロン前に空白 | `uses : owner/repo@<SHA>` |
| 引用符付きの鍵 | `- "uses": owner/repo@<SHA>` |

収集できないまま通すと，そこに書かれた pin はどの検査にも掛からない．
**検査は成功したまま素通りする．**

これらの形を許さないのは素通りを避けるためだけではない．
Dependabot が書き換えるのは 1 行の形だけである．
別の形へ置くと，版コメントの規律（Issue #157）がそもそも成立しない．

判定には YAML の解釈が要る．
「その `uses` は mapping の鍵か，文字列の中身か」を決める必要がある．
鍵の引用・値の引用・block scalar の指示子・flow mapping の構造が絡む．
行単位の正規表現では答えられない．action は `PyYAML` を用意してから script を呼ぶ．

YAML として解釈できないファイルと，`PyYAML` を用意できない環境は，
いずれも検査を省かずに失敗させる．省くと素通りと区別が付かないためである．

## 📐 pin 突合の判定

`verify-upstream` が真のとき，上流へ問い合わせて 3 段に判定する．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: 上流突合の判定と扱い

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 判定 | 扱い |
| --- | --- |
| SHA が上流に実在しない | 失敗 |
| 版コメントの系譜に SHA が属さない | 失敗 |
| 最新タグより古い | 警告 |

最新タグとの一致を失敗にすると，中央が patch を切った瞬間に全 caller が
赤くなる．版コメントを major のみへ改めた狙い（Issue #142）とも衝突するため，
追随は Dependabot の担当領域として警告にとどめる．
警告は標準出力へ残す．緑のまま古い pin が放置される状態を見えなくしない．

可動タグ（`# v2`・`# v2.19`）は系譜に属していれば通す．
固定タグ（`# v2.19.5`）は同じ commit を指していることを求める．
固定タグは動かないため，祖先を許すと別リリースの SHA へ誤った版を
書いた状態を見逃す．

### 確かめられなかったことを，確かめた結果と区別する

一過性のレート制限や 5xx を「実在しない」と読み替えない．
読み替えると，pin は壊れていないのに壊れていると報告することになり，
利用者は直しようのない指摘を受け取る．

権限で読めない repository も同様である．GitHub は権限の無い private resource
にも 404 を返すため，repository 自体の可視性を確かめてから判定する．
読めないなら「確かめられなかった」として扱う．

## 🚫 検査の対象外

- ローカル action（`./` 始まり）．上流を持たないため pin の対象ではない．
- 配布テンプレの未置換プレースホルダ（`@<SHA>`）．
  山括弧を含む ref は git の参照として成立せず，浮動参照と区別できる．
- `docker://` 形式の参照．上流の SHA を持たないため pin の対象ではない．

## 🔒 権限と supply chain

caller へ求める権限は `contents: read` だけである．
`github-token` は上流突合の読み取りにのみ使う．

third-party action は使わない．Dependabot の追随対象は増えない．
`actionlint` はリリース資産を版固定で取得し，`sha256` を検証してから
`install` する．検証前に実行しない．

`PyYAML` は runner に導入済みならそれを使い，無いときだけ版を固定して取得する．
`ubuntu-latest` では導入済みであり，取得の経路は通らない．
2026-09-07 の実測では `6.0.1` が入っていた．

取得する場合は `actionlint` と違い `sha256` の検証を行わない．
**この 1 点だけ供給網の面積が広い．**
self-hosted runner など導入されていない環境で取得を避けるには，
caller 側で先に `PyYAML` を用意する．

対応する runner は linux/amd64 に限る．他の runner で呼ばれた場合は，
対応範囲を示して落とす．

## 🧪 中央自身への自己適用

`test-self-lint.yml` の `integration-workflow-lint` job が本 action を走らせる．
対象は中央自身の workflow と composite action，そして `templates/` である．

`templates/` を走査範囲へ含めるのは，そこが Dependabot の走査対象外で
pin が取り残されやすいためである（Issue #156）．

## 📚 参照

- 発端: `tomio2480/settings` の Issue #304
- 設計: 本リポジトリの Issue #200，PR #202・#204
- 版コメントを major のみへ改めた判断: Issue #142
- 走査範囲を `.yaml` と入れ子へ広げた判断: Issue #195，PR #199
