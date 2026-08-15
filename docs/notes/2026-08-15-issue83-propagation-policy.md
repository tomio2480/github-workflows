# caller テンプレートの構造変更が伝播しない問題への対応方針

## 背景

[Issue #83](https://github.com/tomio2480/github-workflows/issues/83) にて，
composite action（`.github/actions/markdown-lint`）の caller テンプレート
（`templates/.github/workflows/md-lint.yml`）に加えた構造変更が，
既存 caller に伝わらない実態が報告された．PR #77 で追加した `concurrency` と
`timeout-minutes` を例に caller 33 件を全数調査した結果，両方を保持するのは
1 件のみだった．`chrome-tab-tidy-up` と `techbook-template` は Dependabot で
`v2.6.6` まで追随済みだが，それでも構造変更は反映されていなかった．

Dependabot が追うのは `uses:` の SHA とバージョンコメントのみであり，
composite action は自分を呼んだ job・workflow のキー（`concurrency` ／
`timeout-minutes` ／ `permissions` 等）を宣言できない．caller のファイルを
書き換える以外に中央から効かせる方法がなく，これは実装の不備ではなく
composite action という配布形式そのものの構造的な限界である．

## 検討した選択肢

Issue #83 ではコストの低い順に 3 案が示された．

1. リリースノートへ「caller 側対応が必要」の印を付ける運用（実装不要）
2. composite action が caller の `md-lint.yml` を読み，テンプレートとの
   構造差分を lint summary に注記する（実装要，caller は checkout 済みのため
   実現可能）
3. 中央からの定期検知＋自動 Issue 化（実装・維持コスト大，caller 一覧の
   維持と権限設計が要る）

## 決定

**案 1 を正式な運用ルールとして採用する．** 案 2・3 は Issue #83 に選択肢として
残し，今回のセッションでは実装しない．

判断理由は次のとおり．

- 案 1 はコストゼロで即座に導入でき，再発（次に job・workflow レベルの
  設定を変更する場面）を予防できる．今回の PR #77 には印がなく，
  caller 側で気づけたのは偶然だった．
- 案 2 は composite action の実装追加を要し，規模が大きい．
  効果はあるが，まず運用でカバーしてから要否を見直す方が手戻りが少ない．
- 案 3 は caller 一覧という新たな維持対象と，横断アクセス権限の設計を
  要する．現時点では過剰投資と判断した．

併せて，設計指針として「job・workflow レベルの設定が必要な新機能は
composite action ではなく reusable workflow 形式を優先検討する」旨を
[docs/architecture.md](../architecture.md) に明文化した．`claude-review`
（reusable workflow 形式）であれば `concurrency` も `timeout-minutes` も
中央だけで完結し，今回のような伝播漏れは起こらない．

## 見送った対応

- **32 件の caller への `concurrency` / `timeout-minutes` backfill**：
  fleet 規模の作業になるため今回は見送る．各 caller が Dependabot で
  バージョンを上げた際に手動で追従するか，別途まとまった対応が要る．
- **案 2（差分注記機能）の実装**：規模が大きいため見送る．
  運用（案 1）を試した上で，再発頻度が高いようなら実装を検討する．

## 反映先

- [docs/architecture.md](../architecture.md)：「caller テンプレートの構造変更が
  伝播しない問題」節を新設し，composite action と reusable workflow の
  吸収範囲の違いと運用ルールを明文化した．
- [CLAUDE.md](../../CLAUDE.md)：「テンプレート・設定ファイルの変更」節に，
  job・workflow レベルのキー変更時はリリースノートへ明示する規律を追記した．
