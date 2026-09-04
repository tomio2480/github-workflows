# bin/check-native-calls.ps1 の fixture．cmdlet の別名を呼ぶ形である．
#
# gci は Get-ChildItem の別名であり native ではない．
# ResolvedCommand が空を返す別名があるため，Definition から引き直す必要がある．
# ls は環境により実行ファイルを指すため使わない．

gci
