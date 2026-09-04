# bin/check-native-calls.ps1 の fixture．理由を複数行で書いた形である．
#
# 注記が塊の先頭にあり，コマンドは塊の直後にある．

# native-direct: 失敗は必ず表面化する．5.1 は昇格でその場が止まり，
# 7 は素通りするが直後の検査が非 0 で終える
git fetch --quiet origin 'refs/tags/v2'

# 塊が空行で切れていれば免除しない

# native-direct: この注記は下のコマンドへ届かない

gh release view v1.0.0 *> $null
