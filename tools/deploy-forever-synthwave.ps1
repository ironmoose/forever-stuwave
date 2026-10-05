# Deploy the Forever Synthwave addon from this repo to the local WoW install.
#
# Windows-native counterpart to deploy-forever-synthwave.sh. That script is the
# Fedora -> Windows path over the /mnt/windows NTFS mount; this one is for when
# the Windows box is doing the editing itself and there is no mount involved.
#
# Mirrors the .sh exactly: same destination, same exclusions (mockups/ and all
# markdown are dev-only and just bloat the shipped addon), same mirror semantics
# so a deleted source file disappears from the client.
#
# Runs the Lua 5.1 parse gate first. A syntax error makes WoW skip the whole
# file silently -- the addon "loads" and the component simply never appears --
# so shipping an unparsed file is how you lose an evening.
#
# Usage:
#   .\deploy-forever-synthwave.ps1
#   .\deploy-forever-synthwave.ps1 -WowFlavor _classic_      # TBC Anniversary
#   .\deploy-forever-synthwave.ps1 -SkipParseGate            # emergencies only
#
# After it runs: /reload in-client.

[CmdletBinding()]
param(
    [string]$WowRoot = "C:\Program Files (x86)\World of Warcraft",
    [string]$WowFlavor = "_classic_beta_",
    [switch]$SkipParseGate
)

$ErrorActionPreference = "Stop"

$addonRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $WowRoot "$WowFlavor\Interface\AddOns\ForeverSynthwave"

if (-not (Test-Path $addonRoot)) {
    throw "Addon source not found at: $addonRoot"
}
if (-not (Test-Path (Join-Path $WowRoot $WowFlavor))) {
    throw "WoW client not found at: $(Join-Path $WowRoot $WowFlavor). Pass -WowRoot / -WowFlavor to override."
}

if (-not $SkipParseGate) {
    $gatePython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $gateScript = Join-Path $PSScriptRoot "parse-gate.py"
    if (-not (Test-Path $gatePython)) {
        throw "Parse-gate venv missing at $gatePython. Create it:`n" +
              "  & 'C:/Python312/python.exe' -m venv .venv`n" +
              "  uv pip install --python .venv\Scripts\python.exe lupa"
    }
    Write-Host "Parse gate (Lua 5.1)..." -ForegroundColor Cyan
    & $gatePython $gateScript
    if ($LASTEXITCODE -ne 0) {
        throw "Parse gate FAILED -- $LASTEXITCODE file(s) would not load in game. Not deploying."
    }
    & $gatePython (Join-Path $PSScriptRoot "lua-lint.py") --fail-on high
    if ($LASTEXITCODE -ne 0) { throw "Lua lint HIGH gate failed; not deploying." }
}

# Stage runtime only; never copy tools, mockups, source metadata or generators.
$sourcePath = [IO.Path]::GetFullPath($addonRoot).TrimEnd('\')
$targetPath = [IO.Path]::GetFullPath($destination).TrimEnd('\')
if ($targetPath -eq $sourcePath -or $targetPath.StartsWith($sourcePath + '\', [StringComparison]::OrdinalIgnoreCase) -or (Test-Path (Join-Path $destination ".git"))) {
    throw "Destination is a source/Git checkout; update it with git pull."
}
$stage = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Get-ChildItem $addonRoot -File | Where-Object { $_.Extension -eq ".lua" -or $_.Name -in @("ForeverSynthwave.toc", "Bindings.xml", "LICENSE") } | Copy-Item -Destination $stage
    foreach ($folder in @("media", "fonts")) {
        $subdir = Join-Path $stage $folder
        New-Item -ItemType Directory -Path $subdir | Out-Null
        Get-ChildItem (Join-Path $addonRoot $folder) -File | Where-Object {
            ($folder -eq "media" -and $_.Extension -eq ".tga") -or
            ($folder -eq "fonts" -and ($_.Extension -eq ".ttf" -or $_.Name -match '^(OFL|LICENSE|COPYING).*\.txt$'))
        } | Copy-Item -Destination $subdir
    }
    Write-Host "Deploying -> $destination" -ForegroundColor Cyan
    robocopy $stage $destination /MIR /NJH /NJS /NDL /NP | Out-Host
    if ($LASTEXITCODE -ge 8) { throw "robocopy FAILED with exit code $LASTEXITCODE" }
} finally {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
}
Write-Host "Deployed Forever STUwave -> $WowFlavor" -ForegroundColor Green
Write-Host "Restart the client when files were added; otherwise /reload." -ForegroundColor Green
exit 0
