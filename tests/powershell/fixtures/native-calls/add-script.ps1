# bin/check-native-calls.ps1 の fixture．PowerShell インスタンスで評価する形である．
#
# Create() を同じ式で呼ばないため，型と組の判定では届かない．

param([System.Management.Automation.PowerShell]$Shell)

$Shell.AddScript('git status').Invoke()
