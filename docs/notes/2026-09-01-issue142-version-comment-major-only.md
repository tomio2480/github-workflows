# 版コメントを major 限定へ切り替えた判断

## 背景

`templates/` の caller サンプルは `uses: ...@<SHA> # v2.13.3` の形で
patch 番号つきの版コメントを持っていた．
一方で運用は「PR マージごとに patch タグを切る」を種別を問わず適用していた．

この 2 つは同時に満たせない．
`templates/` を触らないリリースが 1 回起きるたび，
版コメントは必ず 1 世代ずれる．
解消には `templates/` を触る PR が要り，その PR がまた新しいタグを生む．

ドリフトは過去 4 回再発した（v2.6.3 前後・v2.6.9・v2.12.1・v2.13.2）．
再発のたびに「点検を欠かさない」と記録してきたが止まらなかった．

## 判断

### 規律で守れない一致要求は，要求そのものを外す

Issue #142 で 3 案を比較し，案 A（版コメントを major のみにする）を採った．
`# v2.13.3` を `# v2` へ改めることで，ずれる余地を構造から取り除いた．

決め手は 2 点である．
第一に，ドリフトは運用の不徹底ではなく要求の設計に由来していた．
検知を機械化する案（Issue #131）でも解消 PR は依然として要り，
往復の回数は減らない．
第二に，`templates/.github/workflows/md-lint.yml` のヘッダー説明である．
そこは既定を「`@<SHA> # v2` 形式」と書いており，本文だけが食い違っていた．
`docs/architecture.md` や `docs/setup-guide.md` も同じく `# v2` で説明していた．
patch 番号を書いていたのは実ファイル 3 件のみで，むしろそちらが外れ値だった．

### 失う情報は代替経路で引ける

patch 番号を落とすと「pin した SHA がどの版か」をコメントから読めなくなる．
これは `git tag --points-at` で引けるため，情報そのものは失われない．
テンプレート内へその旨を注記し，将来の保守者が patch 番号へ戻さないようにした．

### caller 側のコメントは中央の保守対象ではない

caller が `# v2` を持つ状態で Dependabot が SHA を更新したとき，
コメントを解決先の版へ書き戻す可能性がある．
これは caller 自身のファイルであり，中央が同期義務を負う対象ではない．
案 A が消したのは「中央が配布物を毎リリース手直しする」義務である．

## 影響

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 本変更で更新した箇所

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 対象 | 変更内容 |
|---|---|
| `templates/` の caller 3 件 | `# v2.13.3` を `# v2` へ変更 |
| `templates/.../md-lint.yml` ヘッダー | major 限定とする理由を注記 |
| `README.md`・`docs/onboarding-new-repo.md` | 版コメントの手動補正指示を削除 |
| `CLAUDE.md` | 版コメントは major 限定と明記 |
| `docs/development-notes.md` | 旧チェックリスト節を撤回済みと明示 |
| `README.md`・`docs/architecture.md` ほか 2 件 | 既定として示していた patch 形式の例を `# v2` へ統一 |

既定の例を patch 形式のまま残した箇所が 4 件あり，Codex レビューで指摘を受けた．
移行では「実ファイルの書き換え」と「説明文中の例の書き換え」を分けて洗い出す必要がある．
前者だけを直すと，説明が旧形式を既定として示し続け，patch 形式へ戻す動機を残す．

Issue #131（ドリフトの CI 検知）は本変更で条件が単純になる．
「`templates/` 内の版コメントが `# v2` 以外なら fail」で足りる．
最新タグとの突合は不要となる．

## 参照

- Issue #142（本判断の起票）
- Issue #131（ドリフトの機械検知．本変更で検知条件が確定した）
- PR #141（v2.13.3 への同期．最後の対症対応）
- [2026-08-09-tag-drift-and-version-comment-lessons.md](2026-08-09-tag-drift-and-version-comment-lessons.md)
