# Construit Jimmy.exe puis l'installateur (release\Jimmy-Setup-X.Y.Z.exe).
# Usage : powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = "py"; if (-not (Get-Command py -ErrorAction SilentlyContinue)) { $py = "python" }
if (-not (Test-Path .venv-build)) { & $py -m venv .venv-build }
.\.venv-build\Scripts\python.exe -m pip install --upgrade pip
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.\.venv-build\Scripts\pyinstaller.exe jimmy.spec --noconfirm --clean
$version = (Select-String -Path version.py -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Write-Host "Inno Setup introuvable : installe-le (winget install JRSoftware.InnoSetup) pour créer l'installateur."; exit 0 }
& $iscc "/DMyAppVersion=$version" installer\jimmy.iss
Write-Host "Terminé : release\Jimmy-Setup-$version.exe"
