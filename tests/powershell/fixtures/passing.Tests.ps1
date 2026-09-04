# bin/run-pester.ps1 の回帰確認に使う fixture（tests/powershell/run-pester.Tests.ps1 から起動）．
#
# すべて成功する suite である．
# 親ディレクトリの *.Tests.ps1 だけを拾う glob の外へ置くため，
# 本 gate の Pester 対象には入らない．

Describe 'fixture' {
  It 'passes' {
    $true | Should -BeTrue
  }
}
