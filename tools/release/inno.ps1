function Assert-InnoToolchain([string]$Compiler) {
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../../packaging/windows/inno-6.7.3.sha256.json') -Raw | ConvertFrom-Json
    $directory = Split-Path -Parent $Compiler
    foreach ($entry in $manifest) {
        $file = Join-Path $directory $entry.file
        if (-not (Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw "Inno Setup 6.7.3 toolchain hash mismatch: $($entry.file). Reinstall with bootstrap-inno.ps1."
        }
    }
}
