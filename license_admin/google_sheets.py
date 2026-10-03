"""Small Google Sheets REST client using service-account credentials."""

from __future__ import annotations

import base64
import csv
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import requests

from issue_license import LicenseIssueError
from license_admin.domain import (
    LicenseRecord,
    records_digest,
    serialize_signed_csv,
)
from license_admin.feed_manifest import (
    DEFAULT_FRESHNESS,
    FEED_COLUMNS,
    FeedDocument,
    FeedManifest,
    FeedTombstone,
    feed_digest,
    parse_feed_csv,
    publication_content_digest,
    serialize_feed_csv,
    sign_feed,
    verify_feed,
)
from license_admin.service_account_store import load_service_account


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SYNC_SENTINEL_SCHEMA = "activo-sheet-sync-v1"
SYNC_SENTINEL_COLUMNS = ("schema", "target_sheet_id", "revision", "digest", "operation_id")


class SheetConflictError(LicenseIssueError):
    """The remote generation changed after the user reviewed it."""


@dataclass(frozen=True, slots=True)
class RemoteRevision:
    generation: int
    digest: str
    sentinel_sheet_id: int
    target_sheet_id: int
    operation_id: str = ""


@dataclass(frozen=True, slots=True)
class RemoteSnapshot:
    records: tuple[LicenseRecord, ...]
    digest: str
    revision: RemoteRevision | None
    target_sheet_id: int
    target_row_count: int
    target_column_count: int = 2
    tombstones: tuple[FeedTombstone, ...] = ()
    manifest_token: str = ""
    manifest: FeedManifest | None = None
    content_digest: str = ""

    @property
    def guard_matches_data(self) -> bool:
        return self.revision is None or self.revision.digest == self.digest

    @property
    def publication_digest(self) -> str:
        return self.content_digest or publication_content_digest(
            self.records,
            self.tombstones,
        )


@dataclass(frozen=True, slots=True)
class GoogleSheetsConfig:
    spreadsheet_id: str
    worksheet: str = "Signed"
    credentials_path: Path | None = None
    public_csv_url: str = ""

    @property
    def browser_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"


def extract_spreadsheet_id(value: str) -> str:
    candidate = value.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", candidate)
    if match is not None:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", candidate):
        return candidate
    raise LicenseIssueError("Enter a valid Google spreadsheet ID or URL.")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class GoogleSheetsClient:
    def __init__(
        self,
        config: GoogleSheetsConfig,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 30.0),
    ) -> None:
        self.config = config
        self._session = session or requests.Session()
        self._timeout = timeout
        self._access_token: str | None = None
        self._access_token_expires = datetime.min.replace(tzinfo=timezone.utc)

    def _credentials(self) -> dict[str, Any]:
        path = self.config.credentials_path
        if path is None:
            raise LicenseIssueError(
                "Choose a Google service-account JSON file in Settings first."
            )
        return load_service_account(path)

    def _token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._access_token and now < self._access_token_expires:
            return self._access_token

        credentials = self._credentials()
        token_uri = credentials.get("token_uri", "https://oauth2.googleapis.com/token")
        if not isinstance(token_uri, str) or not token_uri.startswith("https://"):
            raise LicenseIssueError("Service-account token_uri must use HTTPS.")
        try:
            key = serialization.load_pem_private_key(
                credentials["private_key"].encode("utf-8"),
                password=None,
            )
        except (TypeError, ValueError) as exc:
            raise LicenseIssueError("Service-account private key is invalid.") from exc
        if not isinstance(key, rsa.RSAPrivateKey):
            raise LicenseIssueError("Service-account private key must be RSA.")

        issued = int(now.timestamp())
        header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
        claims = _b64url(
            json.dumps(
                {
                    "iss": credentials["client_email"],
                    "scope": SHEETS_SCOPE,
                    "aud": token_uri,
                    "iat": issued,
                    "exp": issued + 3_600,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        assertion = f"{header}.{claims}.{_b64url(key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256()))}"
        try:
            response = self._session.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise LicenseIssueError(f"Google authentication failed: {exc}") from exc
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise LicenseIssueError("Google authentication returned no access token.")
        expires_in = payload.get("expires_in", 3_600)
        if not isinstance(expires_in, (int, float)):
            expires_in = 3_600
        self._access_token = access_token
        self._access_token_expires = now + timedelta(seconds=max(60, expires_in - 60))
        return access_token

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token()}"
        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
        except requests.HTTPError as exc:
            detail = ""
            try:
                error_payload = exc.response.json() if exc.response is not None else {}
                detail = error_payload.get("error", {}).get("message", "")
            except (AttributeError, ValueError):
                pass
            suffix = f": {detail}" if detail else f": {exc}"
            raise LicenseIssueError(f"Google Sheets request failed{suffix}") from exc
        except (requests.RequestException, ValueError) as exc:
            raise LicenseIssueError(f"Google Sheets request failed: {exc}") from exc

    def _values_url(self, cell_range: str) -> str:
        encoded_range = quote(cell_range, safe="")
        return (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{self.config.spreadsheet_id}/values/{encoded_range}"
        )

    @property
    def _spreadsheet_url(self) -> str:
        return (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{self.config.spreadsheet_id}"
        )

    @staticmethod
    def _quoted_title(title: str) -> str:
        return f"'{title.replace(chr(39), chr(39) * 2)}'"

    def _sentinel_title(self) -> str:
        target_hash = hashlib.sha256(
            self.config.worksheet.encode("utf-8")
        ).hexdigest()[:16]
        return f"__activo_sync_{target_hash}"

    def _sheet_properties(self) -> dict[str, tuple[int, int, int, bool]]:
        payload = self._request(
            "GET",
            self._spreadsheet_url,
            params={
                "fields": (
                    "sheets.properties("
                    "sheetId,title,hidden,gridProperties(rowCount,columnCount))"
                )
            },
        )
        sheets = payload.get("sheets", []) if isinstance(payload, dict) else []
        result: dict[str, tuple[int, int, int, bool]] = {}
        for sheet in sheets:
            properties = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
            title = properties.get("title")
            sheet_id = properties.get("sheetId")
            if not isinstance(title, str) or isinstance(sheet_id, bool) or not isinstance(
                sheet_id, int
            ):
                continue
            grid = properties.get("gridProperties", {})
            row_count = grid.get("rowCount", 1_000) if isinstance(grid, dict) else 1_000
            column_count = (
                grid.get("columnCount", 26) if isinstance(grid, dict) else 26
            )
            result[title] = (
                sheet_id,
                int(row_count),
                int(column_count),
                bool(properties.get("hidden", False)),
            )
        return result

    def _read_rows(self, title: str, cell_range: str = "A:B") -> list[list[str]]:
        a1_range = f"{self._quoted_title(title)}!{cell_range}"
        payload = self._request("GET", self._values_url(a1_range))
        rows = payload.get("values", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            raise LicenseIssueError("Google Sheets returned invalid row data.")
        normalized: list[list[str]] = []
        for row in rows:
            if not isinstance(row, list):
                raise LicenseIssueError("Google Sheets returned an invalid row.")
            normalized.append([str(value) for value in row])
        return normalized

    def _read_feed_from_title(self, title: str) -> FeedDocument:
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(
            [row[:5] for row in self._read_rows(title, "A:E")]
        )
        return parse_feed_csv(output.getvalue(), allow_legacy=True)

    def _read_records_from_title(self, title: str) -> list[LicenseRecord]:
        return list(self._read_feed_from_title(title).records)

    def read_records(self) -> list[LicenseRecord]:
        return self._read_records_from_title(self.config.worksheet)

    def _read_remote_revision(
        self,
        properties: dict[str, tuple[int, int, int, bool]],
        target_sheet_id: int,
    ) -> RemoteRevision | None:
        sentinel = properties.get(self._sentinel_title())
        if sentinel is None:
            return None
        sentinel_sheet_id, _row_count, _column_count, _hidden = sentinel
        rows = self._read_rows(self._sentinel_title(), "A1:E2")
        if len(rows) != 2 or tuple(rows[0]) != SYNC_SENTINEL_COLUMNS:
            raise LicenseIssueError("The Activo Sheet sync revision is corrupted.")
        values = rows[1]
        if len(values) != len(SYNC_SENTINEL_COLUMNS):
            raise LicenseIssueError("The Activo Sheet sync revision is incomplete.")
        schema, raw_target_id, raw_generation, digest, operation_id = values
        try:
            stored_target_id = int(raw_target_id)
            generation = int(raw_generation)
        except ValueError as exc:
            raise LicenseIssueError(
                "The Activo Sheet sync revision contains invalid numbers."
            ) from exc
        if (
            schema != SYNC_SENTINEL_SCHEMA
            or stored_target_id != target_sheet_id
            or generation < 1
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise LicenseIssueError("The Activo Sheet sync revision is invalid.")
        return RemoteRevision(
            generation=generation,
            digest=digest,
            sentinel_sheet_id=sentinel_sheet_id,
            target_sheet_id=target_sheet_id,
            operation_id=operation_id,
        )

    def read_snapshot(self) -> RemoteSnapshot:
        properties = self._sheet_properties()
        target = properties.get(self.config.worksheet)
        if target is None:
            raise LicenseIssueError(
                f"Worksheet {self.config.worksheet!r} does not exist."
            )
        target_sheet_id, target_row_count, target_column_count, _hidden = target
        feed = self._read_feed_from_title(self.config.worksheet)
        records = feed.records
        digest = (
            feed_digest(feed)
            if feed.manifest_token
            else records_digest(records)
        )
        revision = self._read_remote_revision(properties, target_sheet_id)
        return RemoteSnapshot(
            records=records,
            digest=digest,
            revision=revision,
            target_sheet_id=target_sheet_id,
            target_row_count=target_row_count,
            target_column_count=target_column_count,
            tombstones=feed.tombstones,
            manifest_token=feed.manifest_token,
            content_digest=publication_content_digest(
                feed.records,
                feed.tombstones,
            ),
        )

    @staticmethod
    def _same_revision(
        current: RemoteRevision | None,
        expected: RemoteRevision | None,
    ) -> bool:
        return current == expected

    def _assert_expected_snapshot(
        self,
        snapshot: RemoteSnapshot,
        expected_revision: RemoteRevision | None,
        expected_digest: str,
    ) -> None:
        if (
            snapshot.digest != expected_digest
            or not self._same_revision(snapshot.revision, expected_revision)
        ):
            raise SheetConflictError(
                "The Google Sheet changed after the sync preview. Review the diff again."
            )

    @staticmethod
    def _new_sheet_id(used_ids: set[int]) -> int:
        while True:
            candidate = secrets.randbelow(2_000_000_000) + 1
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate

    def _batch_update(self, requests_payload: list[dict[str, Any]]) -> Any:
        return self._request(
            "POST",
            f"{self._spreadsheet_url}:batchUpdate",
            json={"requests": requests_payload},
        )

    def _create_stage(self, sheet_id: int, title: str, row_count: int) -> None:
        self._batch_update(
            [
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": sheet_id,
                            "title": title,
                            "hidden": True,
                            "gridProperties": {
                                "rowCount": max(2, row_count),
                                "columnCount": len(FEED_COLUMNS),
                            },
                        }
                    }
                }
            ]
        )

    def _delete_sheet(self, sheet_id: int) -> None:
        self._batch_update([{"deleteSheet": {"sheetId": sheet_id}}])

    def _cleanup_stage(self, sheet_id: int, title: str) -> None:
        """Delete only the exact staging sheet owned by this operation."""
        try:
            stage = self._sheet_properties().get(title)
            if stage is not None and stage[0] == sheet_id:
                self._delete_sheet(sheet_id)
        except LicenseIssueError:
            # Cleanup is best-effort; never mask the publish error that led here.
            pass

    def _write_feed(self, title: str, feed: FeedDocument) -> None:
        values = list(
            csv.reader(io.StringIO(serialize_feed_csv(feed), newline=""), strict=True)
        )
        cell_range = f"{self._quoted_title(title)}!A1:E{len(values)}"
        self._request(
            "PUT",
            self._values_url(cell_range),
            params={"valueInputOption": "RAW"},
            json={
                "range": cell_range,
                "majorDimension": "ROWS",
                "values": values,
            },
        )

    @staticmethod
    def _sentinel_rows(
        target_sheet_id: int,
        generation: int,
        digest: str,
        operation_id: str,
    ) -> list[dict[str, Any]]:
        values = (
            SYNC_SENTINEL_COLUMNS,
            (
                SYNC_SENTINEL_SCHEMA,
                str(target_sheet_id),
                str(generation),
                digest,
                operation_id,
            ),
        )
        return [
            {
                "values": [
                    {"userEnteredValue": {"stringValue": value}} for value in row
                ]
            }
            for row in values
        ]

    def _publish_batch(
        self,
        *,
        expected: RemoteSnapshot,
        stage_sheet_id: int,
        stage_row_count: int,
        sentinel_sheet_id: int,
        generation: int,
        digest: str,
        operation_id: str,
    ) -> None:
        requests_payload: list[dict[str, Any]] = []
        if expected.revision is not None:
            requests_payload.append(
                {"deleteSheet": {"sheetId": expected.revision.sentinel_sheet_id}}
            )
        requests_payload.extend(
            [
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": sentinel_sheet_id,
                            "title": self._sentinel_title(),
                            "hidden": True,
                            "gridProperties": {"rowCount": 2, "columnCount": 5},
                        }
                    }
                },
                {
                    "updateCells": {
                        "start": {
                            "sheetId": sentinel_sheet_id,
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rows": self._sentinel_rows(
                            expected.target_sheet_id,
                            generation,
                            digest,
                            operation_id,
                        ),
                        "fields": "userEnteredValue",
                    }
                },
            ]
        )
        if (
            expected.target_row_count < stage_row_count
            or expected.target_column_count < len(FEED_COLUMNS)
        ):
            requests_payload.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": expected.target_sheet_id,
                            "gridProperties": {
                                "rowCount": max(
                                    expected.target_row_count, stage_row_count
                                ),
                                "columnCount": max(
                                    expected.target_column_count,
                                    len(FEED_COLUMNS),
                                ),
                            },
                        },
                        "fields": (
                            "gridProperties.rowCount,"
                            "gridProperties.columnCount"
                        ),
                    }
                }
            )
        requests_payload.extend(
            [
                {
                    "updateCells": {
                        "range": {
                            "sheetId": expected.target_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max(expected.target_row_count, stage_row_count),
                            "startColumnIndex": 0,
                            "endColumnIndex": len(FEED_COLUMNS),
                        },
                        "rows": [],
                        "fields": "userEnteredValue",
                    }
                },
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": stage_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": stage_row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(FEED_COLUMNS),
                        },
                        "destination": {
                            "sheetId": expected.target_sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": stage_row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(FEED_COLUMNS),
                        },
                        "pasteType": "PASTE_VALUES",
                        "pasteOrientation": "NORMAL",
                    }
                },
                {"deleteSheet": {"sheetId": stage_sheet_id}},
            ]
        )
        self._batch_update(requests_payload)

    @staticmethod
    def _is_verified_publish(
        snapshot: RemoteSnapshot,
        *,
        operation_id: str,
        generation: int,
        sentinel_sheet_id: int,
        target_sheet_id: int,
        digest: str,
    ) -> bool:
        revision = snapshot.revision
        return (
            revision is not None
            and revision.operation_id == operation_id
            and revision.generation == generation
            and revision.sentinel_sheet_id == sentinel_sheet_id
            and revision.target_sheet_id == target_sheet_id
            and snapshot.target_sheet_id == target_sheet_id
            and snapshot.digest == digest
            and snapshot.guard_matches_data
            and snapshot.manifest is not None
            and snapshot.manifest.revision == generation
        )

    def publish_records(
        self,
        records: list[LicenseRecord] | tuple[LicenseRecord, ...],
        *,
        tombstones: tuple[FeedTombstone, ...],
        signing_key: rsa.RSAPrivateKey,
        issuer: str,
        audience: str,
        expected_revision: RemoteRevision | None,
        expected_digest: str,
        freshness: timedelta = DEFAULT_FRESHNESS,
        minimum_revision: int = 0,
    ) -> RemoteSnapshot:
        """Sign, stage, atomically compare-and-swap, and verify one feed."""
        ordered = tuple(
            sorted(records, key=lambda item: (item.username.casefold(), item.hwid))
        )
        reviewed = self.read_snapshot()
        self._assert_expected_snapshot(reviewed, expected_revision, expected_digest)
        next_remote_revision = (
            expected_revision.generation + 1
            if expected_revision is not None
            else 1
        )
        generation = max(next_remote_revision, minimum_revision + 1)
        desired_feed = sign_feed(
            ordered,
            tombstones,
            signing_key,
            revision=generation,
            issuer=issuer,
            audience=audience,
            freshness=freshness,
        )
        desired_digest = feed_digest(desired_feed)
        public_pem = signing_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        def verified_snapshot(snapshot: RemoteSnapshot) -> RemoteSnapshot:
            verified_feed = verify_feed(
                FeedDocument(
                    snapshot.records,
                    snapshot.tombstones,
                    snapshot.manifest_token,
                ),
                public_pem,
                expected_issuer=issuer,
                expected_audience=audience,
                minimum_revision=generation,
            )
            manifest = verified_feed.manifest
            if manifest is None or manifest.revision != generation:
                raise LicenseIssueError(
                    "Google Sheets returned the wrong signed manifest revision."
                )
            return replace(snapshot, manifest=manifest)

        properties = self._sheet_properties()
        used_ids = {
            sheet_id
            for sheet_id, _rows, _columns, _hidden in properties.values()
        }
        stage_sheet_id = self._new_sheet_id(used_ids)
        sentinel_sheet_id = self._new_sheet_id(used_ids)
        operation_id = uuid4().hex
        stage_title = f"__activo_stage_{operation_id}"
        stage_cleanup_needed = True
        try:
            stage_row_count = len(ordered) + len(tombstones) + 2
            self._create_stage(stage_sheet_id, stage_title, stage_row_count)
            self._write_feed(stage_title, desired_feed)
            try:
                staged = self._read_feed_from_title(stage_title)
                verify_feed(
                    staged,
                    public_pem,
                    expected_issuer=issuer,
                    expected_audience=audience,
                    minimum_revision=generation,
                )
                staged_matches = feed_digest(staged) == desired_digest
            except LicenseIssueError as exc:
                raise LicenseIssueError(
                    "Google Sheets staging verification failed; published data was untouched."
                ) from exc
            if not staged_matches:
                raise LicenseIssueError(
                    "Google Sheets staging verification failed; published data was untouched."
                )

            current = self.read_snapshot()
            self._assert_expected_snapshot(current, expected_revision, expected_digest)
            try:
                self._publish_batch(
                    expected=current,
                    stage_sheet_id=stage_sheet_id,
                    stage_row_count=stage_row_count,
                    sentinel_sheet_id=sentinel_sheet_id,
                    generation=generation,
                    digest=desired_digest,
                    operation_id=operation_id,
                )
                stage_cleanup_needed = False
            except LicenseIssueError as publish_error:
                try:
                    reconciled = verified_snapshot(self.read_snapshot())
                except LicenseIssueError:
                    raise publish_error
                if self._is_verified_publish(
                    reconciled,
                    operation_id=operation_id,
                    generation=generation,
                    sentinel_sheet_id=sentinel_sheet_id,
                    target_sheet_id=current.target_sheet_id,
                    digest=desired_digest,
                ):
                    stage_cleanup_needed = False
                    return reconciled
                if not self._same_revision(reconciled.revision, expected_revision):
                    raise SheetConflictError(
                        "Another writer published to the Google Sheet first."
                    ) from publish_error
                raise

            try:
                verified = verified_snapshot(self.read_snapshot())
            except LicenseIssueError as exc:
                raise LicenseIssueError(
                    "Google Sheets read-back verification failed; sync was not confirmed."
                ) from exc
            if not self._is_verified_publish(
                verified,
                operation_id=operation_id,
                generation=generation,
                sentinel_sheet_id=sentinel_sheet_id,
                target_sheet_id=current.target_sheet_id,
                digest=desired_digest,
            ):
                raise LicenseIssueError(
                    "Google Sheets read-back verification failed; sync was not confirmed."
                )
            return verified
        finally:
            if stage_cleanup_needed:
                self._cleanup_stage(stage_sheet_id, stage_title)

    def _worksheet_properties(self) -> tuple[int, int]:
        properties = self._sheet_properties().get(self.config.worksheet)
        if properties is not None:
            sheet_id, row_count, _column_count, _hidden = properties
            return sheet_id, row_count
        raise LicenseIssueError(
            f"Worksheet {self.config.worksheet!r} does not exist."
        )

    def format_worksheet(self) -> None:
        sheet_id, row_count = self._worksheet_properties()
        grid_range = {
            "sheetId": sheet_id,
            "startColumnIndex": 0,
            "endColumnIndex": len(FEED_COLUMNS),
        }
        header_range = dict(grid_range, startRowIndex=0, endRowIndex=1)
        body_range = dict(grid_range, startRowIndex=1, endRowIndex=max(2, row_count))
        requests_payload: list[dict[str, Any]] = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "repeatCell": {
                    "range": header_range,
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.92, "green": 0.34, "blue": 0.05},
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": body_range,
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "TEXT", "pattern": "@"},
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "CLIP",
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,verticalAlignment,wrapStrategy)",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 440},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "properties": {"pixelSize": 600},
                    "fields": "pixelSize",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max(2, row_count),
                            "startColumnIndex": 0,
                            "endColumnIndex": len(FEED_COLUMNS),
                        }
                    }
                }
            },
        ]
        self._batch_update(requests_payload)


def download_public_feed(url: str) -> FeedDocument:
    if not url.strip().startswith("https://"):
        raise LicenseIssueError("Public CSV URL must use HTTPS.")
    try:
        response = requests.get(url.strip(), timeout=(5.0, 30.0))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LicenseIssueError(f"Unable to download the published CSV: {exc}") from exc
    return parse_feed_csv(response.text)


def download_public_records(url: str) -> list[LicenseRecord]:
    """Compatibility helper; secure clients should verify the returned feed."""
    return list(download_public_feed(url).records)


def export_csv_text(records: list[LicenseRecord]) -> str:
    return serialize_signed_csv(records)
