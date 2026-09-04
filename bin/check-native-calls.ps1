# native command の直接呼びを検出する（Issue #185）．
#
# 使い方:
#   pwsh -NoProfile -File bin/check-native-calls.ps1 <path> [<path> ...]
#
# 検査対象の決定は bin/verify-shell.py の責務とする．本スクリプトは受け取った
# path をそのまま検査し，違反が 1 件でもあれば非 0 で終わる．
#
# 規律は docs/shell-quality.md の「native command の呼び出し規律」節にある．
# 終了コードで分岐する native command は Invoke-NativeCommand 経由で呼ぶ．
# Windows PowerShell 5.1 は stderr を終了エラーへ昇格させるためである．
#
# 直接呼びのまま残す正当な例外は，同じ行か直前の行へ次の注記を書く．
#
#   # native-direct: <理由>
#
# 判定は AST で行う．正規表現では複数行にまたがる呼び出しを取りこぼす．
#
# 既知の限界は次の 2 つである．どちらも現状の bin/ には当たらない．
#
# - 免除は行単位である．1 行へ native command を 2 つ並べると，
#   注記 1 つで両方が免除される．
# - scriptblock を変数へ入れてから渡す形（`$sb = { git status }` の後に
#   `Invoke-NativeCommand $sb`）は，包まれていると判定できない．
#   scriptblock は呼び出しの引数位置に直接書く．

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
  [string[]]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$WrapperName = 'Invoke-NativeCommand'
$ExceptionMarker = 'native-direct:'

# 文字列評価は中身が AST に現れず，native command かどうかを判定できない．
# 検査を迂回できてしまうため，呼び出しそのものを違反とする．
# CLAUDE.md の Shell / CLI 品質規律でも禁じている
$ForbiddenNames = @('Invoke-Expression', 'iex')

# メンバー呼び出しでも文字列は評価できる．CommandAst に現れないため別に見る．
# 例は $ExecutionContext.InvokeCommand.InvokeScript('git status') である
$ForbiddenMembers = @('InvokeScript', 'ExpandString', 'NewScriptBlock', 'AddScript')

# 型と組で見るもの．メンバー名だけでは広すぎる．
# Create は [scriptblock]::Create(...) だけを違反とする．
# 名前だけで倒すと [HashSet[string]]::Create() まで巻き込む
$ForbiddenStaticMembers = @{
  'scriptblock'                              = @('Create')
  'System.Management.Automation.ScriptBlock' = @('Create')
}

function Test-WrappedInInvokeNativeCommand {
  <#
    .SYNOPSIS
      CommandAst が Invoke-NativeCommand の scriptblock 引数の内側にあるか．
  #>
  param([System.Management.Automation.Language.Ast]$Node)

  $current = $Node.Parent
  while ($null -ne $current) {
    if ($current -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) {
      $owner = $current.Parent
      if ($owner -is [System.Management.Automation.Language.CommandAst] -and
        $owner.GetCommandName() -eq $WrapperName) {
        return $true
      }
    }
    # ヘルパー自身の本体は，渡された scriptblock を呼ぶ側である．
    # 自分で自分を包むことはできない
    if ($current -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $current.Name -eq $WrapperName) {
      return $true
    }
    $current = $current.Parent
  }
  return $false
}

# 対象すべてを先に parse する．ファイル内で定義した関数は native ではないため，
# 名前を集めてから判定する．
#
# 定義名はファイルごとに持つ．関数はファイルを跨いで見えないためである．
# 全ファイル共通で集めると，あるファイルの `function gh { }` が
# 別ファイルの gh 呼び出しを素通りさせる．
$parsed = [ordered]@{}

foreach ($target in $Path) {
  $tokens = $null
  $parseErrors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $target, [ref]$tokens, [ref]$parseErrors
  )

  if ($parseErrors.Count -gt 0) {
    Write-Error "failed to parse ${target}: $($parseErrors[0].Message)"
    exit 1
  }

  # dot-source した helper は対象に含まれていなくても名前で判定するため，
  # ヘルパー名だけは常に既知として扱う
  $localNames = New-Object 'System.Collections.Generic.HashSet[string]' (
    [System.StringComparer]::OrdinalIgnoreCase
  )
  $null = $localNames.Add($WrapperName)

  # 入れ子の定義は集めない．`function Helper { function gh { } }` の内側は
  # 呼び出し位置から見えず，実際には native の gh が起動する
  $definitions = $ast.FindAll(
    { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] },
    $true
  )
  foreach ($definition in $definitions) {
    $outer = $definition.Parent
    $isNested = $false
    while ($null -ne $outer) {
      if ($outer -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        $isNested = $true
        break
      }
      $outer = $outer.Parent
    }
    if ($isNested) {
      continue
    }
    $null = $localNames.Add($definition.Name)
  }

  $parsed[$target] = [pscustomobject]@{
    Ast          = $ast
    Tokens       = $tokens
    DefinedNames = $localNames
  }
}

function Test-NativeCommandName {
  <#
    .SYNOPSIS
      呼び出し名が native command に当たるか．
    .DESCRIPTION
      解決できない名前も native として扱う．module 未導入などで解決に失敗した
      とき，黙って見逃すと「指摘 0 件で成功」に化けるためである．
      判定を緩めるより，偽陽性で気づける側へ倒す．
      別名は解決先まで辿る．実体が実行ファイルなら native である．
  #>
  param(
    [string]$Name,
    [System.Collections.Generic.HashSet[string]]$DefinedNames
  )

  if ($DefinedNames.Contains($Name)) {
    return $false
  }

  $resolved = Get-Command -Name $Name -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -eq $resolved) {
    return $true
  }

  # 別名が実行ファイルを指す場合，CommandType は Alias のままである．
  # 辿らないと native の呼び出しを取りこぼす
  $seen = 0
  while ($resolved.CommandType -eq 'Alias') {
    $next = $resolved.ResolvedCommand
    if ($null -eq $next) {
      # ResolvedCommand が空の別名がある．Definition から引き直す
      $next = Get-Command -Name $resolved.Definition -ErrorAction SilentlyContinue |
        Select-Object -First 1
    }
    if ($null -eq $next) {
      # 解決先が分からない．何を起動するか読めないため native 側へ倒す
      return $true
    }
    $resolved = $next
    $seen++
    # 壊れた別名の循環で止まらなくならないようにする
    if ($seen -gt 10) {
      return $true
    }
  }

  return $resolved.CommandType -eq 'Application'
}

$findings = @()

foreach ($target in $parsed.Keys) {
  $entry = $parsed[$target]
  $sourceLines = [System.IO.File]::ReadAllLines($target)

  # 注記のある行を集める．comment は AST に載らないため token から拾う．
  # 文字列リテラルで騙れないよう Comment token だけを見る
  $commentLines = New-Object 'System.Collections.Generic.HashSet[int]'
  $markerLines = New-Object 'System.Collections.Generic.HashSet[int]'
  foreach ($token in $entry.Tokens) {
    if ($token.Kind -ne 'Comment') {
      continue
    }
    $startLine = $token.Extent.StartLineNumber
    if ($token.Text -match [regex]::Escape($ExceptionMarker)) {
      $null = $markerLines.Add($startLine)
    }
    # 行末コメントのある行はコメント行ではない．塊はそこで切れる．
    # 切らないと，注記が間のコードを跨いで下のコマンドへ届く
    if ($token.Extent.StartColumnNumber -eq 1) {
      $null = $commentLines.Add($startLine)
      continue
    }
    $prefix = $sourceLines[$startLine - 1].Substring(
      0, $token.Extent.StartColumnNumber - 1
    )
    if ([string]::IsNullOrWhiteSpace($prefix)) {
      $null = $commentLines.Add($startLine)
    }
  }

  # メンバー呼び出しによる文字列評価を先に拾う
  $members = $entry.Ast.FindAll(
    {
      param($node)
      $node -is [System.Management.Automation.Language.InvokeMemberExpressionAst]
    },
    $true
  )
  foreach ($member in $members) {
    $memberName = $member.Member.Extent.Text.Trim('"', "'")
    $isForbiddenMember = $ForbiddenMembers -contains $memberName

    if (-not $isForbiddenMember -and
      $member.Expression -is [System.Management.Automation.Language.TypeExpressionAst]) {
      $typeName = $member.Expression.TypeName.FullName
      if ($ForbiddenStaticMembers.ContainsKey($typeName)) {
        $isForbiddenMember = $ForbiddenStaticMembers[$typeName] -contains $memberName
      }
    }

    if (-not $isForbiddenMember) {
      continue
    }
    $findings += [pscustomobject]@{
      File    = $target
      Line    = $member.Extent.StartLineNumber
      Command = $memberName
      Reason  = 'string evaluation'
    }
  }

  $commands = $entry.Ast.FindAll(
    { param($node) $node -is [System.Management.Automation.Language.CommandAst] },
    $true
  )

  foreach ($command in $commands) {
    # dot-source（`. path`）は native command の呼び出しではない．
    # 名前を静的に決められないため，除かないと必ず偽陽性になる
    if ($command.InvocationOperator -eq 'Dot') {
      continue
    }

    $name = $command.GetCommandName()

    # module 修飾（`Microsoft.PowerShell.Utility\Invoke-Expression`）を外す．
    # GetCommandName() は修飾名をそのまま返すため，完全一致では躱される
    $bareName = $name
    if ($null -ne $bareName -and $bareName.Contains('\')) {
      $bareName = $bareName.Substring($bareName.LastIndexOf('\') + 1)
    }

    # 文字列評価は包んでも中身を検査できない．包まれていても違反とする
    $isForbidden = $null -ne $bareName -and $ForbiddenNames -contains $bareName

    if (-not $isForbidden) {
      # 名前を静的に決められない呼び出し（& $variable など）も native とみなす
      if ($null -ne $bareName -and
        -not (Test-NativeCommandName -Name $bareName -DefinedNames $entry.DefinedNames)) {
        continue
      }

      if (Test-WrappedInInvokeNativeCommand -Node $command) {
        continue
      }
    }

    $line = $command.Extent.StartLineNumber
    # 行末の注記と，直上の連続したコメント塊の中の注記を許す．
    # 理由が 1 行へ収まらないことがあるためである．
    # 空行やコードで切れた時点で遡るのをやめる
    # 文字列評価は注記でも通さない．中身を検査できないことに変わりはない
    if (-not $isForbidden) {
      $exempt = $markerLines.Contains($line)
      $cursor = $line - 1
      while (-not $exempt -and $commentLines.Contains($cursor)) {
        if ($markerLines.Contains($cursor)) {
          $exempt = $true
        }
        $cursor--
      }
      if ($exempt) {
        continue
      }
    }

    $display = if ($null -eq $name) { $command.Extent.Text } else { $name }
    $findings += [pscustomobject]@{
      File    = $target
      Line    = $line
      Command = $display
      Reason  = if ($isForbidden) { 'string evaluation' } else { 'unwrapped native call' }
    }
  }
}

if ($findings.Count -gt 0) {
  Write-Output "native command call(s) violating the calling rule:"
  foreach ($finding in $findings) {
    Write-Output "  $($finding.File):$($finding.Line): $($finding.Command) [$($finding.Reason)]"
  }
  Write-Output ''
  Write-Output "unwrapped native call: wrap in ${WrapperName}, or annotate with '# ${ExceptionMarker} <reason>'"
  Write-Output 'string evaluation: pass arguments as an array instead'
  exit 1
}

Write-Output "check-native-calls: no unwrapped native command call in $($Path.Count) file(s)"
exit 0
