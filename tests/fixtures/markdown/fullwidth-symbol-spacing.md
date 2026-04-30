# fullwidth-symbol-spacing fixture

Issue #15 で観測された「全角記号前後の半角スペース」パターン集．
preset-ja-spacing 既定では検出されず caller 側で手作業修正されている事象を fixture 化する．

対象シンボルは中黒 `・`，全角スラッシュ `／`，波ダッシュ `〜` の 3 種である．
全角コロン `：` は ja-no-space-between-full-width で既に検出されるため対象外とした．

stage 2 で中央 textlintrc にルールを追加する際の入力となる．

## 観測される NG パターン

CI ・ cron をハイブリッドに組み合わせる．
hatena ／ note の併用も検討する．
source ／ url ／ title の 3 列でデータを管理する．
取得期間は 2025-08-30 〜 2026-04-13 とする．

## 期待形

CI・cron をハイブリッドに組み合わせる．
hatena／note の併用も検討する．
source／url／title の 3 列でデータを管理する．
取得期間は 2025-08-30〜2026-04-13 とする．
