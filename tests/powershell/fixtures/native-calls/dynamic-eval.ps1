# bin/check-native-calls.ps1 の fixture．メンバー呼び出しで文字列を評価する形である．
#
# CommandAst に現れないため，Invoke-Expression を塞ぐだけでは足りない．

$ExecutionContext.InvokeCommand.InvokeScript('git status')

[scriptblock]::Create('gh release view v1.0.0').Invoke()
