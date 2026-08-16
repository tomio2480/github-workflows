# caller 追加 prh 辞書 .prh-extra.yml の加算方式と衝突時の優先順位

## 要約

caller が中央 `prh.yml` を置き換えずに固有の表記ゆれ規則を足せる `.prh-extra.yml` を v2.7.0 で追加した．
`textlint-rule-prh` は `rulePaths` を配列で受けるため，中央と追加を並べるだけで実現できた．
同一パターンの衝突は先に並べた辞書が勝つことを実測し，中央を先頭に固定した．
追加辞書は「足す」専用であり，中央規則を弱めたい caller は `.textlint-allowlist.yml` か `prh.yml` 置き換えを使う．
自リポジトリでは読点「，」統一を `.prh-extra.yml` に置き，統合テストの fixture で効き目を確認する dogfooding にした．

## 目次

- 背景
- 判断
- 実測した挙動
- 代替案と棄却理由
- 波及先
- 参照

## 背景

`tomio2480/techbook-template#99` で読点 `、` を機械検出したい要望があった．
caller root の `prh.yml` は中央辞書を全置換する規約のため，1 規則を足すために約 23 規則を写す必要があった．
写した caller は中央辞書の更新から取り残される．
`.textlint-allowlist.yml`（v2.1）が加算方式で成功していたため，同じ形を辞書側にも用意した．

## 判断

- ファイル名は Issue 提案どおり `.prh-extra.yml` とした．`prh.yml` と並べたとき役割の違いが名前で分かる．
- 検出は `action.yml` の設定解決 step で `[ -f .prh-extra.yml ]` を inline 判定する．
  中央フォールバックを持たないため `resolve-config-path.sh` には流用しない（allowlist と同じ判断）．
- `generate-textlint-runtime.py` は optional の argv 5 つ目で受ける．空文字を「未設定」と解釈し，
  argv 3 つ・4 つの呼び出しは従来動作を厳密維持する．
- `rulePaths` の順序は `[中央, 追加]` に固定する．中央の既定が caller の追加で変質しないようにする．
- `prh.yml`（置き換え）と `.prh-extra.yml`（追加）を両方置いた場合は `[caller prh.yml, .prh-extra.yml]` とする．
  置き換え辞書を基点に追加辞書が加算される単純な規則にした．
- 追加辞書ファイルが指定されたのに存在しない場合は `ValueError` で fail-fast にする．
  action 側は存在するときだけパスを渡すため，通常経路では発生しない．

## 実測した挙動

`textlint-rule-prh` 6.1.0 で，同じパターン `Github` に別の `expected` を書いた 2 辞書を並べて実行した．
`rulePaths` の順序を入れ替えると `expected` も入れ替わったため，衝突は **先頭の辞書が勝つ** ．
prh は複数辞書を読み込み順にマージし，同一パターンは先に登録された規則を保持する．

表 1. 衝突時の実測結果

| `rulePaths` の順序 | `Github` への指摘 |
|---|---|
| `[central, extra]` | `Github => GitHub`（中央が勝つ） |
| `[extra, central]` | `Github => ギットハブ`（追加が勝つ） |

衝突しない規則（追加辞書の `、 => ，`）はどちらの順序でも検出された．
空辞書（`rules: []`）の追加は無害で，中央 6 件の検出数は変わらなかった．

## 代替案と棄却理由

- caller 側に独自の検査スクリプトを置く案．
  コードブロック・インラインコードの除外を自前で再実装することになる．
  prh は textlint の `Str` ノードだけを見るため，中央で加算方式を用意する方が全 caller に効く．
- prh の `imports` で中央辞書を取り込む案．
  中央辞書は action のチェックアウト先にあり，caller から相対パスで指せない．
- `[追加, 中央]` の順で caller に上書きを許す案．
  中央の既定が caller ごとに変質し，`docs/rule-rationale.md` の根拠が効かなくなる．
  上書きしたい caller には `prh.yml` 置き換えという既存手段がある．

## 波及先

- `tomio2480/techbook-template`: 読点「，」統一を `.prh-extra.yml` で導入できる．
  caller テンプレの版コメントを v2.7.0 へ進める際に併せて案内する．
- 本リポジトリ root の `.prh-extra.yml` は dogfooding 兼統合テスト入力である．
  中央辞書に入れない「このリポジトリだけの規約」を置く場所として維持する．

## 参照

- Issue #91・PR #93（v2.7.0）
- Issue #14（`.textlint-allowlist.yml` の加算方式，v2.1）
- `tomio2480/techbook-template#99`（発端）
- [docs/dictionary-maintenance.md](../dictionary-maintenance.md) 2️⃣・5️⃣ 節
- [docs/architecture.md](../architecture.md) 設定ファイルの解決順序
