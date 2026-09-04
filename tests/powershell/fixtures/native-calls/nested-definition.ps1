# bin/check-native-calls.ps1 の fixture．入れ子の関数で名前を隠す形である．
#
# 内側の gh は呼び出し位置から見えない．実際には native の gh が起動する．
# 定義を無条件に全件集めると素通りする．

function Helper {
  function gh {
    Write-Output 'not the real gh'
  }
}

gh release view v1.0.0
