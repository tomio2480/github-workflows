# PR checks の監視と実行記録

## 要約

`bin/watch-pr-checks.{sh,ps1}` は，対象 commit へ GitHub CLI の情報が追いつくまで待つ．
続いて，観測した checks の件数が一定になるまで待つ．
通常は従来の進捗を表示する．`summary` または `json` を指定すると，
全照会の応答を保存し，終了時に小さな結果を返す．

## 使い方

```bash
bash bin/watch-pr-checks.sh 165 --format summary
bash bin/watch-pr-checks.sh 165 --format json --limit 5 --output-dir /tmp/check-records
```

```powershell
pwsh -File bin/watch-pr-checks.ps1 -Pr 165 -Format summary
pwsh -File bin/watch-pr-checks.ps1 -Pr 165 -Format json -Limit 5 -OutputDir C:\Temp\check-records
```

記録モードは Python 3.9 以降の標準ライブラリを使う．
追加 package は不要である．`scripts/watch-checks-record.py` を隣接して配置する．
記録しない既定の呼び出しには Python を要求しない．

表 1 に追加 option を示す．監視の時間と SHA の option は従来どおりである．

| Bash / PowerShell | 既定値 | 意味 |
| --- | --- | --- |
| `--format` / `-Format` | `full` | `full`・`summary`・`json` |
| `--limit` / `-Limit` | `20` | 表示する check の上限．`0` なら件数と参照のみ |
| `--output-dir` / `-OutputDir` | OS の一時フォルダ | 記録先の親フォルダ |

`full` は保存先を指定したときだけ記録する．
保存先の配下へ実行ごとに一意なフォルダを作り，過去の結果を上書きしない．
`summary` と `json` の stdout には途中経過や長い診断を混ぜない．
入力の誤り，依存不足，記録先を作れない場合は stderr と exit 1 を返す．
この段階では `report.json` を作れない場合がある．

## 保存内容

表 2 に保存するファイルを示す．

| ファイル | 内容 |
| --- | --- |
| `context.json` | 作業ディレクトリ・開始時刻・待機条件・`GH_REPO` の指定 |
| `queries/*.json` | 各 gh 呼び出しの argv・時刻・終了コード・応答ファイル名 |
| `queries/*.stdout` | gh の stdout 全体．checks は名前・状態・bucket・link の JSON |
| `queries/*.stderr` | gh の stderr 全体 |
| `full.txt` | 監視処理の進捗と結果 |
| `diagnostics.log` | 照会と監視処理の診断 |
| `checks.json` | 最終照会を正常に解釈できた場合の checks 全件 |
| `summary.txt` / `report.json` | 要約と機械処理用の結果 |

要約の生成では GitHub へ再照会しない．
gh の照会回数と監視順序も，既定の呼び出しから増やさない．
保存するのは取得した項目の全体であり，Actions の実行ログや artifact は含まない．
`full.txt` だけでは各応答を確認できないため，詳細は `queries/` を読む．
記録は自動削除しない．不要になった実行フォルダは利用者が削除する．

## 結果の契約

`report.json` は `schema_version: 1`，`tool: watch-pr-checks` とする．
表 3 に状態と終了コードの対応を示す．

| exit | status | 意味 |
| --- | --- | --- |
| `0` | `ok` | 観測した checks に fail・cancel がない |
| `0` | `not_applicable` | 観測した checks がすべて skip |
| `1` | `error` | 入力・環境・記録処理のエラー |
| `2` | `partial` | 待機の締切，head の変化，終了時の head 取得失敗 |
| `3` | `findings` | 観測した checks に fail・cancel がある |

`reason` は正常に据え置けた場合に `settled`，検査失敗で `checks_failed` となる．
待機期限は `timeout`，head の変化は `head_changed` とする．
終了時の head 取得失敗は `head_unavailable`，その他のエラーは `error` である．
`expected_sha` と `observed_sha` に対象と観測値を記録する．
`counts` では pass・fail・pending・skipping・cancel を分ける．
取得できなかった件数は `null` とし，0 件へ読み替えない．

`coverage.scope` は `observed_checks` である．
`observation_complete` は監視の完了と終了時の head 一致を表す．
必要な check の集合は照合しないため，`expected_checks_complete` は常に `null` とする．
0 件の応答は完了条件を満たさず，締切まで待つ．
壊れた JSON と未知の bucket も記録モードでは完了と判定しない．

`checks` には表示上限までの要約を載せる．pass 以外を先に並べる．
名前などの文字列は空白をまとめて最大 160 文字と省略記号に絞り，
省略を `truncated` で示す．原文は応答ファイルと `checks.json` に残す．
`display` へ表示件数・省略件数・上限を記録する．
JSON 全体に長い診断本文は埋め込まず，`artifacts` から参照する．

## 監視の保証範囲

対象 SHA の解決，head の追随待ち，件数が一定になるまでの待機，
終了時の head 再照合は，Bash と PowerShell の既存処理が担う．
Python は応答の保存・状態の抽出・表示を担当し，別の監視ループを持たない．

`--settle` の既定は 120 秒である．その後に登録される check は観測できない．
前後の head 確認は，個々の run の SHA を検証することとも異なる．
required checks の集合との突き合わせと，各 run の SHA 照合は後続の設計対象である．
また，締切は polling の間で確認する．固まった外部 process を強制終了する契約ではない．

gh は pending を exit 8 で返し，失敗した check があっても応答を出す．
そのため終了コードだけで照会失敗と決めず，応答の bucket で判断する．
値と JSON 項目の根拠は [GitHub CLI の公式文書](https://cli.github.com/manual/gh_pr_checks) にある．
監視の設計経緯は [Issue #133 の記録](notes/2026-09-03-issue133-watch-pr-checks.md) を参照する．
