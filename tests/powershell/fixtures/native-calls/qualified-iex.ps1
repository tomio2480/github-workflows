# bin/check-native-calls.ps1 の fixture．module 修飾で禁止名を躱す形である．
#
# GetCommandName() は修飾名を返す．完全一致では拾えない．

Microsoft.PowerShell.Utility\Invoke-Expression 'git status'
