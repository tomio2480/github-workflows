# bin/check-native-calls.ps1 の fixture．注記を文字列で騙る形である．
#
# 免除は comment token だけを見る．文字列の中身では免除されない．

$Message = '# native-direct: これはコメントではない'
gh release view v1.0.0 *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Output $Message
}
