"""Small Google Sheets REST client using service-account credentials."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import requests

from issue_license import LicenseIssueError
from license_admin.domain import (
    LicenseRecord,
    parse_signed_csv,
    serialize_signed_csv,
)


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


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
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LicenseIssueError(f"Unable to read service-account JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LicenseIssueError("Service-account JSON must contain an object.")
        for field in ("client_email", "private_key"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise LicenseIssueError(
                    f"Service-account JSON is missing {field!r}."
                )
        return data

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

    def read_records(self) -> list[LicenseRecord]:
        cell_range = f"'{self.config.worksheet}'!A:B"
        payload = self._request("GET", self._values_url(cell_range))
        rows = payload.get("values", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            raise LicenseIssueError("Google Sheets returned invalid row data.")
        csv_rows: list[list[str]] = []
        for row in rows:
            if not isinstance(row, list):
                raise LicenseIssueError("Google Sheets returned an invalid row.")
            csv_rows.append([str(value) for value in row[:2]])
        import io
        import csv

        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(csv_rows)
        return parse_signed_csv(output.getvalue())

    def replace_records(
        self,
        records: list[LicenseRecord],
        *,
        existing_records: list[LicenseRecord] | None = None,
    ) -> None:
        current = self.read_records() if existing_records is None else existing_records
        ordered = sorted(records, key=lambda item: (item.username.casefold(), item.hwid))
        values = [["hwid", "token"]] + [[item.hwid, item.token] for item in ordered]
        start_range = f"'{self.config.worksheet}'!A1:B{len(values)}"
        self._request(
            "PUT",
            self._values_url(start_range),
            params={"valueInputOption": "RAW"},
            json={"range": start_range, "majorDimension": "ROWS", "values": values},
        )
        old_row_count = len(current) + 1
        if old_row_count > len(values):
            trailing_range = (
                f"'{self.config.worksheet}'!A{len(values) + 1}:B{old_row_count}"
            )
            self._request("POST", f"{self._values_url(trailing_range)}:clear", json={})

    def _worksheet_properties(self) -> tuple[int, int]:
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{self.config.spreadsheet_id}"
        )
        payload = self._request(
            "GET",
            url,
            params={"fields": "sheets.properties(sheetId,title,gridProperties.rowCount)"},
        )
        for sheet in payload.get("sheets", []):
            properties = sheet.get("properties", {})
            if properties.get("title") == self.config.worksheet:
                return int(properties["sheetId"]), int(
                    properties.get("gridProperties", {}).get("rowCount", 1_000)
                )
        raise LicenseIssueError(
            f"Worksheet {self.config.worksheet!r} does not exist."
        )

    def format_worksheet(self) -> None:
        sheet_id, row_count = self._worksheet_properties()
        grid_range = {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": 2}
        header_range = dict(grid_range, startRowIndex=0, endRowIndex=1)
        body_range = dict(grid_range, startRowIndex=1, endRowIndex=max(2, row_count))
        requests_payload = [
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
                            "endColumnIndex": 2,
                        }
                    }
                }
            },
        ]
        url = (
            "https://sheets.googleapis.com/v4/spreadsheets/"
            f"{self.config.spreadsheet_id}:batchUpdate"
        )
        self._request("POST", url, json={"requests": requests_payload})


def download_public_records(url: str) -> list[LicenseRecord]:
    if not url.strip().startswith("https://"):
        raise LicenseIssueError("Public CSV URL must use HTTPS.")
    try:
        response = requests.get(url.strip(), timeout=(5.0, 30.0))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LicenseIssueError(f"Unable to download the published CSV: {exc}") from exc
    return parse_signed_csv(response.text)


def export_csv_text(records: list[LicenseRecord]) -> str:
    return serialize_signed_csv(records)
