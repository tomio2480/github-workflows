# bin/check-native-calls.ps1 の fixture．規律に反した形である．
#
# 5.1 では gh の stderr が終了エラーへ昇格し，if へ到達しない．

gh release view v1.0.0 *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Output 'exists'
}
