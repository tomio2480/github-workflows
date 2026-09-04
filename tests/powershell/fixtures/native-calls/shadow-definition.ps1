# bin/check-native-calls.ps1 の fixture．同名の関数を定義する形である．
#
# この定義は別ファイルからは見えない．
# 定義名を全ファイル共通で集めると，violation.ps1 の gh 呼び出しが素通りする．

function gh {
  Write-Output 'not the real gh'
}

gh release view v1.0.0
