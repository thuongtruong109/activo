"""Validation and atomic import of per-project RSA key pairs."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.secret_protection import (
    is_protected_secret,
    protect_secret,
    unprotect_secret,
)
from license_admin.windows_security import restrict_to_current_user


MAX_KEY_FILE_BYTES = 64 * 1024
MIN_RSA_KEY_SIZE = 2_048
PRIVATE_KEY_FILENAME = "private.key"
LEGACY_PRIVATE_KEY_FILENAME = "private.pem"
PUBLIC_KEY_FILENAME = "public.pem"


class KeyPasswordRequiredError(LicenseIssueError):
    """Raised when an encrypted private key needs a password."""


@dataclass(frozen=True, slots=True)
class KeyPairInfo:
    fingerprint: str
    key_size: int
    private_key_encrypted: bool
    private_key_os_protected: bool = False

    @property
    def short_fingerprint(self) -> str:
        return self.fingerprint[:16]


@dataclass(frozen=True, slots=True)
class ImportedKeyPair:
    private_key_path: Path
    public_key_path: Path
    info: KeyPairInfo


def _read_key_file(path: Path, label: str) -> bytes:
    try:
        with path.open("rb") as source:
            contents = source.read(MAX_KEY_FILE_BYTES + 1)
        if not contents or len(contents) > MAX_KEY_FILE_BYTES:
            raise LicenseIssueError(
                f"{label} must contain between 1 and {MAX_KEY_FILE_BYTES} bytes."
            )
        return contents
    except LicenseIssueError:
        raise
    except OSError as exc:
        raise LicenseIssueError(f"Unable to read {label} {path}: {exc}") from exc


def _read_private_key_file(path: Path) -> tuple[bytes, bool]:
    stored = _read_key_file(path, "private key")
    protected = is_protected_secret(stored)
    return unprotect_secret(stored), protected


def _load_private_key(
    private_pem: bytes,
    password: bytes | None,
) -> tuple[rsa.RSAPrivateKey, bool]:
    encrypted = b"ENCRYPTED" in private_pem[:2_048].upper()
    if encrypted and password is None:
        raise KeyPasswordRequiredError("The private key is encrypted.")
    try:
        loaded = serialization.load_pem_private_key(private_pem, password=password)
    except (TypeError, ValueError) as exc:
        raise LicenseIssueError(
            "The private key password is incorrect or the PEM is invalid."
        ) from exc
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise LicenseIssueError("The private key must be an RSA private key.")
    if loaded.key_size < MIN_RSA_KEY_SIZE:
        raise LicenseIssueError(
            f"The RSA private key must be at least {MIN_RSA_KEY_SIZE} bits."
        )
    return loaded, encrypted


def _load_public_key(public_pem: bytes) -> rsa.RSAPublicKey:
    try:
        loaded = serialization.load_pem_public_key(public_pem)
    except (TypeError, ValueError) as exc:
        raise LicenseIssueError("The public key PEM is invalid.") from exc
    if not isinstance(loaded, rsa.RSAPublicKey):
        raise LicenseIssueError("The public key must be an RSA public key.")
    if loaded.key_size < MIN_RSA_KEY_SIZE:
        raise LicenseIssueError(
            f"The RSA public key must be at least {MIN_RSA_KEY_SIZE} bits."
        )
    return loaded


def inspect_key_pair(
    private_key_path: Path,
    public_key_path: Path,
    *,
    password: bytes | None = None,
) -> KeyPairInfo:
    """Validate two PEM files and prove that they form one RSA key pair."""
    private_pem, os_protected = _read_private_key_file(private_key_path)
    public_pem = _read_key_file(public_key_path, "public key")
    return replace(
        _inspect_key_pair_material(private_pem, public_pem, password),
        private_key_os_protected=os_protected,
    )


def load_private_key_file(
    private_key_path: Path,
    password: bytes | None = None,
) -> rsa.RSAPrivateKey:
    """Decrypt an installed DPAPI envelope and load its RSA private key."""
    private_pem, _os_protected = _read_private_key_file(private_key_path)
    private_key, _pem_encrypted = _load_private_key(private_pem, password)
    return private_key


def _inspect_key_pair_material(
    private_pem: bytes,
    public_pem: bytes,
    password: bytes | None,
) -> KeyPairInfo:
    private_key, encrypted = _load_private_key(private_pem, password)
    public_key = _load_public_key(public_pem)
    private_public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if private_public_der != public_der:
        raise LicenseIssueError(
            "The selected private key and public key do not form a matching pair."
        )
    return KeyPairInfo(
        fingerprint=hashlib.sha256(public_der).hexdigest(),
        key_size=public_key.key_size,
        private_key_encrypted=encrypted,
    )


def public_key_fingerprint(public_key_path: Path) -> str:
    public_pem = _read_key_file(public_key_path, "public key")
    public_key = _load_public_key(public_pem)
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(public_der).hexdigest()


def _temporary_path(directory: Path, prefix: str) -> Path:
    descriptor, filename = tempfile.mkstemp(
        prefix=prefix,
        suffix=".tmp",
        dir=str(directory),
    )
    os.close(descriptor)
    return Path(filename)


def _restore_backup(target: Path, backup: Path | None) -> None:
    target.unlink(missing_ok=True)
    if backup is not None and backup.exists():
        os.replace(backup, target)


def _unlink_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def import_key_pair(
    private_key_path: Path,
    public_key_path: Path,
    destination_directory: Path,
    *,
    password: bytes | None = None,
    overwrite: bool = False,
) -> ImportedKeyPair:
    """Validate and atomically copy a pair into one project directory."""
    private_pem, source_os_protected = _read_private_key_file(private_key_path)
    public_pem = _read_key_file(public_key_path, "public key")
    info = replace(
        _inspect_key_pair_material(private_pem, public_pem, password),
        private_key_os_protected=source_os_protected,
    )
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
        restrict_to_current_user(destination_directory)
    except OSError as exc:
        raise LicenseIssueError(
            f"Unable to create project directory {destination_directory}: {exc}"
        ) from exc

    private_target = destination_directory / PRIVATE_KEY_FILENAME
    public_target = destination_directory / PUBLIC_KEY_FILENAME
    same_private = private_key_path.resolve(strict=False) == private_target.resolve(
        strict=False
    )
    same_public = public_key_path.resolve(strict=False) == public_target.resolve(
        strict=False
    )
    if same_private and same_public:
        restrict_to_current_user(private_target)
        return ImportedKeyPair(private_target, public_target, info)
    existing = [path for path in (private_target, public_target) if path.exists()]
    if existing and not overwrite:
        raise LicenseIssueError(
            "The project already contains key files. Confirm replacement before importing."
        )

    private_temp: Path | None = None
    public_temp: Path | None = None
    private_backup: Path | None = None
    public_backup: Path | None = None
    private_installed = False
    public_installed = False
    try:
        private_temp = _temporary_path(destination_directory, ".private.key.")
        public_temp = _temporary_path(destination_directory, ".public.pem.")
        protected_private = protect_secret(private_pem)
        with private_temp.open("wb") as private_stream:
            private_stream.write(protected_private)
            private_stream.flush()
            os.fsync(private_stream.fileno())
        with public_temp.open("wb") as public_stream:
            public_stream.write(public_pem)
            public_stream.flush()
            os.fsync(public_stream.fileno())
        restrict_to_current_user(private_temp)

        if private_target.exists():
            private_backup = _temporary_path(destination_directory, ".private.backup.")
            private_backup.unlink()
            os.replace(private_target, private_backup)
        if public_target.exists():
            public_backup = _temporary_path(destination_directory, ".public.backup.")
            public_backup.unlink()
            os.replace(public_target, public_backup)

        os.replace(private_temp, private_target)
        private_installed = True
        restrict_to_current_user(private_target)
        os.replace(public_temp, public_target)
        public_installed = True
    except (OSError, LicenseIssueError) as exc:
        rollback_errors: list[str] = []
        for target, backup, installed in (
            (private_target, private_backup, private_installed),
            (public_target, public_backup, public_installed),
        ):
            if backup is None and not installed:
                continue
            try:
                _restore_backup(target, backup)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        detail = (
            f" Rollback also failed: {'; '.join(rollback_errors)}"
            if rollback_errors
            else ""
        )
        raise LicenseIssueError(f"Unable to import the key pair: {exc}.{detail}") from exc
    else:
        for backup in (private_backup, public_backup):
            # The imported pair is already installed. A stale hidden backup is safer
            # than treating cleanup as a failed import and rolling back.
            _unlink_quietly(backup)
    finally:
        _unlink_quietly(private_temp)
        _unlink_quietly(public_temp)

    return ImportedKeyPair(
        private_target,
        public_target,
        replace(
            info,
            private_key_os_protected=is_protected_secret(protected_private),
        ),
    )


def migrate_legacy_private_key(
    legacy_path: Path,
    destination_path: Path,
    *,
    remove_legacy: bool = True,
) -> bool:
    """Copy a legacy PEM into the current-user secret envelope, then remove it."""
    if not legacy_path.is_file() or destination_path.exists():
        return False
    private_pem, _already_protected = _read_private_key_file(legacy_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    restrict_to_current_user(destination_path.parent)
    temporary = _temporary_path(destination_path.parent, ".private-migration.")
    try:
        protected = protect_secret(private_pem)
        with temporary.open("wb") as stream:
            stream.write(protected)
            stream.flush()
            os.fsync(stream.fileno())
        restrict_to_current_user(temporary)
        if unprotect_secret(temporary.read_bytes()) != private_pem:
            raise LicenseIssueError("Private-key migration verification failed.")
        os.replace(temporary, destination_path)
        restrict_to_current_user(destination_path)
        # Limit the legacy file before removing the now-redundant plaintext copy.
        restrict_to_current_user(legacy_path)
        if remove_legacy:
            legacy_path.unlink()
    except Exception:
        _unlink_quietly(temporary)
        if destination_path.exists():
            _unlink_quietly(destination_path)
        raise
    return True
