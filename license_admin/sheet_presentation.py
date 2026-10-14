"""Sheet presentation for both client formats, shared by publish and manual formatting."""

from typing import Any

from license_admin.feed_format import LEGACY
from license_admin.feed_manifest import FEED_COLUMNS


def sheet_format_requests(sheet_id: int, row_count: int, feed_format: str) -> list[dict[str, Any]]:
    legacy = feed_format == LEGACY
    column_count = 2 if legacy else len(FEED_COLUMNS)
    grid_range = {
        "sheetId": sheet_id,
        "startColumnIndex": 0,
        "endColumnIndex": column_count,
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
        *[
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                              "startIndex": index, "endIndex": index + 1},
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
            for index, width in enumerate((440, 600) if legacy else (112, 440, 600, 280, 190))
        ],
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": max(2, row_count),
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    }
                }
            }
        },
    ]
    return requests_payload
