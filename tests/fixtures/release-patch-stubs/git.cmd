@echo off
rem bin/release-patch.ps1 の 5.1 回帰テスト用 git スタブ（PATH へ置いて使う）．
rem 関数スタブでは native command にならず，stderr の昇格を再現できない．
rem cmd の解析はブロック構文で行末に敏感なため，if は入れ子の 1 行で書く．
if "%~1"=="rev-parse" if "%~2"=="--is-shallow-repository" echo false
if "%~1"=="rev-parse" if "%~2"=="--is-shallow-repository" exit /b 0
if "%~1"=="rev-parse" exit /b 1
if "%~1"=="ls-remote" echo 1111111111111111111111111111111111111111
exit /b 0
