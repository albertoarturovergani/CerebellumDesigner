# Offline launcher tests: no WSL installation, server or browser is started.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'launcher-common.ps1')
$checks = 0
function Assert-Equal($Actual, $Expected, $Label) {
    if ($Actual -cne $Expected) { throw "$Label : expected [$Expected], got [$Actual]" }
    $script:checks++
}
function Assert-Throws([scriptblock]$Code, $Label) {
    $caught = $false
    try { & $Code } catch { $caught = $true }
    if (-not $caught) { throw "Expected rejection: $Label" }
    $script:checks++
}

Get-ChildItem -LiteralPath $root -Filter '*.ps1' -Recurse | ForEach-Object {
    $tokens = $null; $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    $script:checks++
}
Assert-Equal (ConvertTo-CDNativeArgument '') '""' 'empty'
Assert-Equal (ConvertTo-CDNativeArgument '/mnt/c/My files/a.sh') '"/mnt/c/My files/a.sh"' 'spaces'
Assert-Equal (ConvertTo-CDNativeArgument 'C:\My files\') '"C:\My files\\"' 'trailing backslash'
Assert-Equal (ConvertTo-CDNativeArgument 'a"b') '"a\"b"' 'embedded quotes'
Assert-Equal (ConvertTo-CDNativeArgument 'x&y;$(bad)') '"x&y;$(bad)"' 'literal metacharacters'
$arguments = @(Get-CDWslArguments 'Ubuntu-24.04' "/mnt/c/Alberto's work/wsl-helper.sh" 'start' 8893)
Assert-Equal $arguments.Count 7 'separate native arguments'
Assert-Equal $arguments[4] "/mnt/c/Alberto's work/wsl-helper.sh" 'apostrophe retained'
Assert-Equal $arguments[6] '8893' 'custom port'
Assert-Throws { Get-CDWslArguments 'Ubuntu;bad' '/tmp/h.sh' 'start' 8891 } 'distro injection'
Assert-Throws { Get-CDWslArguments 'Ubuntu' 'relative.sh' 'start' 8891 } 'relative helper'
Assert-Throws { Get-CDWslArguments 'Ubuntu' '/tmp/h.sh' 'delete' 8891 } 'unknown action'
Assert-Throws { Get-CDWslArguments 'Ubuntu' '/tmp/h.sh' 'start' 80 } 'privileged port'
Assert-Equal (Test-CDCatalog ([pscustomobject]@{name='Cerebellum Designer'; populations=@(1,2,3,4,5,6,7)})) $true 'recognise Designer'
Assert-Equal (Test-CDCatalog ([pscustomobject]@{name='Other'; populations=@(1,2,3,4,5,6,7)})) $false 'reject other app'
Assert-Equal (Test-CDCatalog ([pscustomobject]@{error='not ready'})) $false 'reject malformed response'
Assert-Equal (Test-CDCatalog $null) $false 'reject null'
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('cd-launcher-test-' + [guid]::NewGuid())
try {
    [System.IO.File]::WriteAllText($temporary, 'not an archive')
    Assert-Throws { Assert-CDArchive $temporary } 'tampered payload'
    Assert-Throws { Assert-CDArchive ($temporary + '.missing') } 'missing payload'
    $archive = Join-Path (Split-Path $root -Parent) 'downloads/CerebellumDesigner_Ubuntu_20261123.tar.gz'
    if (-not (Test-Path -LiteralPath $archive)) { $archive = Join-Path $root 'payload/CerebellumDesigner_Ubuntu_20261123.tar.gz' }
    Assert-CDArchive $archive
    $checks++
} finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
Write-Host "$checks launcher checks passed. No real WSL end-to-end test was performed."
