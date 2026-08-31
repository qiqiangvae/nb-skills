@echo off
rem ============================================================================
rem  setup.cmd - Windows launcher for setup.ps1
rem
rem  Purpose: Windows PowerShell defaults to ExecutionPolicy "Restricted", which
rem  blocks running any .ps1. This wrapper launches setup.ps1 with
rem  "-ExecutionPolicy Bypass" so you do NOT need to change system policy.
rem
rem  Usage:
rem    .\scripts\setup.cmd                                interactive
rem    .\scripts\setup.cmd --agent dsh --all               install all to DSH
rem    .\scripts\setup.cmd --dry-run --agent dsh           preview only
rem
rem  All arguments are forwarded to setup.ps1. See setup.ps1 --help for options.
rem ============================================================================
setlocal
set "SCRIPT_DIR=%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup.ps1" %*

exit /b %ERRORLEVEL%
