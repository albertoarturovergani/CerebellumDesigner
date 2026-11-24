#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Install', 'Start', 'Exports', 'Terminal')][string]$Action = 'Start',
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Distribution = 'Ubuntu-24.04',
    [ValidateRange(1024, 65535)][int]$Port = 8891
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Use this launcher on Windows. Ubuntu users should use start_designer.sh.' }
    # WSL emits UTF-8 paths; preserve accented Windows usernames under PowerShell 5.1.
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $OutputEncoding
    $wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
    if (-not (Test-Path -LiteralPath $wsl)) {
        throw 'WSL2 is required. In an Administrator PowerShell run: wsl --install -d Ubuntu-24.04 . Restart Windows and create your Ubuntu username/password.'
    }
    # wslpath handles spaces, accents and user-specific Windows drive letters.
    $linuxPath = @(& $wsl --distribution $Distribution --exec wslpath -u $PSScriptRoot)
    if ($LASTEXITCODE -ne 0 -or $linuxPath.Count -ne 1 -or -not $linuxPath[0].StartsWith('/')) {
        throw 'Ubuntu-24.04 is not ready. Run: wsl --install -d Ubuntu-24.04 ; restart if requested, then open Ubuntu and create a normal Linux user.'
    }
    $helper = $linuxPath[0].TrimEnd('/') + '/wsl-helper.sh'
    $arguments = Get-CDWslArguments $Distribution $helper 'check' $Port
    & $wsl @arguments
    if ($LASTEXITCODE -ne 0) { throw 'WSL prerequisites failed. See the message above.' }

    switch ($Action) {
        'Install' {
            $archive = Join-Path $PSScriptRoot 'payload\CerebellumDesigner_Ubuntu_20261123.tar.gz'
            # Also work directly from a clone of this repository.
            if (-not (Test-Path -LiteralPath $archive)) {
                $archive = Join-Path (Split-Path $PSScriptRoot -Parent) 'downloads\CerebellumDesigner_Ubuntu_20261123.tar.gz'
            }
            Assert-CDArchive $archive
            $arguments = Get-CDWslArguments $Distribution $helper 'install' $Port
            & $wsl @arguments
            if ($LASTEXITCODE -ne 0) { throw 'Installation did not complete. Existing results were preserved. Read the error above before retrying.' }
            Write-Host 'Installed. Double-click 2_Start_Designer.cmd to open the dashboard.' -ForegroundColor Green
        }
        'Start' {
            $arguments = Get-CDWslArguments $Distribution $helper 'ready' $Port
            & $wsl @arguments
            if ($LASTEXITCODE -ne 0) { throw 'Run 1_Install_Designer.cmd first.' }
            $state = Get-CDPortState $Port
            if ($state -eq 'occupied') {
                throw "Port $Port is used by another application. Do not close it automatically. Use: .\2_Start_Designer.cmd -Port 8893"
            }
            if ($state -eq 'free') {
                $arguments = Get-CDWslArguments $Distribution $helper 'start' $Port
                $commandLine = ($arguments | ForEach-Object { ConvertTo-CDNativeArgument $_ }) -join ' '
                $server = Start-Process -FilePath $wsl -ArgumentList $commandLine -PassThru
                $deadline = (Get-Date).AddSeconds(90)
                $ready = $false
                do {
                    Start-Sleep -Milliseconds 700
                    if ((Get-CDPortState $Port) -eq 'designer') { $ready = $true; break }
                    if ($server.HasExited) { throw 'Designer stopped before becoming ready. Read the server error; no reconstruction was started.' }
                } while ((Get-Date) -lt $deadline)
                if (-not $ready) { throw "The dashboard is not reachable at http://127.0.0.1:$Port/ . Check the server window and WSL localhost forwarding; do not launch another copy." }
            }
            Start-Process "http://127.0.0.1:$Port/"
            Write-Host 'Designer is open in your Windows browser. Keep the server window open; Ctrl+C stops it.'
        }
        'Exports' {
            $arguments = Get-CDWslArguments $Distribution $helper 'exports' $Port
            $folder = @(& $wsl @arguments)
            if ($LASTEXITCODE -ne 0 -or $folder.Count -ne 1) { throw 'Export folder is unavailable. Install Designer first.' }
            Start-Process -FilePath 'explorer.exe' -ArgumentList (ConvertTo-CDNativeArgument $folder[0])
        }
        'Terminal' {
            $arguments = Get-CDWslArguments $Distribution $helper 'terminal' $Port
            & $wsl @arguments
            if ($LASTEXITCODE -ne 0) { throw 'The reconstruction terminal returned an error.' }
        }
    }
    exit 0
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
