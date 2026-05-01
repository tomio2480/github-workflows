# SemVer 風 patch タグ運用への移行

## 背景

中央 composite action のリリース運用で `v1` `v2` の major mutable タグだけが存在していた．
patch tag を切る運用は未実行で，caller は `@main`（即時反映）か `@<SHA>`（固定）の二択しかなかった．
さらに `v2` mutable は PR #4 のマージ位置から動かされていなかった．
`@v2` pin 利用者は v2.1 の caller-side allowlist 以降の改善を受け取れない状態が続いていた．

利用者が細かいバージョンアップの恩恵を受けられるよう，SemVer 風の patch tag 運用へ移行する．

## 判断

PR マージごとに `vX.Y.Z` patch タグを切る運用とする．major mutable（`v2`）は同時に最新 patch へ進める．caller は次の 4 形態から pin を選択できる．

- `@main`：即時反映．即時性優先の利用者
- `@v2` major mutable：PR マージごとに最新 patch へ自動追従．caller の介入なし
- `@v2.2.0` patch immutable：固定．新 patch への切り替えは caller の明示操作
- `@<SHA> # v2.2.0`：SHA pin．Dependabot が patch tag 更新を検知して PR 起票

retroactive に v2.0.0 / v2.1.0 / v2.2.0 を切る．対応コミットは次のとおり．

- v2.0.0：`8382b97`（PR #4 — composite action 移行の初出）
- v2.1.0：`9d82865`（PR #17 — caller-side textlint allowlist 対応）
- v2.2.0：`39b56da`（PR #23 — Issue #15 stage 2 prh ルール）

`v2` mutable は v2.2.0 まで進める．

中間 patch（v2.0.x の細分化など）は切らない．判定が難しく，必要な caller は SHA pin で固定可能．

## 代替案と棄却理由

1. **patch tag を切らない（現状維持）**
   `@v2` mutable のみで運用する．caller の選択肢が二択（main か固定 SHA）になり，意図的な patch 追随が困難になる．SHA pin と Dependabot の組合せでは「patch だけ取りたい」「minor 以上は手動レビューしたい」のような細粒度制御ができない．現状の不便を放置するため棄却した．

2. **過去の commit 全てに patch tag を割り当てる**
   v2.0.1 / v2.0.2 / ... のように細かく区切る．判定が判断依存で運用負荷が高い．fix と内部リファクタの境界判定が難しい．caller への利益も限定的．代表的な節目（PR #17 = v2.1.0）のみで足りるため棄却した．

3. **`v1` 系も patch tag を切る**
   `v1` は self-detection bug で動作しないため使われていない．patch tag を打つ意味が無く棄却した．

## 参照

- [docs/dictionary-maintenance.md](../dictionary-maintenance.md) — 表 2／表 3 の参照方式・変更種別マトリクス
- [CLAUDE.md](../../CLAUDE.md) — タグ運用規律（PR マージごとの patch リリース・major mutable 追従）
- [docs/setup-guide.md](../setup-guide.md) — リリース時のコマンド例
- [docs/fork-usage.md](../fork-usage.md) — フォーク利用者向けの patch リリース手順
- [SemVer 2.0.0](https://semver.org/lang/ja/) — バージョン番号の意味づけ
