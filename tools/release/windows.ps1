param(
    [string]$Python = '.venv-release/Scripts/python.exe',
    [string]$Iscc = 'build/tools/inno/ISCC.exe',
    [string]$OutputDir,
    [switch]$Unsigned
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot/process.ps1"
. "$PSScriptRoot/inno.ps1"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repoRoot
try {
    $Python = (Resolve-Path -LiteralPath $Python).Path
    $Iscc = (Resolve-Path -LiteralPath $Iscc).Path
    Assert-InnoToolchain $Iscc
    & $Python -m tools.release.lock --check-environment
    if ($LASTEXITCODE -ne 0) { throw 'Release environment check failed' }
    $version = (& $Python -m tools.release.metadata).Trim()
    if (-not $OutputDir) { $OutputDir = "dist/releases/$version" }
    $releasePath = if ([IO.Path]::IsPathRooted($OutputDir)) { [IO.Path]::GetFullPath($OutputDir) } else { [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDir)) }
    if (-not $releasePath.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Release output must be inside the repository' }
    if (Test-Path -LiteralPath $releasePath) { throw 'Use a new release output directory; existing artifacts are never overwritten' }
    if (-not $Unsigned -and (-not $env:CODE_SIGN_CERT_SHA1 -or -not $env:CODE_SIGN_TIMESTAMP_URL)) { throw 'Production builds require the code-signing certificate and timestamp URL' }
    if (-not $Unsigned) {
        $dirty = @(& git status --porcelain --untracked-files=all)
        if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'Production releases require a clean, committed source tree' }
    }
    New-Item -ItemType Directory -Path $releasePath | Out-Null
    & $Python -m tools.release.inventory
    if ($LASTEXITCODE -ne 0) { throw 'SBOM/notice generation failed' }
    & $Python -m pytest tests -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $Python -m mypy
    if ($LASTEXITCODE -ne 0) { throw 'Type checks failed' }
    $previousBuildPath = $env:PATH
    try {
        # Never pick up native libraries from unrelated tools on the builder's PATH.
        $env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot + ';' + (Split-Path -Parent $Python)
        & $Python -m PyInstaller --noconfirm --clean license_admin.spec
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    } finally { $env:PATH = $previousBuildPath }
    & $Python -m tools.release.artifacts --analysis build/license_admin/Analysis-00.toc --native-report (Join-Path $releasePath 'native-binaries.json')
    if ($LASTEXITCODE -ne 0) { throw 'Unexpected native binary source' }
    $exe = Join-Path $releasePath 'LicenseAdmin.exe'
    Copy-Item -LiteralPath 'dist/LicenseAdmin.exe' -Destination $exe
    foreach ($name in @('THIRD_PARTY_NOTICES.txt', 'sbom.cdx.json')) {
        Copy-Item -LiteralPath (Join-Path 'build/release-metadata' $name) -Destination $releasePath
    }
    Copy-Item -LiteralPath 'pylock.windows.toml' -Destination $releasePath
    & $Python -m tools.release.artifacts --exe $exe --report (Join-Path $releasePath 'binary-report.json')
    if ($LASTEXITCODE -ne 0) { throw 'Binary resource checks failed' }
    if (-not $Unsigned) { & "$PSScriptRoot/sign.ps1" -Path $exe }
    $compilerArgs = @("/DPayloadDir=$releasePath", "/DReleaseVersion=$version", "/DOutputDir=$releasePath")
    if (-not $Unsigned) {
        $compilerArgs += '/DSigning=1'
        $compilerArgs += ('/Sactivo=powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' + "$PSScriptRoot/sign.ps1" + '$q -Path $f')
    }
    & $Iscc @compilerArgs 'packaging/windows/LicenseAdmin.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation/signing failed' }
    $setup = Join-Path $releasePath "LicenseAdmin-$version-windows-x64-setup.exe"
    & $Python -m tools.release.artifacts --exe $setup --report (Join-Path $releasePath 'installer-report.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installer resource checks failed' }
    if (-not $Unsigned) { & "$PSScriptRoot/sign.ps1" -Path $setup -VerifyOnly }
    Invoke-ReleaseProbe -Executable $exe -Report (Join-Path $releasePath 'runtime-report.json')
    & "$PSScriptRoot/test-lifecycle.ps1" -ReleaseDir $releasePath -Iscc $Iscc
    $status = if ($Unsigned) { 'unsigned-development-only' } else { 'signed-and-timestamped' }
    @{ version = $version; signing = $status; commit = (& git rev-parse HEAD); sourceDirty = @(& git status --porcelain --untracked-files=all).Count -ne 0; python = (& $Python --version) } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releasePath 'release.json') -Encoding utf8
    Copy-Item -LiteralPath 'docs/WINDOWS_RELEASE.md' -Destination $releasePath
    Compress-Archive -LiteralPath $exe, (Join-Path $releasePath 'THIRD_PARTY_NOTICES.txt'), (Join-Path $releasePath 'sbom.cdx.json') -DestinationPath (Join-Path $releasePath "LicenseAdmin-$version-windows-x64-portable.zip")
    & $Python -m tools.release.artifacts --checksums $releasePath
    if ($LASTEXITCODE -ne 0) { throw 'Checksum generation failed' }
    Write-Output "Release artifacts: $releasePath ($status)"
} finally { Pop-Location }
