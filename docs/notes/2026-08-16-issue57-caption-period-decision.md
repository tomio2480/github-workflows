# キャプション句点廃止の決定（Issue #57 再訪）

## 背景

[前回のノート](2026-07-09-mixed-period-caption-conflict.md) は，
見直しトリガの 1 つとして次を挙げていた．

> 本リポジトリの中央設定を採用する caller が，句点なしの体言止め
> キャプションを規約として持ち込みたいと要望したとき．

今回，リポジトリオーナー自身がこのトリガを引いた．
グローバル規律（`~/.claude/CLAUDE.md`）の
『文末は「．」で統一する．箇条書き・キャプションも同様．』を改め，
図表キャプションは体言止め（句点なし）とする方針に変更した．
箇条書きの句点有無は文脈依存とし，一律のルールを定めないこととした．

## 再調査した内容

前回のノートで「案 A（ルールオプション）」は未調査のまま
「先回り対応は過剰設計」として保留していた．
今回はオプションを実際に確認した．

`textlint-rule-ja-no-mixed-period` が受け付けるオプションは次の 5 つである．

- `periodMark`：文末に使う句点文字
- `allowPeriodMarks`：句点として許可する文字列の配列
- `allowEmojiAtEnd`：絵文字での終端を許可するか
- `forceAppendPeriod`：`--fix` 時に句点を強制付与するか
- `checkFootnote`：脚注をチェックするか

リスト項目・表・見出し・キャプションなど，ノード種別を対象外にする
オプションは存在しない．
案 A は実現不可能であることが確定した．
案 B（AST ノード種別ベースの `overrides`）が textlint の機構上
実現不可能である点は，前回ノートの調査ですでに確定済みである．

## 決定

- 図表キャプションの句点省略は，**執筆規約（CLAUDE.md）の変更としてのみ**
  対応する．
- 中央 textlint 設定（`templates/.textlintrc.json`）は変更しない．
  `ja-no-mixed-period` はキャプションと本文の地の文を構造的に
  区別できないため，中央側での自動免除は技術的に不可能である．
- 今後，本リポジトリ自身の Markdown でも図表キャプションに句点を
  付けない．これにより，本リポジトリの lint が将来キャプション文を
  誤検出する可能性がある．
  発生した場合は caller 側の対応と同様，個別に許容する．
- 案 C（caller 側 `.textlintrc.json` でのファイル単位無効化）は，
  強い手段である．ファイル全体で `ja-no-mixed-period` を無効化する．
  本文の地の文の句点チェックも道連れで失われるため，
  既定では推奨しない．必要な caller は個別に判断する．

## 見直しトリガ（更新）

以下が観測された場合，Issue #57 を再度開いて判断する．

- 上流 `textlint-rule-ja-no-mixed-period` に
  ノード種別除外オプションが追加されたとき．
- 本リポジトリ自身の docs で `ja-no-mixed-period` の誤検出が
  実際に CI へ現れ，対応コストが無視できなくなったとき．

## 参照

- [Issue #57](https://github.com/tomio2480/github-workflows/issues/57)
- [2026-07-09-mixed-period-caption-conflict.md](2026-07-09-mixed-period-caption-conflict.md)
- [textlint-rule-ja-no-mixed-period](https://github.com/textlint-ja/textlint-rule-ja-no-mixed-period)
