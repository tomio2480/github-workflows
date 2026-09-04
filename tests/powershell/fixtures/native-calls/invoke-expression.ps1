# bin/check-native-calls.ps1 の fixture．文字列評価で検査を迂回する形である．
#
# 文字列の中身は AST に現れないため，native command かどうかを判定できない．
# 迂回を許さないため，Invoke-Expression 自体を違反とする．

Invoke-Expression 'git status'

iex 'gh release view v1.0.0'
