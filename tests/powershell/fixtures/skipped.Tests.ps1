# bin/run-pester.ps1 の回帰確認に使う fixture（tests/powershell/run-pester.Tests.ps1 から起動）．
#
# 成功 1 件と skip 1 件を持つ suite である．
# 実環境では 5.1 の不在で skip される Issue #184 の状況を模す．

Describe 'fixture' {
  It 'passes' {
    $true | Should -BeTrue
  }

  It 'is skipped' -Skip {
    $true | Should -BeFalse
  }
}
