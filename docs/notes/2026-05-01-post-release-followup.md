# v2.2.2 リリース後のフォローアップ運用と判断記録

## 背景

v2.0.0 から v2.2.2 までのタグ発行と GitHub Release 作成を完了した．
完了後に残課題のクロージングとして次の 3 領域に対応した．
本ノートは個別の対応そのものではなく，運用判断のパターンとして再利用可能な知見を残す．

- Issue #15（全角記号スペース禁止ルール）の上流提案を控える判断
- 別リポジトリの meta Issue（[tomio2480/settings#11](https://github.com/tomio2480/settings/issues/11) と [#12](https://github.com/tomio2480/settings/issues/12)）への観測材料コメント
- caller リポジトリ全体の v2.2.2 追従状況の確認

## 判断 1：意見が割れる領域は中央リポジトリで差分を持つ

[Issue #15](https://github.com/tomio2480/github-workflows/issues/15) は短期対策を本リポジトリの prh 拡張で完了した．
上流（textlint-ja/textlint-rule-preset-ja-spacing）への新規ルール提案は **当面実施しない方針** に確定した．

判断軸は次のとおり．

- **意見が割れる領域である**：JTF スタイル（禁止）と他の組版習慣（容認）で立場が異なる．既存ルール設計も中間解と読める
- **上流の merge 議論にエネルギーを取られない**：punctuation 周りは breaking change ラベルが付きやすい．コアメンテナ議論を要する性質
- **中央リポジトリで差分を持つ運用が成立している**：caller は `@v2.2.0` 以降で恩恵を受けられる．例外吸収も `.textlint-allowlist.yml` で個別対応可能

汎用化すると次のヒューリスティックになる．

> **上流提案より自律運用を優先する条件**
> 1. 観点に**専門家のあいだで意見の対立** がある（規範/慣習/組版方針 等）
> 2. 中央リポジトリで**自律的に差分を保持・運用** できている
> 3. caller 側に**個別の例外吸収手段** が用意されている

3 つを満たすときは上流に Issue を立てない選択が現実的になる．

## 判断 2：close せず open のまま「経緯保管庫」 として残す Issue

Issue #15 は open のまま残す方針を取った．
caller 開発者が「このルールはどこから来たのか」と調査する際の参照経路を確保する目的である．

### 経緯保管庫の Issue に書くべき要素

1. **直近の判断結果**：何を決めたか，なぜ決めたか
2. **上流の状況サマリ**：本日時点の調査結果．後日読み返したとき比較材料になる
3. **caller 開発者向けの参照経路**：lint メッセージから本 Issue への到達ルート．ルール本体・採用根拠・判断ログ・例外吸収方法へのリンク
4. **再見直しトリガ**：どんな観測が出たら本 Issue で再議論するか

経緯保管庫の Issue は **close せずに open のまま放置することが機能** する．
GitHub の検索・通知・参照のしやすさを使うために close は不利である．

## 判断 3：別リポジトリの meta Issue への「観測材料コメント」 という対応形態

[tomio2480/settings#11](https://github.com/tomio2480/settings/issues/11) と [#12](https://github.com/tomio2480/settings/issues/12) は本リポジトリのスコープ外である．
具体的には Skill・CLAUDE.md・agent prompt の改修対象になる．
直近の PR #23・#25・#26 で実観測した繰り返し指摘パターンは，これらの Issue にとって裏付けデータとして価値が高い．

### 取り組み方の 3 形態

| 形態 | 内容 | 適する状況 |
|---|---|---|
| 直接実装 | 別リポジトリへ切り替えて改修 PR を起票 | 該当リポジトリの全体把握が済んでいる場合 |
| 観測材料コメント | 直近観測の事例を Issue にコメントで蓄積 | 別リポジトリの全体把握が未済，かつ近時情報の鮮度が高い場合 |
| 何もしない | 既存 Issue の内容で十分 | 暫定リストが既に網羅的な場合 |

PR #23・#25・#26 の対応が直近であり，鮮度の高い観測データが揃っていた状況では「観測材料コメント」が最適だった．
コメントの書き方として次の構造が有効である．

- 本 Issue の暫定リストに対する**観点別の紐付け**
- 既出 anti-pattern の**再観測** と新規追加候補の提示
- 進め方への**補足提案**．暫定リスト精査時の判断材料として残す

実改修は別セッションで該当リポジトリのコンテキストを揃えてから着手する形が筋になる．

## 判断 4：並行セッションを前提とした caller 追従確認

caller リポジトリの追従確認は単に SHA を読むだけではなく，**並行セッションによる更新が走っている可能性** を含めて状況把握する必要がある．

### 観察された並行セッションの痕跡

caller 追従確認のため blog 系 2 リポジトリの workflow ファイルを覗いた．
本セッションでの v2.2.2 タグ発行から数時間後，両 caller で取り込み PR がマージ済みになっていた．
コミットメッセージには Claude Opus 4.7 の Co-Author 署名が付いていた．
**自分の知らない別セッションで並行作業が進んでいた** ことが分かった．

### caller 追従確認の標準手順

```bash
# 1. caller リポジトリを全網羅で発見
gh search code "tomio2480/github-workflows" --owner tomio2480 --extension yml \
  --json repository,path

# 2. 各 caller の workflow 参照と Dependabot 設定を確認
for repo in <caller_list>; do
  gh api "repos/tomio2480/${repo}/contents/.github/workflows/md-lint.yml" \
    --jq '.content' | base64 -d | grep "uses:.*github-workflows"
  gh api "repos/tomio2480/${repo}/contents/.github/dependabot.yml" \
    --jq '.content' | base64 -d 2>/dev/null
done

# 3. 並行セッションの可能性を踏まえて最近の commit と open PR を確認
for repo in <caller_list>; do
  gh api "repos/tomio2480/${repo}/commits?path=.github/workflows/md-lint.yml&per_page=3"
  gh pr list --repo "tomio2480/${repo}" --search "author:app/dependabot github-workflows"
done
```

### 観察された 4 リポジトリの追従パターン

| Caller | dependabot.yml | 追従経路 |
|---|---|---|
| blog-private | あり | 並行セッションで v2.2.2 取り込み済み |
| blog-pipeline | あり | 並行セッションで v2.2.2 取り込み済み |
| settings | **なし** | 手動で SHA だけ最新化．`# v2` コメント |
| picoruby-tea5767 | あり（grouped） | v2.2.1 で停止．次回 Dependabot schedule で追従予定 |

settings に dependabot.yml が無い点は別途検討候補として記録する（現状で実害はない）．

## 代替案と棄却理由

1. **Issue #15 を close する**
   close すると検索・通知・新規コメントの発見性が落ちる．
   経緯保管庫として機能させるには open が望ましい．
   caller 開発者が lint メッセージから本 Issue に到達する流れを保つ目的でも棄却した．

2. **settings 改修を本セッションで実施する**
   別リポジトリのコンテキストを揃えるオーバーヘッドが大きい．
   具体的には Skill・agent prompt の構造把握が必要になる．
   現セッションは `github-workflows` 中心で進めてきた経緯があり，スコープを跨ぐと判断品質が落ちる懸念もある．
   観測材料コメントで知見だけ Issue に蓄積し，実改修は別セッションに譲る形で棄却した．

3. **caller 全リポジトリに proactive PR を立てる**
   並行セッションが既に動いていることも判明し，重複作業のリスクは高い．
   Dependabot に任せて schedule で自然に追従させる形を維持し，必要な箇所だけ介入する方針に棄却した．

## 参照

- [docs/notes/2026-05-01-semver-release-operations.md](2026-05-01-semver-release-operations.md) — SemVer 運用への移行判断
- [docs/notes/2026-05-01-retroactive-tag-rollout.md](2026-05-01-retroactive-tag-rollout.md) — タグ発行の実行手順
- [docs/notes/2026-04-30-fullwidth-symbol-prh-rule.md](2026-04-30-fullwidth-symbol-prh-rule.md) — 全角記号スペース禁止ルールの判断
- [Issue #15](https://github.com/tomio2480/github-workflows/issues/15) — 経緯保管庫として open
- [tomio2480/settings#11](https://github.com/tomio2480/settings/issues/11) / [#12](https://github.com/tomio2480/settings/issues/12) — 観測材料コメントを蓄積
