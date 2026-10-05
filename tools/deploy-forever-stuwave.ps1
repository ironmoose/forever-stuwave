# Install runtime files and preserve legacy settings. Close WoW before running.
[CmdletBinding()]
param(
    [string]$WowRoot = "C:\Program Files (x86)\World of Warcraft",
    [string]$WowFlavor = "_classic_beta_",
    [switch]$SkipParseGate
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$addonRoot = Join-Path $repoRoot "forever-stuwave"
$client = Join-Path $WowRoot $WowFlavor
$destination = Join-Path $client "Interface\AddOns\forever-stuwave"
$legacy = Join-Path $client "Interface\AddOns\ForeverSynthwave"
if (-not (Test-Path $addonRoot -PathType Container)) { throw "Addon source not found: $addonRoot" }
if (-not (Test-Path $client -PathType Container)) { throw "Client not found: $client" }
$repoPath = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
$targetPath = [IO.Path]::GetFullPath($destination).TrimEnd('\')
if ($targetPath -eq $repoPath -or
    $targetPath.StartsWith($repoPath + '\', [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path (Join-Path $destination ".git")) -or (Test-Path (Join-Path $legacy ".git"))) {
    throw "Destination or legacy addon is a Git checkout; move it outside AddOns first."
}
if (-not $SkipParseGate) {
    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { throw "Run uv sync first, or use -SkipParseGate for a trusted tester checkout." }
    & $python (Join-Path $PSScriptRoot "parse-gate.py")
    if ($LASTEXITCODE -ne 0) { throw "Lua parse/manifest gate failed; not deploying." }
    & $python (Join-Path $PSScriptRoot "lua-lint.py") --fail-on high
    if ($LASTEXITCODE -ne 0) { throw "Lua lint HIGH gate failed; not deploying." }
}
$stage = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    Get-ChildItem $addonRoot -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($addonRoot.Length + 1)
        if ($relative -match '^(Core|Modules)\\.+\.lua$' -or
            $relative -match '^Media\\Textures\\.+\.tga$' -or
            $relative -match '^Media\\Fonts\\.+\.ttf$' -or
            $relative -match '^Media\\Fonts\\(OFL|LICENSE|COPYING).*\.txt$') {
            $output = Join-Path $stage $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $output) -Force | Out-Null
            Copy-Item $_.FullName $output
        }
    }
    Copy-Item (Join-Path $addonRoot "forever-stuwave.toc"), (Join-Path $addonRoot "Bindings.xml"), (Join-Path $repoRoot "LICENSE") -Destination $stage
    $accounts = Join-Path $client "WTF\Account"
    if (Test-Path $accounts) {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        Get-ChildItem $accounts -Recurse -File | Where-Object {
            $_.Directory.Name -eq "SavedVariables" -and $_.Name -in @("ForeverSynthwave.lua", "ForeverSynthwave.lua.bak")
        } | ForEach-Object {
            $target = Join-Path $_.Directory.FullName ($_.Name.Replace("ForeverSynthwave", "forever-stuwave"))
            if (-not (Test-Path $target)) {
                $text = [IO.File]::ReadAllText($_.FullName).Replace("ForeverSynthwave", "ForeverSTUwave")
                $temporary = $target + "." + [Guid]::NewGuid().ToString() + ".tmp"
                try {
                    [IO.File]::WriteAllText($temporary, $text, $utf8)
                    [IO.File]::Move($temporary, $target)
                } finally {
                    if (Test-Path $temporary) { Remove-Item $temporary }
                }
            }
        }
        Get-ChildItem $accounts -Recurse -File -Filter "bindings-cache.wtf" | ForEach-Object {
            $text = [IO.File]::ReadAllText($_.FullName)
            if ($text.Contains("ForeverSynthwave")) {
                $backup = $_.FullName + ".forever-stuwave.bak"
                if (-not (Test-Path $backup)) { Copy-Item $_.FullName $backup }
                $temporary = $_.FullName + "." + [Guid]::NewGuid().ToString() + ".tmp"
                try {
                    [IO.File]::WriteAllText($temporary, $text.Replace("ForeverSynthwave", "ForeverSTUwave"), $utf8)
                    [IO.File]::Replace($temporary, $_.FullName, $null)
                } finally {
                    if (Test-Path $temporary) { Remove-Item $temporary }
                }
            }
        }
    }
    if (Test-Path $legacy -PathType Container) {
        $retired = Join-Path $client "Interface\RetiredAddOns"
        New-Item -ItemType Directory -Path $retired -Force | Out-Null
        Move-Item $legacy (Join-Path $retired ("ForeverSynthwave-" + [Guid]::NewGuid().ToString()))
    }
    robocopy $stage $destination /MIR /NJH /NJS /NDL /NP | Out-Host
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }
} finally {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
}
Write-Host "Installed Forever STUwave -> $destination"
Write-Host "Fully restart WoW."
exit 0
