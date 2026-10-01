"""Convert the legacy username,hwid,expiry CSV into signed licenses."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import io
import os
from pathlib import Path
import sys
import tempfile

from cryptography.hazmat.primitives.asymmetric import rsa

if __package__ in (None, ""):
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)

from issue_license import (
    LicenseIssueError,
    issue_license_until,
    load_private_key,
    normalize_hwid,
    resolve_private_key_password,
)
from license_admin.limits import MAX_LICENSE_FEED_BYTES


@dataclass(frozen=True, slots=True)
class MigrationResult:
    csv_text: str
    issued_count: int
    skipped_expired_count: int


def _parse_expiry(value: str, row_number: int) -> date:
    for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    raise LicenseIssueError(
        f"Legacy row {row_number} has an invalid expiry; use MM/DD/YYYY or YYYY-MM-DD."
    )


def migrate_legacy_csv(
    csv_text: str,
    private_key: rsa.RSAPrivateKey,
    *,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> MigrationResult:
    """Sign every active legacy row while preserving its end-of-day expiry."""
    if len(csv_text.encode("utf-8")) > MAX_LICENSE_FEED_BYTES:
        raise LicenseIssueError("The legacy license CSV is too large.")
    issued_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seen_hwids: set[str] = set()
    signed_rows: list[tuple[str, str]] = []
    skipped_expired = 0

    try:
        rows = csv.reader(
            io.StringIO(csv_text.lstrip("\ufeff"), newline=""),
            strict=True,
        )
        for row_number, row in enumerate(rows, start=1):
            if not row or all(not field.strip() for field in row):
                continue
            if len(row) >= 3 and (
                row[0].strip().casefold() in {"username", "user", "name"}
                and row[1].strip().casefold() == "hwid"
            ):
                continue
            if len(row) < 3:
                raise LicenseIssueError(
                    f"Legacy row {row_number} must contain username, HWID, and expiry."
                )

            username = row[0].strip()
            hwid = normalize_hwid(row[1])
            if hwid in seen_hwids:
                raise LicenseIssueError(
                    f"Legacy CSV contains duplicate HWID at row {row_number}."
                )
            seen_hwids.add(hwid)
            expires_on = _parse_expiry(row[2], row_number)
            expires_at = datetime.combine(
                expires_on,
                time(23, 59, 59),
                tzinfo=timezone.utc,
            )
            if expires_at <= issued_at:
                skipped_expired += 1
                continue
            token = issue_license_until(
                private_key,
                username=username,
                hwid=hwid,
                expires_at=expires_at,
                issuer=issuer,
                audience=audience,
                now=issued_at,
            )
            signed_rows.append((hwid, token))
    except csv.Error as exc:
        raise LicenseIssueError("The legacy license list is not valid CSV.") from exc

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("hwid", "token"))
    writer.writerows(signed_rows)
    return MigrationResult(
        csv_text=output.getvalue(),
        issued_count=len(signed_rows),
        skipped_expired_count=skipped_expired,
    )


def _write_atomic(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise LicenseIssueError(
            f"Output file already exists: {path}. Pass --force to replace it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
        text=True,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(content, encoding="utf-8", newline="")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert legacy licenses to a signed CSV.",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    key_default = os.getenv("LICENSE_PRIVATE_KEY")
    issuer_default = os.getenv("LICENSE_ISSUER")
    audience_default = os.getenv("LICENSE_AUDIENCE")
    parser.add_argument(
        "--key",
        type=Path,
        default=Path(key_default) if key_default else None,
        required=key_default is None,
    )
    parser.add_argument(
        "--issuer",
        default=issuer_default,
        required=issuer_default is None,
    )
    parser.add_argument(
        "--audience",
        default=audience_default,
        required=audience_default is None,
    )
    parser.add_argument("--password-env")
    parser.add_argument("--ask-password", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        if args.input.resolve() == args.output.resolve():
            raise LicenseIssueError("Input and output files must be different.")
        private_key = load_private_key(
            args.key,
            resolve_private_key_password(
                args.password_env,
                args.ask_password,
            ),
        )
        result = migrate_legacy_csv(
            args.input.read_text(encoding="utf-8-sig"),
            private_key,
            issuer=args.issuer,
            audience=args.audience,
        )
        _write_atomic(args.output, result.csv_text, overwrite=args.force)
    except (LicenseIssueError, OSError, UnicodeError) as exc:
        parser.error(str(exc))

    print(
        f"Issued {result.issued_count} signed license(s); "
        f"skipped {result.skipped_expired_count} expired row(s)."
    )


if __name__ == "__main__":
    main()
