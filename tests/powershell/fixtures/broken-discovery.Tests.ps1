# bin/run-pester.ps1 の回帰確認に使う fixture（tests/powershell/run-pester.Tests.ps1 から起動）．
#
# 閉じ括弧が欠けており discovery に失敗する．
# Pester はこのとき FailedCount を 0 のまま Container failed として扱う．
# 件数だけを見て終了コードを決めると，壊れた suite が緑で通る．

Describe 'fixture' {
  It 'is never discovered' {
    $true | Should -BeTrue
