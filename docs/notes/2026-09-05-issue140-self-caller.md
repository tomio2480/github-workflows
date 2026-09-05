# 中央自身の `@claude` 導線と，代替案の効果を先に測ること（Issue #140）

## 要約

中央リポジトリの PR で `@claude` が起動しなかった問題を，self-caller の新設で
解決した．設計の争点はメンション判定の `if:` をどこへ置くかだったが，検討の
過程で「代替案の効果を測らないまま副作用を論じていた」誤りが露見した．
本稿はその誤りの構造と，受け入れ条件の解釈を確定させた経緯を残す．

## 目次

- 背景
- 判断
- 誤りの構造：効果を測らずに副作用を論じた
- 受け入れ条件の解釈
- 代替案と棄却理由
- レビューから得たもの
- 参照

## 背景

`.github/workflows/claude-review.yml` は `on: workflow_call` 専用であった．
`issue_comment` を受ける caller は `templates/` 側にしか無かった．
中央リポジトリの default ブランチには，有効な workflow が無い状態である．
結果として，中央の PR で `@claude` をメンションしても，
Actions run と Bot 応答のどちらも生成されなかった．

回避のため別リポジトリの caller からレビューを依頼した経緯がある．
Claude の sandbox が別リポジトリへの読み取り権限を取れず，差分を丸ごと
コメントへ転載する形になった．レビュー対象と実行場所が分離し，
無関係な PR へ大きな差分が残った．

## 判断

中央専用の self-caller `.github/workflows/claude-review-self.yml` を新設した．
`uses: ./.github/workflows/claude-review.yml` でローカル呼び出しする．
trigger と `permissions` は配布用テンプレートと同一で，差分は `uses` だけである．

メンション判定の `if:` は reusable workflow 側（中央）へ置いたままとした．
採った原則は次のとおりである．

> caller へ置くのは，GitHub の仕様が caller に置くことを強制するものだけとする．

`on:` は caller にしか書けない．`permissions` は called 側の宣言が caller の
付与を超えられないため，同じく caller に要る．`if:` はどちらにも置けるため，
中央へ集約する．

## 誤りの構造：効果を測らずに副作用を論じた

当初，`if:` を caller へ移す案の検討で次の 2 点を根拠に現状維持を結論づけた．

1. `skipped` は runner 時間を消費しないので実害がない．
2. 移すと判定が caller ごとへ複製され，Dependabot が追随しないため中央から
   差し替えられなくなる．

**この 2 点はどちらも，潰すべき前提を潰していない．**
移しても workflow run の件数は 1 件も変わらないからである．
run は `on:` が event に一致した時点で作られ，job の `if:` はその後に評価される．
どちらへ置いても対象外のコメントは `skipped` として記録される．

つまり代替案は，期待された効果をゼロしか生まない．そこを先に測っていれば，
副作用の大小も Dependabot の制約も論じる必要が無かった．

根拠 2 には別の欠陥もあった．**証明しすぎている．**
同じ論法なら `permissions` も caller へ置けないことになる．
だが仕様上そこにしか置けず，本リポジトリは既にそのコストを支払っている．
Dependabot の制約は絶対的な禁止線ではなく，支払う価値があるかの問題でしかない．

教訓は 1 つである．**選択肢を比べる前に，その選択肢が目的の量をどれだけ動かす
かを測る．** 副作用の議論はその後で足りる．順序を逆にすると，効果ゼロの案に
対して精緻な反論を組み立てることになる．

## 受け入れ条件の解釈

Issue #140 の受け入れ条件に「通常 Issue のコメント，同じメンションの編集，
対象外コメントで不要に起動しない」があった．
これを「run が作られない」と読むか「job が実行されない」と読むかで割れた．

**後者で確定した．** 前者はどう実装しても達成できないためである．
`issue_comment` が受け付けるフィルタは `types` だけであり，コメント本文でも
Issue か PR かの別でも `on:` レベルでは絞れない．
GitHub の公式ドキュメントは `github.event.issue.pull_request` を条件文で
使うよう案内している．job の `if:` が唯一かつ公式推奨の手段である．

一方，「同じメンションの編集」は `types: [created]` の購読で trigger レベルの
まま満たしている．**`on:` で絞れるものは `on:` で，絞れないものは条件文で**
という区別が，条件の書き手の意図と読める．

実測は次のとおりである（caller リポジトリ `settings` の直近 100 run，約 22.8 時間）．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 起動の内訳

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 区分 | 件数 |
|---|---|
| `skipped` | 97 |
| `success` | 3 |
| `issue_comment` 由来 | 48 |
| `pull_request_review_comment` 由来 | 52 |

およそ 105 件/日である．GitHub の上限は `500 workflow runs / 10 秒 / repository`
であり，桁が 4 つ離れているため問題にならない．

この解釈は Issue #140 のコメントで確定させた．
根拠は `.github/workflows/claude-review.yml` と配布テンプレートの双方へ残した．
`skipped` が並ぶのは正常であり，「無反応」を疑うときは run が `skipped` か
`failure` かを先に見る．

## 代替案と棄却理由

### 案 1: reusable workflow 本体へ trigger を直接足す

棄却した．1 つのファイルが「配布する部品」と「中央の稼働 workflow」を兼ねる．
`permissions` の決まり方は呼び出し経路ごとに 2 通りへ分かれる．
中央 direct trigger では job 側の宣言が効き，caller 経由では caller の付与に縛られる．
`docs/security.md` の記述も条件分岐する．

### 案 2: caller へ粗い条件を足す折衷案

棄却した．**破壊的である．**
`if: github.event.issue.pull_request` を caller へ置いたとする．
`pull_request_review_comment` では `github.event.issue` が存在しない．
式は偽に評価される．
実測で 52% を占める最も本来的な起動経路が丸ごと死ぬ．

正しく書くには `github.event_name != 'issue_comment' || ...` の形が要る．
その時点で「粗い条件」ではなく，caller へ焼き付けたロジックになる．
しかも削減効果は上限で 48%，run 件数は 1 件も減らない．

2 箇所に条件を持つ弊害は drift である．食い違ったとき狭い側が勝ち，
起動しない理由が「中央のロジック」ではなく「caller の残骸」になる．
Issue #140 が問題視した「無反応の原因を切り分けられない」状態の再生産にあたる．

## レビューから得たもの

### 検査の走査範囲は，守ろうとしている条件と同じ広さで取る

Codex から P2 の指摘を受けた．二重起動の検査が `.github/workflows/*.yml` しか
走査しておらず，`.yaml` で足された workflow を見落とす形だった．
GitHub は双方を workflow として認識する．

テストが守ろうとしていたのは「二重起動しない」であって
「`.yml` の範囲で二重起動しない」ではない．
走査が片方の拡張子しか見ていない時点で，条件の保証になっていなかった．

対処では，走査の穴そのものを検査するテストも足した．
ディレクトリを差し替えられるようにし，実在の `.github/workflows/` の中身に
依存せず穴を検査できる形とした．
修正後は，`issue_comment` で発火する `.yaml` を一時的に置くとテストが落ち，
撤去すると通ることを実測している．

同じ穴が `tests/python/test_action_pins.py` の `_SEARCH_GLOBS` にも残っている．

### 中央自身の導線が無いと，レビューの依頼先が壊れる

本 PR 自身では `@claude` を起動できなかった．
workflow は default ブランチの定義で動くためである．
受け入れ条件「`@claude` で run が 1 件起動する」は，マージ後の別 PR でしか
確認できない．導線を新設する変更に共通する制約であり，
検証をマージ後へ持ち越す前提で計画する必要がある．

## 参照

- Issue [#140](https://github.com/tomio2480/github-workflows/issues/140)
- PR [#193](https://github.com/tomio2480/github-workflows/pull/193)
- [events-that-trigger-workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [docs/architecture.md](../architecture.md) の composite action と reusable workflow の節
