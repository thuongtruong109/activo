# Windows release, update and rollback

Release target: Windows 10 1809 / Windows 11, x64, CPython 3.12.10.
Application version is defined once in `license_admin/version.py`. EXE resources,
About, QApplication and installer must agree. Review interpreter security updates
when changing the release toolchain; a dependency lock does not establish that a
runtime is free of vulnerabilities.

## Build a candidate

Use uv 0.11.27 and the locked Inno Setup 6.7.3 compiler. Run from the repository:

```powershell
python -m pip install --require-hashes -r requirements-bootstrap.windows.txt
uv venv .venv-release --python 3.12.10
uv pip sync pylock.windows.toml --python .venv-release/Scripts/python.exe --require-hashes --only-binary :all:
./tools/release/bootstrap-inno.ps1
./tools/release/windows.ps1 -Unsigned
```

Unsigned candidates are for development/testing. Do not publish them as production
releases. Output is a new `dist/releases/<version>` directory. It includes EXE,
installer, portable ZIP, SHA256SUMS, CycloneDX 1.6 SBOM, third-party notices,
lockfile and verification reports. Hashes are generated after signing and packaging.
Build-time PATH is isolated to Windows and the locked interpreter. A native-binary
hash inventory rejects DLLs accidentally taken from unrelated tools outside the
release environment/interpreter (for example, Poppler's incompatible ICU).
`LicenseAdmin.exe --self-test-output <absolute-json-path>` checks the packaged Qt,
local 16/24/32/48/64/128/256px icons, application version and RSA crypto offline.

Dependency inputs are `requirements.in` and `requirements-build.in`. To deliberately
update locks, run `tools/release/lock.ps1` and review all version/hash changes.
`pylock.windows.toml` is the PEP 751 release lock. `requirements-build.windows.txt`
is its pip compatibility export. Runtime-only `requirements.txt` also pins
transitive dependencies and hashes, including Linux wheels for Docker.
The lock reproduces dependency inputs; signed PE/installer bytes and timestamps
are not promised to be bit-for-bit identical across machines.

## Sign and verify

Provision a publicly trusted code-signing certificate with its private key in the
Windows certificate store, preferably backed by the issuer's supported hardware
or signing service. Never commit/export the private key into the repository.
Set the exact certificate thumbprint and an issuer-approved RFC3161 HTTPS endpoint:

```powershell
$env:CODE_SIGN_CERT_SHA1 = '<certificate thumbprint>'
$env:CODE_SIGN_TIMESTAMP_URL = 'https://<trusted-timestamp-service>'
./tools/release/windows.ps1
```

The SHA-1 thumbprint selects the certificate; file and timestamp digests are SHA-256.
Production builds require a clean, committed source tree. Development reports
explicitly record when the source is dirty; they are not immutable releases.
`sign.ps1` uses `/fd SHA256 /tr <url> /td SHA256`, then `verify /pa /all /tw` and
requires `Get-AuthenticodeSignature` to report Valid, the expected publisher and
a timestamp certificate. Inno signs setup **and its embedded uninstaller** using
the same verifier. Missing credentials, signing errors or warnings stop production
builds. Run verification on a clean Windows machine too; locally trusted test
certificates do not establish public trust.

Sources: [SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool),
[Authenticode timestamps](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures),
[pylock specification](https://packaging.python.org/en/latest/specifications/pylock-toml/).

## Install and update

The per-user installer uses `%LOCALAPPDATA%\Programs\Activo\LicenseAdmin` and a
stable uninstall identity. It does not need administrator rights. Start-menu
shortcuts use the local EXE icon and the application's stable AppUserModelID.
The application does not fetch its brand logo/icon from Icons8 at runtime.

Updates are explicit: download the approved signed installer, compare its SHA-256
against the published checksum, verify Authenticode, close License Admin and run
the installer. There is no automatic downloader or background updater.
Project data stays at `%LOCALAPPDATA%\Activo\LicenseAdmin\projects` (or the explicit
`ACTIVO_PROJECTS_ROOT`); installer/uninstaller never delete or replace that data,
DPAPI keys, revocation history or QSettings.

## Rollback

Keep the previous signed installer and an offline encrypted backup of project data
before updating. Ordinary downgrade is blocked. After checking that the older
application supports the current project/feed schemas, run the retained installer:

```powershell
./LicenseAdmin-<previous-version>-windows-x64-setup.exe /ALLOWDOWNGRADE=1
```

This replaces program files only. Never restore an older revocation/feed revision
store as part of rollback. DPAPI keys must remain under the same Windows identity.
If schema compatibility is uncertain, stop and repair/migrate with a compatible
version. Backups are recovery material, not permission to revive revoked licenses.

## Validation and publication gate

`tools/release/test-lifecycle.ps1` runs clean install, installer version upgrade,
blocked downgrade, explicit rollback and uninstall under a unique test AppId.
It checks payload hashes, runtime probe and data preservation. Its upgrade fixture
changes installer version but retains the current payload; additionally test a real
previous-to-current binary upgrade on a disposable Windows VM before production.
Do not run destructive installer tests against a real user installation.

CI tests/builds unsigned PR candidates on Windows, then runs the lifecycle checks.
Manual production builds, selected on an existing `v<version>` tag, use a dedicated Windows signing runner and protected
`windows-release` environment; release assets are attached to a draft only after
all gates pass. Configure that runner/certificate and review the draft before publishing.
Configure required environment reviewers and restrict signing runners to trusted
release tags (never PR code). The manual workflow additionally requires an explicit
attestation of clean-VM historical upgrade/rollback and license review. The scripts
do not claim that the synthetic installer fixture establishes schema compatibility.

The SBOM identifies locked wheels (including excluded build tools), CPython, Qt
and cryptography's bundled OpenSSL. It records its scope explicitly; a complete
native-library SBOM requires reviewing PyInstaller analysis and Qt's own SBOM.
Review Qt/PySide LGPL/GPL/commercial terms, bundled native libraries, Icons8 rights
and the notices before release. Review the Inno Setup commercial-use terms and
the builder's license too (the unlicensed compiler labels itself non-commercial).
Generated notices do not prove legal compliance.
