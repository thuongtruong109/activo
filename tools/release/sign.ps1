param(
    [Parameter(Mandatory)][string]$Path,
    [string]$CertificateThumbprint = $env:CODE_SIGN_CERT_SHA1,
    [string]$TimestampUrl = $env:CODE_SIGN_TIMESTAMP_URL,
    [string]$SignToolPath = $env:SIGNTOOL_PATH,
    [switch]$MachineStore,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($CertificateThumbprint -notmatch '^[a-fA-F0-9]{40}$') { throw 'Specify the exact code-signing certificate SHA-1 thumbprint (not a digest algorithm)' }
if (-not $SignToolPath) {
    $sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin'
    $SignToolPath = Get-ChildItem -LiteralPath $sdkRoot -Directory |
        Where-Object Name -Match '^\d+\.\d+\.\d+\.\d+$' |
        Sort-Object { [version]$_.Name } -Descending |
        ForEach-Object { Join-Path $_.FullName 'x64/signtool.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $SignToolPath -or -not (Test-Path -LiteralPath $SignToolPath)) { throw 'Windows SDK SignTool is required' }
$artifact = (Resolve-Path -LiteralPath $Path).Path
if (-not $VerifyOnly) {
    $timestamp = $null
    if (-not [Uri]::TryCreate($TimestampUrl, [UriKind]::Absolute, [ref]$timestamp) -or $timestamp.Scheme -ne 'https') { throw 'Set a trusted RFC3161 HTTPS timestamp URL' }
    $signArgs = @('sign', '/sha1', $CertificateThumbprint, '/s', 'My', '/fd', 'SHA256', '/tr', $TimestampUrl, '/td', 'SHA256')
    if ($MachineStore) { $signArgs += '/sm' }
    & $SignToolPath @signArgs $artifact
    if ($LASTEXITCODE -ne 0) { throw 'Signing/timestamping failed' }
}
& $SignToolPath verify /pa /all /tw $artifact
if ($LASTEXITCODE -ne 0) { throw 'Authenticode verification failed or returned a warning' }
$signature = Get-AuthenticodeSignature -LiteralPath $artifact
if ($signature.Status -ne 'Valid' -or $null -eq $signature.TimeStamperCertificate -or
    $signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint) {
    throw 'Valid expected publisher and trusted timestamp are both required'
}
