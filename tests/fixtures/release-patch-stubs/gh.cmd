@echo off
rem bin/release-patch.ps1 の 5.1 回帰テスト用 gh スタブ（PATH へ置いて使う）．
rem Release 未作成を再現する．stderr へ書きつつ非 0 で終える経路である．
if "%~1"=="release" if "%~2"=="view" echo release not found 1>&2
if "%~1"=="release" if "%~2"=="view" exit /b 1
exit /b 0
