# 🔗 Claude セッション URL 検査 composite action

## 🎯 要約

PR のタイトル・本文・コミットメッセージに Claude Code のセッション URL が
残っていないかを検査する．見つかれば job を失敗させる blocking gate である．
発生源の抑止は Claude Code 側の設定 `attribution.sessionUrl=false` が担う．
本 action は設定漏れや別経路の混入を PR の段階で受け止める最後の防衛線である．

## 🗺 目次

- 🧭 背景
- 🔍 検出するもの
- 🚀 導入
- 📜 contract
- 🧱 限界
- 🧹 見つかったときの対処

## 🧭 背景

Claude Code は cloud と Remote Control のセッションで作る commit と PR に，
既定でセッション URL を付ける．commit では `Claude-Session` trailer になる．
設定リファレンスの `attribution.sessionUrl` は既定 `true` である．
公開リポジトリの履歴へ残った URL は，GitHub の commit 検索で横断的に集められる．
履歴の書き換えは fork・cache・PR 参照に残り，完全な除去には GitHub Support が要る．
このため，履歴へ入る前の PR で止める．

## 🔍 検出するもの

大文字小文字を区別せず，次のいずれかを含む行を検出する．

- `claude.ai/code/session_…` または `claude.ai/code/cse_…`（素の URL 形式）
- `Claude-Session:`（git trailer 形式）

セッション ID を伴わない `claude.ai/code` は検出しない．
対象は PR のタイトル・本文と，PR に含まれる全コミットのメッセージである．

## 🚀 導入

`templates/.github/workflows/session-url-check.yml` を caller repo へコピーする．
`OWNER` は利用する中央 repo の owner に置換する．
`<SHA>` は確定 commit SHA に置換する．

```bash
OWNER=tomio2480
SHA=$(gh api "repos/${OWNER}/github-workflows/git/refs/tags/v2" --jq '.object.sha')

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/session-url-check.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/session-url-check.yml
```

caller の checkout は不要である．検査は GitHub API の読み取りだけで完結する．
必要な権限は `contents: read` と `pull-requests: read` である．
fork からの PR でも読み取りは可能なため，同一 repo 限定の guard は置かない．

## 📜 contract

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: `scripts/check-session-url.sh` の入出力

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 項目 | 内容 |
|---|---|
| 入力 | 環境変数 `GH_TOKEN`・`REPO`・`PR_NUMBER`（すべて必須） |
| exit 0 | 検出なし |
| exit 1 | 検出あり．行ごとの `::error::` と件数の `::error::` を出す |
| exit 2 | API 取得失敗などの実行エラー．検査できない PR は通さない（fail-closed） |

## 🧱 限界

- PR に含まれるコミットだけを見る．マージ済みの履歴は見ない．
  既存の履歴は commit 検索（`gh api /search/commits`）で別途確認する．
- commit 検索は default ブランチだけを対象とする．
  他ブランチの確認は `git log --all --grep` で補う．
- PR 本文の編集履歴は GitHub 上に残る．検出後に本文を直しても履歴からは消えない．
- 検出パターンの文字列そのものにも一致する．本 action を扱う PR で，
  コミットメッセージや本文へ trailer 名やセッション URL の形を平文で書くと落ちる．
  説明は「セッション URL」「trailer 形式」のように言い換える．

## 🧹 見つかったときの対処

- コミットメッセージは `git commit --amend` か `git rebase -i` で直し，force push する．
  Draft PR の段階なら，他者の clone を汚す心配は小さい．
- PR 本文は編集で URL を消す．
- 発生源を止めるため，Claude Code の settings.json へ次を置く．
  反映にはセッションの再起動が要る．

```json
{
  "attribution": {
    "sessionUrl": false
  }
}
```

参照先は次のとおり．

<!-- URL を含む行は文長の上限を超えるため，この一覧だけ文長検査を外す． -->
<!-- textlint-disable ja-technical-writing/sentence-length -->

- Claude Code 設定リファレンス（`attribution`）: `https://code.claude.com/docs/en/settings-reference`
- GitHub commit 検索の仕様: `https://docs.github.com/en/search-github/searching-on-github/searching-commits`
- GitHub 機密データの除去手順: `https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository`

<!-- textlint-enable ja-technical-writing/sentence-length -->
