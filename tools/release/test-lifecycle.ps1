param(
    [Parameter(Mandatory)][string]$ReleaseDir,
    [string]$Iscc = 'build/tools/inno/ISCC.exe'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot/process.ps1"
. "$PSScriptRoot/inno.ps1"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repoRoot
try {
    $payload = (Resolve-Path -LiteralPath $ReleaseDir).Path
    $Iscc = (Resolve-Path -LiteralPath $Iscc).Path
    Assert-InnoToolchain $Iscc
    $id = 'Activo.LicenseAdmin.Test.' + [Guid]::NewGuid().ToString('N')
    $testRoot = Join-Path $repoRoot ('build/lifecycle/' + $id)
    $installPath = Join-Path $testRoot 'program'
    $dataPath = Join-Path $testRoot 'projects'
    New-Item -ItemType Directory -Path $testRoot, $dataPath | Out-Null
    # Only isolated, synthetic data. Never write/delete actual user projects.
    $sentinel = Join-Path $dataPath 'data-preservation-sentinel.txt'
    'Synthetic key/feed/revision backup; do not remove during an update.' | Set-Content -LiteralPath $sentinel -Encoding utf8
    $sentinelHash = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
    $payloadHash = (Get-FileHash -LiteralPath (Join-Path $payload 'LicenseAdmin.exe') -Algorithm SHA256).Hash
    $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryView]::Registry64)
    $uninstallKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\${id}_is1"
    $previousProjectsRoot = $env:ACTIVO_PROJECTS_ROOT
    $env:ACTIVO_PROJECTS_ROOT = $dataPath
    $steps = [System.Collections.Generic.List[string]]::new()
    $uninstalled = $false

    function Assert-InstalledVersion([string]$Expected) {
        $key = $registry.OpenSubKey($uninstallKey)
        try {
            if ($null -eq $key -or $key.GetValue('DisplayVersion') -ne $Expected) { throw "Incorrect installed version; expected $Expected" }
        } finally { if ($null -ne $key) { $key.Dispose() } }
        if ((Get-FileHash -LiteralPath (Join-Path $installPath 'LicenseAdmin.exe') -Algorithm SHA256).Hash -ne $payloadHash) { throw 'Installed payload hash changed' }
        if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) { throw 'Project data was changed' }
    }
    function Install-Fixture([string]$Version, [bool]$AllowDowngrade = $false) {
        $installerArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOICONS',
            ('/DIR="' + $installPath + '"'), ('/LOG="' + (Join-Path $testRoot ($Version + '-install-' + $steps.Count + '.log')) + '"'))
        if ($AllowDowngrade) { $installerArgs += '/ALLOWDOWNGRADE=1' }
        return Invoke-ReleaseProcess -FilePath (Join-Path $testRoot "LicenseAdmin-$Version-windows-x64-setup.exe") -Arguments $installerArgs
    }
    try {
        # Two installer versions exercise policy, not historical application/schema compatibility.
        foreach ($version in @('1.0.0', '1.0.1')) {
            & $Iscc "/DPayloadDir=$payload" "/DReleaseVersion=$version" "/DOutputDir=$testRoot" "/DInstallerId=$id" 'packaging/windows/LicenseAdmin.iss'
            if ($LASTEXITCODE -ne 0) { throw 'Lifecycle fixture compilation failed' }
        }
        if ((Install-Fixture '1.0.0') -ne 0) { throw 'Clean install failed' }
        Assert-InstalledVersion '1.0.0'
        Invoke-ReleaseProbe -Executable (Join-Path $installPath 'LicenseAdmin.exe') -Report (Join-Path $testRoot 'installed-runtime.json')
        $steps.Add('clean-install-and-runtime')
        if ((Install-Fixture '1.0.1') -ne 0) { throw 'Upgrade failed' }
        Assert-InstalledVersion '1.0.1'
        $steps.Add('upgrade')
        if ((Install-Fixture '1.0.0') -eq 0) { throw 'Implicit downgrade was not blocked' }
        Assert-InstalledVersion '1.0.1'
        $steps.Add('downgrade-blocked')
        if ((Install-Fixture '1.0.0' $true) -ne 0) { throw 'Explicit rollback failed' }
        Assert-InstalledVersion '1.0.0'
        $steps.Add('explicit-rollback')
        $code = Invoke-ReleaseProcess -FilePath (Join-Path $installPath 'unins000.exe') -Arguments @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
        if ($code -ne 0 -or (Test-Path -LiteralPath (Join-Path $installPath 'LicenseAdmin.exe'))) { throw 'Uninstall failed' }
        $key = $registry.OpenSubKey($uninstallKey)
        if ($null -ne $key) { $key.Dispose(); throw 'Uninstall registration remained' }
        if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) { throw 'Uninstall changed project data' }
        $uninstalled = $true
        $steps.Add('uninstall-and-data-preservation')
        @{ ok = $true; steps = @($steps); scope = 'Isolated installer-version fixtures with the current binary; real historical upgrade still requires a disposable VM' } |
            ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $payload 'lifecycle-report.json') -Encoding utf8
    } finally {
        $env:ACTIVO_PROJECTS_ROOT = $previousProjectsRoot
        $registry.Dispose()
        # This uninstaller belongs only to the GUID-named test directory/AppId above.
        $uninstaller = Join-Path $installPath 'unins000.exe'
        if (-not $uninstalled -and (Test-Path -LiteralPath $uninstaller)) {
            $code = Invoke-ReleaseProcess -FilePath $uninstaller -Arguments @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
            if ($code -ne 0) { throw "Test fixture cleanup failed ($code): $installPath" }
        }
    }
    Write-Output "Lifecycle checks passed; isolated logs: $testRoot"
} finally { Pop-Location }
