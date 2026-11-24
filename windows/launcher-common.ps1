# Compatible with Windows PowerShell 5.1 and PowerShell 7.
Set-StrictMode -Version Latest

function ConvertTo-CDNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting; never invoke cmd.exe with these arguments.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Get-CDWslArguments {
    param([string]$Distribution, [string]$HelperPath, [string]$Action, [int]$Port = 8891)
    if ($Distribution -notmatch '^[A-Za-z0-9._-]+$') { throw 'Invalid WSL distribution name.' }
    if (-not $HelperPath.StartsWith('/')) { throw 'Expected an absolute Linux helper path.' }
    if ($HelperPath.Contains("`n") -or $HelperPath.Contains("`r")) { throw 'Invalid helper path.' }
    if ($Action -notin @('check', 'install', 'ready', 'start', 'exports', 'terminal')) { throw 'Invalid action.' }
    if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
    return @('--distribution', $Distribution, '--exec', 'bash', $HelperPath, $Action, [string]$Port)
}

function Test-CDCatalog {
    param($Catalog)
    return ($null -ne $Catalog -and
        $null -ne $Catalog.PSObject.Properties['name'] -and
        $Catalog.name -eq 'Cerebellum Designer' -and
        $null -ne $Catalog.PSObject.Properties['populations'] -and
        @($Catalog.populations).Count -eq 7)
}

function Get-CDPortState {
    param([int]$Port)
    try {
        $catalog = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/catalog" -TimeoutSec 2
        if (Test-CDCatalog $catalog) { return 'designer' }
    } catch { }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($connection.AsyncWaitHandle.WaitOne(600)) {
            $client.EndConnect($connection)
            return 'occupied'
        }
    } catch { } finally { $client.Dispose() }
    return 'free'
}

function Assert-CDArchive {
    param([string]$Archive)
    $expected = 'd98bff221871c5e18678ebaf5dfdacc866c06ee444f076a7476968d791704b17'
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw 'The source archive is missing. Extract the entire Windows ZIP before running this launcher.'
    }
    if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'Source archive checksum mismatch. Nothing has been installed; download the package again.'
    }
}
