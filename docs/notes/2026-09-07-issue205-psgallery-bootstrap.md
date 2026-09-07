# 🧰 成功しているのに落ちる step（Issue #205）

## 要約

中央の Shell quality reusable workflow が落ちた．
PSGallery 未登録の runner で，toolchain setup ごと落ちる．
一過性で狙って再現できないため，
`Unregister-PSRepository` で故障側を人為的に作って測った．
測ってみると，当初立てた 3 つの対応案はいずれも単独では成り立たなかった．
windows では，登録の成功した step が落ちる経路もあった．
原因は cmdlet の内側で呼ばれる `nuget.exe` の終了コードである．
初版はその終了コードを握り潰す根拠を誤って置き，レビューで差し替えた．

## 目次

- 🔁 一過性の故障は，こちらから壊して測る
- 🧾「登録の失敗」ではなかった
- 🧪 案の検証は，故障側と正常側の両方の入力へ当てる
- 🧱 `Invoke-NativeCommand` で包めない領域がある
- 🪞 自分が引用した文書と矛盾する前提を置いていた

## 🔁 一過性の故障は，こちらから壊して測る

Issue #205 の観測は 1 回きりであり，同一 commit の再実行で pass していた．
待っても再現しない．**再現を待つ代わりに，故障側の状態を人為的に作った．**

測定専用のブランチへ使い捨ての workflow を置いた．
`Unregister-PSRepository -Name PSGallery` で未登録状態を作る．
そのうえで各案を走らせた．測定後にブランチごと削除した．

このとき，未登録にできたことを `throw` で確かめる step を挟んだ．
未登録にできていなければ，以降は正常系を測っているだけである．
**そのとき「どの案も通った」という誤った結論が出る．**
故障側を作る測定では，故障が作れたこと自体を検査する．

## 🧾「登録の失敗」ではなかった

案 2 は未登録なら `Register-PSRepository -Default` する案である．
`ubuntu-latest` で通り，`windows-latest` で落ちた．
ログは次のとおりである．

```text
Missing option value for: '-source'
NuGet.Commands.CommandException: Missing option value for: '-source'
```

ところが，この直後の `Get-PSRepository` は PSGallery を表示していた．
**登録は成功している．** 失敗したのは登録ではなく step の終了コードである．

`Register-PSRepository -Default` は内部で `nuget.exe` を呼ぶ．
これが異常終了して `$LASTEXITCODE` へ 1 を残す．
cmdlet は `$LASTEXITCODE` を戻さないため，後続の `Install-Module` を
何度通しても 1 のままである．
runner の pwsh は script の末尾で `exit $LASTEXITCODE` を実行する．

診断は，1 行ごとに `$LASTEXITCODE` を出す case を足して行った．
`Register` の直後で 1 になり，以降変わらないことがはっきりした．
**エラーメッセージの読解ではなく，値の観測で決着した．**

## 🧪 案の検証は，故障側と正常側の両方の入力へ当てる

第 2 ラウンドでは，修正案そのものを 2 つの入力へ当てた．
未登録から（故障側）と，登録済みから（通常）である．
後者は `if` の guard が登録を飛ばす経路であり，
**修正が正常系を壊していないことは，別の入力でしか確かめられない．**

併せて，導入後に版まで突き合わせる assert を置いた．
windows runner には PSScriptAnalyzer と Pester が preinstall されている．
「module がある」だけを見ると，別版が残っているだけで素通りする．
`1.25.0` と `6.1.0` を名指しで確かめた．

修正案の case には `continue-on-error` を付けなかった．
観測用の case と検証用の case で，落ち方の扱いを変える．

## 🧱 `Invoke-NativeCommand` で包めない領域がある

本リポジトリは native command の終了コードを `Invoke-NativeCommand` で受ける．
この規律は `bin/check-native-calls.ps1` が AST で検査する（Issue #179・#185）．
今回の呼び出しはこれに掛からない．
**`nuget.exe` の呼び出しが cmdlet の内側にあり，呼び出し側の AST に現れない．**

規律の対象は「自分が書いた native command」であって，
「自分が受け取る終了コード」ではなかった．
workflow の `shell: pwsh` step では，後者だけが問題になる場面がある．

対処は step の末尾で `$global:LASTEXITCODE = 0` を書くことである．
ただし **戻しを単独で置いてはならない．** 理由は次節に書く．

## 🪞 自分が引用した文書と矛盾する前提を置いていた

初版では `$LASTEXITCODE` の戻しを，導入の成否を確かめずに置いた．
根拠はこうである．「`Install-Module` の失敗は
`$ErrorActionPreference = 'Stop'` で止まり，戻しの行へ到達しない」．

これは誤りである．**同じ `docs/shell-quality.md` の，
本件で追記した節のすぐ上に反例が書いてある．**

> 7 は native command の非 0 終了で停止しない．

`Install-Module` の内側が native command を呼んで黙って失敗すれば，
PowerShell のエラーは飛ばない．戻しがその痕跡まで消す．
**今回 `Register-PSRepository` で踏んだ経路と地続きである．**
自分で観測した現象を，2 行下の推論へ反映できていなかった．

レビューでこの矛盾を指摘され，根拠を差し替えた．
「エラーが飛ばなかった」という消極的な根拠を，
「意図した版が実際に入った」という積極的な根拠へ置き換えた．
`throw` を戻しより前へ置き，通ったときだけ戻す．

得られた規律は次のとおりである．

- **終了コードを握り潰す変更は，握り潰してよい理由とセットで書く．**
  理由が「失敗なら止まるはず」の形になったら疑う．止まらない実装がある．
- **文書を引用して追記するときは，引用元の残りも読む．**
  自分の主張の反例が同じ節にあることがある．
- レビュー依頼では，疑っている前提を名指しで書くと，
  そこを重点的に検証してもらえる（[2026-09-05-issue140-self-caller.md](2026-09-05-issue140-self-caller.md) と同じ筋）．

## 参照

- Issue #205，PR #206
- `docs/shell-quality.md`「native command の呼び出し規律」
- `tests/python/test_shell_quality_bootstrap.py`
- 関連: Issue #179（5.1 の stderr 昇格），Issue #185（規律を機械で守る）
