# native command を「終了コードで分岐する」ために呼ぶヘルパー．
#
# 実行するスクリプトではない．利用側から dot-source して使う．
#
#   . (Join-Path $PSScriptRoot 'lib/native.ps1')
#
# Windows PowerShell 5.1 は $ErrorActionPreference = 'Stop' のもとで，
# native command が stderr へ書いた内容を ErrorRecord へ昇格させる．
# 昇格はリダイレクト（`*> $null`）より先に起きるため，呼び出し側では抑止できない．
# PowerShell 7.3 以降も $PSNativeCommandUseErrorActionPreference が真なら，
# 非 0 終了で同じく終了エラーになる．
#
# どちらも「stderr を出しつつ非 0 で終える」正常な分岐を潰す．
# 例は `gh release view` である．Release 未作成は想定内の経路であり，
# 終了コードで判定したい（Issue #179）．

function Invoke-NativeCommand {
  <#
    .SYNOPSIS
      scriptblock 内の native command を，終了エラーへ昇格させずに実行する．
    .DESCRIPTION
      標準出力と $LASTEXITCODE はそのまま呼び出し元へ渡る．
      緩和は関数スコープの局所変数であり，呼び出し元の設定は変わらない．
    .EXAMPLE
      Invoke-NativeCommand { gh release view $Version *> $null }
      if ($LASTEXITCODE -eq 0) { ... }
    .EXAMPLE
      Invoke-NativeCommand { & gh @args } -ArgumentList $GhArgs
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory = $true, Position = 0)]
    [scriptblock]$Command,

    # scriptblock 内では $args で受ける．外の変数を暗黙に拾うのではなく
    # 明示して渡したい場合に使う
    [Parameter(Position = 1)]
    [object[]]$ArgumentList = @()
  )

  # 代入は関数スコープの局所変数を作る．PowerShell の変数解決は呼び出し階層を
  # 遡るため，& で呼ぶ scriptblock からはこの値が見える．
  # 関数を抜ければ消えるため，明示的な復元は要らない．
  # MUTATION 2: 7 でだけ緩和する．ubuntu の機構テストは通り，5.1 でのみ壊れる
  if ($PSVersionTable.PSVersion.Major -ge 7) { $ErrorActionPreference = 'Continue' }
  # 7.3 以降にのみ存在する．5.1 では未定義の変数を作るだけで害は無い
  $PSNativeCommandUseErrorActionPreference = $false

  & $Command @ArgumentList
}
