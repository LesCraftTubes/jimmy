# Publie une nouvelle version : change le numéro, commit, tag, push. GitHub Actions construit l'installateur
# et le joint à la release ; les Jimmy déjà installés proposent alors la mise à jour.
# Usage : powershell -ExecutionPolicy Bypass -File release.ps1 -Version 1.1.0
param([Parameter(Mandatory = $true)][string]$Version)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Numéro de version invalide (attendu : 1.2.3)" }
if (git status --porcelain) { Write-Host "Des changements ne sont pas encore commités : ils seront inclus dans la version $Version." }
(Get-Content version.py) -replace '__version__ = ".*"', "__version__ = `"$Version`"" | Set-Content version.py -Encoding utf8
git add -A
git commit -m "Version $Version"
git tag "v$Version"
git push
git push origin "v$Version"
Write-Host "Version $Version publiée : suis la construction dans l'onglet Actions de GitHub."
