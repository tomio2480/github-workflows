# 📓 Issue #148: lint レポートの artifact 配布で得た知見

## 要約

lint summary が案内していた「内訳は Actions ログから確認してください」は，実在しない参照経路だった．個別の指摘は reviewdog へ渡るだけで，ログには rule ID とファイル名のどちらも残らない．対策として生レポートを run の artifact で配布し（v2.14.0），案内文を実態へ合わせた．本ノートは，このとき得た 3 つの知見を残す．案内する経路は実在を確認すること，`always()` の step は前段の skip 前提を壊すこと，caller の報告は中央の盲点を突くことである．

## 目次

- 📌 背景
- 🔍 知見 1: 案内した参照経路の実在を確認する
- ⚠️ 知見 2: `always()` の step は前段の skip 前提を壊す
- 📣 知見 3: caller からの報告は中央の盲点を突く
- 🧭 設計判断の記録
- 🔗 参照

## 📌 背景

Issue #148 は caller から届いた報告である．summary はリポジトリ全体の件数を出すが，その内訳を取得する手段が無いという内容だった．報告者は `gh run view --log` を実際に取得していた．rule ID を含む行・ファイル名を含む行がいずれも 0 件であることを確認したうえでの起票である．

回避策としてローカル再現も試みられていた．しかし棚卸しのたび，中央設定と固定版ツールの組み立て直しが要る．さらに再現の忠実性も保証されない．実際に `markdownlint` の総数は summary と一致した一方，textlint は一致しなかったという報告があった．

## 🔍 知見 1: 案内した参照経路の実在を確認する

誤った案内文は PR #28（v2.3.0 相当）で入った．当時の設計判断は `docs/development-notes.md` の「集計件数と表示件数のギャップは UI 側で吸収する」節に残っている．そこには「漏れた分の参照経路を本文に組み込む」という規律が書かれている．規律そのものは正しい．

問題は，組み込んだ参照経路が実在するかを確認しなかった点にある．reviewdog は指摘を PR の inline コメントへ送るだけで，標準出力へ書き戻さない．「Actions ログを見れば何かある」という推測が，そのまま 5 ヶ月以上残った．

**UI に参照経路を書くときは，その経路を 1 度実際にたどる．** たどれない経路の案内は，無い案内より悪い．利用者は存在しない出力を探して時間を使う．

## ⚠️ 知見 2: `always()` の step は前段の skip 前提を壊す

Codex のレビューが 1 件の P2 を指摘した．内容は次のとおりである．

`fail-on-error: "true"` を渡した caller を考える．`markdownlint` 側の reviewdog は `-fail-on-error` により非ゼロ終了する．composite action の step は前段の失敗で skip される．後続の `Run textlint with reviewdog` は走らない．ところが今回追加した upload step は `always()` を持つ．結果として `markdownlint` のレポートだけを含む artifact が，両方入りとして案内される．

指摘は正しかった．`Run textlint with reviewdog` に `if:` は無い．検証は step の条件を 1 つずつ読んで行った．

**`always()` を足す step は，前段が skip される経路を必ず洗う．** `always()` は「前段が成功していなくても走る」という宣言である．前段の成果物が揃っている前提とは両立しない．成果物を扱う step ではとくに危うい．

対応は 2 案あった．採否は次のとおりである．

- 採用: 部分的なアップロードを結合レポートとして扱わない．実在するレポートを検出し，summary へはそのファイル名だけを渡す．欠けていれば `::warning::` を出す．どちらも無ければアップロードを見送る．
- 不採用: 両方の linter を必ず実行する．`fail-on-error: "true"` は「指摘が出たら止める」という caller の明示的な選択であり，その短絡を解除するのは挙動変更である．本 PR の範囲を超える．

## 📣 知見 3: caller からの報告は中央の盲点を突く

本リポジトリは Issue #109 で自身の lint 債務を段階的に解消した．そのときも内訳は必要だった．しかし中央リポジトリなら手元にレポートがあるため，不便を感じずに済んでいた．同じことを caller 側でやろうとして初めて，経路が無いことが露見した．

**中央リポジトリの dogfooding は，caller の体験を完全には代替しない．** 中央には配布物の中身が手元にあるという非対称がある．caller だけが踏む経路は，報告を待つか，caller の立場で 1 度なぞるかでしか見つからない．

## 🧭 設計判断の記録

Issue が挙げた 3 案のうち，案 2（artifact）と案 3（案内文の修正）を採った．案 1（summary へ全体の内訳を出す）は採らなかった．件数の多い caller では折りたたみが長大になり，PR コメントの本文上限にも近づくためである．

その他の判断は次のとおりである．

- 既定は `upload-reports: "true"` とした．opt-in にすると，内訳が無いことに気づいていない caller には届かない．誤案内の解消が目的であるため，既定で有効にする．
- artifact 名の既定は `lint-reports-<job id>` とした．`actions/upload-artifact` は同一 run 内の同名アップロードで失敗する．matrix で同一 job を並列展開する caller のために `report-artifact-name` を用意した．
- アップロードの失敗では job を落とさない．reviewdog 本体は既に投稿済みであり，summary 投稿と同じ fail-open の方針に揃えた．
- 追加権限は要らない．artifact のアップロードは runtime token を使うため，caller の `permissions` 宣言に変更は生じない．

## 🔗 参照

- [Issue #148](https://github.com/tomio2480/github-workflows/issues/148)・[PR #152](https://github.com/tomio2480/github-workflows/pull/152)（v2.14.0）
- [Issue #153](https://github.com/tomio2480/github-workflows/issues/153)（本作業中に発見した Dependabot の追跡漏れ）
- [docs/architecture.md](../architecture.md) の「lint summary コメントの投稿」節
- [docs/onboarding-existing-repo.md](../onboarding-existing-repo.md) の「既存指摘を棚卸し」節
