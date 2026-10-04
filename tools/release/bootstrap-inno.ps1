param([string]$Destination = 'build/tools/inno')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot/inno.ps1"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$destinationPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $Destination))
if (-not $destinationPath.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Compiler install directory must be inside the repository'
}
$download = Join-Path $repoRoot 'build/tools/innosetup-6.7.3.exe'
New-Item -ItemType Directory -Force -Path (Split-Path $download) | Out-Null
if (-not (Test-Path -LiteralPath $download)) {
    Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' -OutFile $download
}
$expectedHash = '9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732'
if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Inno Setup download hash mismatch' }
$signature = Get-AuthenticodeSignature -LiteralPath $download
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') { throw 'Inno Setup publisher verification failed' }
$installer = Start-Process -FilePath $download -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', '/NOICONS',
    ('/DIR="' + $destinationPath + '"')
)
if ($installer.ExitCode -ne 0) { throw "Inno Setup installation failed: $($installer.ExitCode)" }
Assert-InnoToolchain (Join-Path $destinationPath 'ISCC.exe')
Write-Output (Join-Path $destinationPath 'ISCC.exe')
