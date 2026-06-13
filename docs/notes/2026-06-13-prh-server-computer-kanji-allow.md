# prh 否定先読みの横展開と max-kanji-continuous-len allow 公開（Issue #48・#49）

## 要約

Issue #33 で `ユーザー` に適用した否定先読みパターン `(?!ー)` を，
`サーバー` と `コンピューター` に横展開した（Issue #48）．
また `max-kanji-continuous-len` の `allow` オプションを中央テンプレに明示し，
固有名詞を per-repo で除外する経路を文書化した（Issue #49）．

## 目次

- Issue #48：サーバー・コンピューターへの否定先読み横展開
- Issue #49：max-kanji-continuous-len allow の公開
- Opus + Sonnet 協調レビューで気づいたこと

---

## Issue #48：サーバー・コンピューターへの否定先読み横展開

### 背景

`tomio2480/settings` PR #92 で `サーバー` の誤検出が発生した．
中央テンプレ `templates/prh.yml` が `サーバ`（plain string）でパターンを定義していたため，
正しい表記 `サーバー` 内の部分文字列 `サーバ` にも substring match した．
`コンピューター` も同じ構造の plain string パターンを持っており，
同根の誤検出リスクがあった．

### 判断

Issue #33 の `ユーザー` 対応（`/ユーザ(?!ー)/`）を先例として，
`サーバー` と `コンピューター` に同じ否定先読みを適用した．

```yaml
- expected: サーバー
  patterns:
    - /サーバ(?!ー)/
  specs:
    - from: サーバ環境
      to: サーバー環境
    - from: サーバー環境      # 境界例：変換されないことの自己テスト
      to: サーバー環境

- expected: コンピューター
  patterns:
    - /コンピュータ(?!ー)/
  specs:
    - from: コンピュータ科学
      to: コンピューター科学
    - from: コンピューター科学  # 境界例
      to: コンピューター科学
```

`specs` の `from === to` ペアは「正しい表記が変換されないこと」の
自己テストとして機能する（`ユーザー` の先例と同じ構成）．

### 残課題

`プリンター`・`フォルダー`・`ブラウザー`・`ルーター` など，
長音「ー」で終わる語が plain string で書かれていた場合，
同根の誤検出リスクがある．Opus のレビューで指摘を受けたが，
今回のスコープ外として Issue 化を保留している．

---

## Issue #49：max-kanji-continuous-len allow の公開

### 背景

`max-kanji-continuous-len`（漢字連続文字数制限，既定 `max: 6`）が
「電波法施行規則」や「情報処理推進機構」などの固有名詞で誤検出する事例が
caller リポジトリで報告されていた．
中央テンプレにはこのルールの `allow` オプションが定義されておらず，
per-repo で除外する経路が文書化されていなかった．

### 判断

`textlint-rule-max-kanji-continuous-len` の `allow` オプションは
`string[]`（デフォルト `[]`）で，特定の語を例外として登録できる．

中央テンプレ `templates/.textlintrc.json` に `"allow": []` を明示することで，
- 中央側の挙動はそのまま（空配列なので実質 no-op）
- caller が per-repo override で任意の固有名詞を追加できることを可視化

という設計にした．

```json
"max-kanji-continuous-len": {
  "max": 6,
  "allow": []
}
```

per-repo での追加例は `docs/rule-rationale.md` の
「max-kanji-continuous-len と固有名詞の例外」節に記載した．
caller-side の除外方針は
[docs/dictionary-maintenance.md](../dictionary-maintenance.md) の「5️⃣」節を参照する．

### Opus レビューで修正した点

初稿で `docs/onboarding-existing-repo.md` を参照先として記述したが，
同ファイルには `allow` オプションの記載がない．
Opus が「参照先が誤っている」と指摘し，
`dictionary-maintenance.md` の「5️⃣」節（`max-kanji-continuous-len` 除外の実例あり）
に変更して PR マージ前に修正した．

**教訓**：参照先はリンク先の実際の内容を確認してから書く．
「既存リポジトリへの導入手順」と「allowlist の運用指針」は別ドキュメントにある．

---

## Opus + Sonnet 協調レビューで気づいたこと

今回は「Opus と Sonnet が協力してセルフレビューし，問題なければマージ」という
運用を初めて実施した．

- **Opus 担当**：設計・アーキテクチャ視点（拡張性・漏れ・参照の正確性）
- **Sonnet 担当**：記法・80 字制限・目次整合・文末句点などの機械的チェック

Opus が「参照先が誤っている」という中程度の指摘を出したことで，
マージ前に修正できた．Sonnet のみでは記法レベルの問題しか検出できず，
意味的に誤った参照先を見落とす可能性があった．

**並列呼び出し**（`Agent` ツールを 2 回並列）は 1 ターンで両者の結果を得られる．
Opus の設計レビューと Sonnet のメカニカルチェックは依存関係がないため，
逐次ではなく並列で呼ぶと時間効率がよい．

---

## 参照

- [Issue #48](https://github.com/tomio2480/github-workflows/issues/48) — サーバー誤検出
- [Issue #49](https://github.com/tomio2480/github-workflows/issues/49) — 固有名詞誤検出
- [PR #51](https://github.com/tomio2480/github-workflows/pull/51) — Issue #48 の対応
- [PR #52](https://github.com/tomio2480/github-workflows/pull/52) — Issue #49 の対応
- [docs/notes/2026-05-03-prh-user-negative-lookahead.md](2026-05-03-prh-user-negative-lookahead.md) — Issue #33 の先例
- [docs/rule-rationale.md](../rule-rationale.md) — prh と max-kanji-continuous-len の根拠
- [docs/dictionary-maintenance.md](../dictionary-maintenance.md) — allowlist 運用指針
