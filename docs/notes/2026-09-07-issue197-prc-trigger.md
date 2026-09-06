# 🔀 `pull_request_review_comment` は PR 側の定義で発火する（Issue #197）

## 🎯 要約

公式ドキュメントは，コメントで発火する 2 つの event へ同じ制約を課す．
`issue_comment` と `pull_request_review_comment` の双方である．
制約は「default ブランチに workflow ファイルが存在する場合のみ発火する」である．
PR #193 の観測はこれと食い違っていた．使い捨ての PR で実験し，
**`pull_request_review_comment` が PR 側の定義で発火することを再現した．**

ただし**確定できたのは観測であって，仕様ではない．**
測ったのは 2026-09-07 時点，同一リポジトリの branch での挙動である．
意図した契約なのか不具合なのかまでは判別できない．
文書どおりへ修正されれば，これに依存した手順は破綻する．
本稿は実験の組み方と，交絡を潰す過程，そして限定の付け方を残す．

## 🗺 目次

- 何が食い違っていたか
- 実験の設計
- 観測結果
- 交絡を潰す
- 実験が既存のガードを踏んだ
- 配布物とドキュメントへの反映
- 確かめていないこと
- 参照

## 🔍 何が食い違っていたか

PR #193 で self-caller を追加したときに観測した．
当該ファイルが `main` に入る前の時間帯である．
そこへ `pull_request_review_comment` 由来の run が 2 件作られた．
`issue_comment` 側は仕様どおりで，マージ後の PR #194 で初めて発火した．

観測は 1 度きりであり，別の説明も立てられた．
workflow entity の登録時点の扱いや，`refs/pull/N/merge` の解決結果である．
断定を避け，配布物からは断定的な記述を外したうえで Issue #197 へ送った．

**この時点で「レビューコメントなら caller 追加 PR 自身で確認できる」と
結論しなかったのは正しかった．** 根拠が観測 1 件しか無かったためである．

## 🧪 実験の設計

使い捨ての branch へ probe workflow を 1 本置き，PR を作った．
設計上の要点は 4 つである．

- **`if:` と `types` のどちらも置かない．** 発火の有無そのものを見るためである．
- **checkout せず，third-party action も使わない．**
  pin の検査に掛からず，実験が既存の規律と衝突しない．
- **`GITHUB_WORKFLOW_REF` を出力する．**
  どの ref の定義で動いたかがこれ 1 つで判る．発火の有無より強い証拠になる．
- **同じ probe へ `issue_comment` も並べる．**
  ドキュメントは両者へ同じ制約を課している．同一 PR・同一 branch・同一ファイルで
  両方を叩けば，制約が本当に同じかを条件をそろえて比べられる．

`main` に当該ファイルが無いことは，push 前に REST contents API で確認した．
404 が返ることをもって「存在しない」とした．

## 📊 観測結果

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. probe workflow の発火（同一 PR・同一 branch）

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| event | 投稿回数 | probe の run | 判定 |
|---|---|---|---|
| `pull_request_review_comment` | 2 | 2 件（いずれも success） | 発火する |
| `issue_comment` | 2 | 0 件 | 発火しない |

決め手は `GITHUB_WORKFLOW_REF` である．

```text
GITHUB_WORKFLOW_REF=tomio2480/github-workflows/.github/workflows/issue197-prc-probe.yml@refs/pull/201/merge
GITHUB_REF=refs/pull/201/merge
```

定義の出所が `refs/pull/201/merge` と明示された．
`main` に存在しないファイルが，PR 側の定義として実行されている．
発火の有無だけを見ていたら「なぜか動いた」で終わっていた．

`issue_comment` を投稿した時刻には `Claude Review (self)` が発火している．
こちらの `headBranch` は `main` であり，default ブランチ側の定義で動いた．
同じ PR の同じ瞬間に，2 つの経路が別々の定義を引いていることになる．

## ⏱ 交絡を潰す

対照実験の 1 回目は，`issue_comment` を足した push から 14 秒後に投稿した．
**この時間差では「登録が間に合わなかっただけ」と説明できてしまう．**

`pull_request_review_comment` 側は push から約 56 秒後の投稿だった．
条件がそろっていない以上，0 件を「発火しない」と読んではならない．
約 93 秒後にもう 1 度叩き，結果が変わらないことを確かめた．

実験で要るのは，差が出たことより，その理由を 1 つに絞れることである．
差が出た直後は結論を書きたくなる．そこで交絡を数え上げる方が早い．

## 🚪 実験が既存のガードを踏んだ

probe を `.github/workflows/` へ置いた時点で，二重起動検査が落ちた．
検査は `tests/python/test_claude_review_self.py` にある．
コメントで発火する中央 workflow が 2 本になったためである．

**これは PR #193 で入れたガードが意図どおり働いた証拠である．**
実験に伴う想定内の失敗として扱い，修正せずに PR 本文へ理由を書いた．

副次的に判ったこともある．中央リポジトリで comment 発火の workflow を
一時的にでも増やすと，このガードが必ず落ちる．
実験のために CI を緑にしようとして検査を緩めると，本来の守りが消える．

## 📌 配布物とドキュメントへの反映

イベント別に書き分ける形へ改めた．両者を同じ制約でまとめると誤りになる．

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2. コメント発火イベントの制約

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| event | default ブランチ限定 | 同一 repo の branch PR 自身で確認できるか |
|---|---|---|
| `issue_comment` | 課される | できない |
| `pull_request_review_comment` | 課されない（観測） | **できる** |

同一リポジトリの branch から作った PR なら，
オンボーディングの「動作確認はマージ後の別 PR で行う」は緩められる．
caller を追加した PR の diff 行へ `@claude` を含むレビューコメントを
投稿すれば，その場で run と応答を見られる．

`issue_comment`（PR の会話タブ）は従来どおりである．
利用者へ案内する導線が 2 通りに分かれる点は残る．

### 脅威モデルの前提が 1 つ崩れた

`docs/security.md` の 12 番は，対策の根拠を 1 つ誤っていた．
「checkout は ref 未指定（default ブランチのみ）で，PR head は取得しない」である．
**この記述は `pull_request_review_comment` について成り立たない．**

reusable workflow の checkout は `ref:` を指定しないため `GITHUB_SHA` を取る．
本イベントの `GITHUB_SHA` は PR の merge commit である．
実測では `9ff1c71e` であり，当時の `main`（`20e660c`）ではなかった．

PR 側の定義で動くことには，もう 1 つの帰結がある．
**PR ブランチへ push できる者は workflow 自身を書き換えられる．**
`claude-code-action` の権限検査も，書き換えれば外せる．
同一 repo の write collaborator は信頼境界の内側に置く．

fork PR では repository secret が渡らず `GITHUB_TOKEN` も read-only へ降格するため，
この経路は成立しない．表 3 のとおり，逆に確認手順としても使えない．

## 🚧 確かめていないこと

実験の射程を明示する．**ここを書かないと，読み手は測っていない範囲まで
結論が及ぶと読む．**

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 3. 測った範囲と測っていない範囲

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 条件 | 測ったか | 備考 |
|---|---|---|
| 同一 repo の branch PR | 測った | 発火する．2 回とも success |
| fork からの PR | **測っていない** | 発火の有無自体が未確認 |
| 最小 probe（`if:` も `types` も無し） | 測った | これで発火した |
| 実際の caller（`types: [created]` と reusable 側の `if:`） | **測っていない** | 構成が違う |

fork については，仮に発火しても確認手順としては使えない．
公式ドキュメントが次を明記している．

> With the exception of `GITHUB_TOKEN`, secrets are not passed to the runner
> when a workflow is triggered from a forked repository.

`CLAUDE_CODE_OAUTH_TOKEN` が渡らず，`GITHUB_TOKEN` も read-only になる．
run が作られたとしても Claude の応答までは到達しない．

実際の caller 構成での確認は，次に caller を追加する PR で行える．
そこで初めて `types: [created]` と reusable 側の `if:` を通した経路が測れる．

## 📚 参照

- Issue [#197](https://github.com/tomio2480/github-workflows/issues/197)
- 実験用 PR [#201](https://github.com/tomio2480/github-workflows/pull/201)（マージせず破棄）
- Issue [#140](https://github.com/tomio2480/github-workflows/issues/140)，PR [#193](https://github.com/tomio2480/github-workflows/pull/193)
- [2026-09-05-issue140-self-caller.md](2026-09-05-issue140-self-caller.md) の未解決節
- [events-that-trigger-workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
