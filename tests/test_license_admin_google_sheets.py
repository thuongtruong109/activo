from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license
from license_admin.domain import LicenseRecord, parse_signed_csv
from license_admin.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConfig,
    extract_spreadsheet_id,
)

TEST_ISSUER = "test-license-server"
TEST_AUDIENCE = "test-desktop"


class RecordingSheetsClient(GoogleSheetsClient):
    def __init__(self, existing: list[LicenseRecord]) -> None:
        super().__init__(
            GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("unused.json"),
            )
        )
        self.existing = existing
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def read_records(self) -> list[LicenseRecord]:
        return self.existing

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        if method == "GET":
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "Signed",
                            "gridProperties": {"rowCount": 1_000},
                        }
                    }
                ]
            }
        return {}


class LicenseAdminGoogleSheetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )

    def _record(self, character: str) -> LicenseRecord:
        hwid = character * 64
        token = issue_license(
            self.private_key,
            username=f"User {character}",
            hwid=hwid,
            days=365,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            now=datetime(2026, 9, 28, tzinfo=timezone.utc),
        )
        return parse_signed_csv(f"{hwid},{token}\n")[0]

    def test_extracts_id_from_sheet_urls(self) -> None:
        sheet_id = "abcDEF_12345678901234567890"
        self.assertEqual(
            extract_spreadsheet_id(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
            ),
            sheet_id,
        )
        self.assertEqual(extract_spreadsheet_id(sheet_id), sheet_id)
        with self.assertRaises(LicenseIssueError):
            extract_spreadsheet_id("not a sheet")

    def test_replace_updates_first_then_clears_stale_rows(self) -> None:
        existing = [self._record("a"), self._record("b"), self._record("c")]
        client = RecordingSheetsClient(existing)

        client.replace_records([existing[0]])

        self.assertEqual([call[0] for call in client.calls], ["PUT", "POST"])
        update_payload = client.calls[0][2]["json"]
        self.assertEqual(update_payload["values"][0], ["hwid", "token"])
        self.assertEqual(update_payload["values"][1][0], "a" * 64)
        self.assertIn("A3%3AB4", client.calls[1][1])

    def test_format_freezes_header_formats_text_and_adds_filter(self) -> None:
        client = RecordingSheetsClient([])

        client.format_worksheet()

        self.assertEqual([call[0] for call in client.calls], ["GET", "POST"])
        requests_payload = client.calls[1][2]["json"]["requests"]
        request_kinds = {next(iter(item)) for item in requests_payload}
        self.assertIn("updateSheetProperties", request_kinds)
        self.assertIn("repeatCell", request_kinds)
        self.assertIn("updateDimensionProperties", request_kinds)
        self.assertIn("setBasicFilter", request_kinds)


if __name__ == "__main__":
    unittest.main()
