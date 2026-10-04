# Shared process runner for offline packaging probes and installer tests.
function Invoke-ReleaseProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [int]$TimeoutSeconds = 300
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            # A one-file PyInstaller launcher owns a child process. Kill only this
            # launched process tree, not other instances or a name-based match.
            & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $process.Id /T /F | Out-Null
            throw "Timed out: $FilePath"
        }
        # WaitForExit refreshes process state before reading ExitCode.
        $process.WaitForExit()
        return $process.ExitCode
    } finally { $process.Dispose() }
}

function Invoke-ReleaseProbe {
    param([string]$Executable, [string]$Report)
    $previousPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        $code = Invoke-ReleaseProcess -FilePath $Executable -Arguments @('--self-test-output', ('"' + $Report + '"')) -TimeoutSeconds 60
        if ($code -ne 0 -or -not (Test-Path -LiteralPath $Report)) { throw 'Frozen runtime self-test failed' }
        $result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
        if ($result.ok -ne $true) { throw 'Frozen runtime self-test reported a failure' }
    } finally { $env:QT_QPA_PLATFORM = $previousPlatform }
}
