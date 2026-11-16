# Publie une nouvelle version : change le numéro, commit, tag, push. GitHub Actions construit l'installateur
# et le joint à la release ; les Jimmy déjà installés proposent alors la mise à jour.
# Usage : powershell -ExecutionPolicy Bypass -File release.ps1 -Version 1.1.0 [-Notes notes.md]
# Avec -Notes (fichier de notes en français) : le script attend la fin de la construction, pose les notes sur la release
# et supprime les releases plus anciennes (une seule reste téléchargeable). Sans -Notes : seulement commit, tag, push.
param([Parameter(Mandatory = $true)][string]$Version, [string]$Notes = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Numéro de version invalide (attendu : 1.2.3)" }
# Garde anti-fuites : rien de privé (serveur, mémoire, packs, secrets) ne doit partir sur GitHub.
python leak_guard.py
if ($LASTEXITCODE -ne 0) { throw "Garde anti-fuites : publication refusée (voir la liste ci-dessus)." }
if (git status --porcelain) { Write-Host "Des changements ne sont pas encore commités : ils seront inclus dans la version $Version." }
(Get-Content version.py) -replace '__version__ = ".*"', "__version__ = `"$Version`"" | Set-Content version.py -Encoding utf8
git add -A
git commit -m "Version $Version"
git tag "v$Version"
git push
git push origin "v$Version"
Write-Host "Version $Version publiée : suis la construction dans l'onglet Actions de GitHub."
if ($Notes) {
    if (-not (Test-Path $Notes)) { throw "Fichier de notes introuvable : $Notes" }
    Write-Host "Attente de la release v$Version (la construction prend environ 4 minutes)..."
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
        gh release view "v$Version" --json assets --jq ".assets | length" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $n = [int](gh release view "v$Version" --json assets --jq ".assets | length"); if ($n -ge 1) { $ok = $true; break } }
        Start-Sleep -Seconds 15
    }
    if (-not $ok) { throw "La release v$Version n'a pas ses fichiers : vérifie l'onglet Actions, puis relance gh release edit à la main." }
    gh release edit "v$Version" --title "Jimmy $Version" --notes-file $Notes
    foreach ($t in (gh release list --json tagName --jq ".[].tagName")) { if ($t -ne "v$Version") { gh release delete $t --cleanup-tag --yes } }
    Write-Host "Release v$Version publiée avec ses notes ; les anciennes sont supprimées."
}
