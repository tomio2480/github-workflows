# bin/check-native-calls.ps1 の fixture．解決できない名前を使う形である．
#
# 実在しないコマンドであり Get-Command では解決できない．
# 見逃すと，ツール未導入の環境で検査が「指摘 0 件で成功」に化ける．

zz-not-a-real-command --check
if ($LASTEXITCODE -eq 0) {
  Write-Output 'ok'
}
