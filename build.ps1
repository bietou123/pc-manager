# Build a single-file windowed exe: PCManager.exe (in this folder).
# Requirements: Python 3.10+, pip install -r requirements.txt
# Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less files as
# ANSI/GBK, so non-ASCII literals would be garbled.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "python not found; install Python 3 and add it to PATH" }

& $py tools\make_icon.py
if (-not (Test-Path "assets\app.ico")) { throw "assets/app.ico was not generated" }

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name PCManager `
    --icon assets\app.ico `
    --add-data "web;web" `
    --hidden-import clr `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import webview.platforms.winforms `
    app.py

Copy-Item "dist\PCManager.exe" "PCManager.exe" -Force
Remove-Item build, dist, PCManager.spec -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Done: $PSScriptRoot\PCManager.exe"
