# ローカル lint の条件と caller の宣言を結び付ける

## 要約

ローカルの lint 成功を CI の検証済みと扱わないため，実行条件の記録を追加した．
要求と対応範囲は [local-lint](../local-lint.md) に置く．

## 目次

- HEAD だけでは足りない
- 設定の選択を複製しない
- 宣言と実行を区別する
- 検証と残る範囲

## HEAD だけでは足りない

既存の保存記録は caller と中央の HEAD を持っていた．
ただし，同じ HEAD でも未コミットの設定変更があれば lint の結果は変わる．
また，ローカル中央 checkout の版と，caller が pin した版は一致するとは限らない．
README と local-lint にあった「違いは終了コードだけ」という説明を改めた．

## 設定の選択を複製しない

記録処理が設定を探し直すと，実行側とのずれが新たに生じる．
そこで，既存 resolver の結果を path の引数として渡す．
元設定と依存 manifest の hash を記録し，終了時にも同じ file を確認する．
設定本文は保存しない．runtime config と作業用の複製は，従来どおり終了時に回収する．

## 宣言と実行を区別する

GitHub は workflow の `.yml` と `.yaml` を認識し，action の `with` で input を渡す．
この構造を PyYAML で読む．行単位で uses を探さず，文字列の中身を呼び出しと誤認しない．
[GitHub の workflow 構文](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)

pin の既定値と設定は手元の Git object から読む．無ければ unknown とする．
現行 checkout の値で代用すると，古い pin との違いを隠すためである．
reusable workflow の呼び出しは job 単位であり，直接の action 呼び出しとは別に記録する．
その先の展開や条件式の評価は，今回の処理では行わない．
[GitHub の reusable workflow](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)

## 検証と残る範囲

対照には古い pin，同じ HEAD 上の設定変更，caller override，未取得 object，式を使った．
YAML の重複 key，壊れた document，block scalar 内の uses も区別する．
Bash から実行し，成功する lint の途中で設定だけを変更すると exit 2 になることを確認する．
変えない対照は exit 0 を保つ．

これは特定の項目の照合であり，CI の実行証明ではない．
custom rule 等の推移的な依存，必要 gate の期待集合，GitHub の実行条件は残る．
source の dirty と raw hash を残すことで，比較の限界も後から確かめられるようにした．
