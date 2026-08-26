# caller テンプレートの構造変更が伝播しない問題への対応方針

## 背景

caller テンプレートの構造変更は，既存 caller に伝わらない．
経緯は [Issue #83](https://github.com/tomio2480/github-workflows/issues/83) を参照．
対象は composite action（`.github/actions/markdown-lint`）である．
変更元は `templates/.github/workflows/md-lint.yml` である．

PR #77 で追加した `concurrency` と `timeout-minutes` を例に取る．
caller 33 件を全数調査した．
両方を保持していたのは 1 件のみだった．
`chrome-tab-tidy-up` と `techbook-template` は Dependabot で
`v2.6.6` まで追随していた．
それでも構造変更は反映されていなかった．

Dependabot が追随するのは `uses:` の SHA とバージョンコメントのみである．
composite action は，job・workflow のキーを宣言できない．
対象は `concurrency`/`timeout-minutes`/`permissions` 等である．
これらは自分を呼んだ側のキーであるためだ．
caller のファイルを書き換える以外に，中央から効かせる方法がない．
これは実装の不備ではない．
composite action という配布形式そのものの限界である．

## 検討した選択肢

Issue #83 ではコストの低い順に 3 案が示された．

1. リリースノートへ「caller 側対応が必要」の印を付ける運用（実装不要）．
2. composite action が caller の `md-lint.yml` を読む．
   テンプレートとの構造差分を lint summary に注記する（実装要）．
   caller は checkout 済みのため実現できる．
3. 中央からの定期検知＋自動 Issue 化．
   実装・維持コストは大きい．caller 一覧の維持と権限設計が要る．

## 決定

**案 1 を正式な運用ルールとして採用する．**
案 2・3 は Issue #83 に選択肢として残す．
今回のセッションでは実装しない．

判断理由は次のとおりである．

- 案 1 はコストゼロで即座に導入できる．
  次に構造変更を加える場面での再発を防げる．
  今回の PR #77 には印がなかった．
  caller 側で気づけたのは偶然だった．
- 案 2 は composite action の実装追加を要する．規模が大きい．
  まず運用でカバーし，そのうえで要否を見直す方が手戻りは少ない．
- 案 3 は caller 一覧という新たな維持対象を要する．
  横断アクセス権限の設計も要る．現時点では過剰投資と判断した．

併せて設計指針を明文化した．
job・workflow レベルの設定が必要な新機能は，composite action でなく
reusable workflow 形式を優先検討する．
反映先は [docs/architecture.md](../architecture.md) である．
`claude-review`（reusable workflow 形式）は好例である．
`concurrency` と `timeout-minutes` は，いずれも中央だけで完結する．
今回のような伝播漏れは起こらない．

## 見送った対応

- **32 件の caller への backfill は見送る．**
  対象は `concurrency`/`timeout-minutes` である．
  fleet 規模の作業になるためである．
  各 caller が Dependabot でバージョンを上げた際に手動で追従するか，
  別途まとまった対応を検討する．
- **案 2（差分注記機能）の実装も見送る．**
  規模が大きいためである．
  運用（案 1）を試したうえで，再発頻度が高ければ実装を検討する．

## 反映先

- [docs/architecture.md](../architecture.md) を更新した．「caller テンプレートの構造変更が伝播しない問題」節を新設した．
  composite action と reusable workflow の吸収範囲の違いを明文化した．
  併せて運用ルールも明文化した．
- [CLAUDE.md](../../CLAUDE.md) を更新した．「テンプレート・設定ファイルの変更」節に規律を追記した．
  対象は job・workflow レベルのキー変更時の運用である．
