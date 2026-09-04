# bin/run-pester.ps1 の回帰確認に使う fixture（tests/powershell/run-pester.Tests.ps1 から起動）．
#
# 必ず失敗する suite である．-FailOnSkipped の有無にかかわらず，
# 失敗が非 0 で伝わることを確かめるために使う．

Describe 'fixture' {
  It 'fails' {
    $true | Should -BeFalse
  }
}
