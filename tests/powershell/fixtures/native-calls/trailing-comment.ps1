# bin/check-native-calls.ps1 の fixture．注記とコマンドの間にコードを挟む形である．
#
# 行末コメントのある行はコメント行ではない．
# ここで塊が切れなければ，上の注記が下のコマンドへ届いてしまう．

# native-direct: この注記は下の git へ届いてはいけない
Write-Output 'x' # ただの行末コメント
git status
