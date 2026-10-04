param([string]$Uv = 'uv')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repoRoot
try {
    & $Uv pip compile requirements-build.in --python-version 3.12.10 --python-platform x86_64-pc-windows-msvc --only-binary :all: --format pylock.toml --output-file pylock.windows.toml --default-index https://pypi.org/simple
    if ($LASTEXITCODE -ne 0) { throw 'Windows lock resolution failed' }
    python -m tools.release.lock --export requirements-build.windows.txt
    if ($LASTEXITCODE -ne 0) { throw 'Lock export failed' }
    & $Uv pip compile requirements.in --python-version 3.12 --universal --generate-hashes --only-binary :all: --constraint requirements-build.windows.txt --output-file requirements.txt --default-index https://pypi.org/simple
    if ($LASTEXITCODE -ne 0) { throw 'Runtime lock resolution failed' }
} finally { Pop-Location }
