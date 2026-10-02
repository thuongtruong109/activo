"""Small runtime localization service for the desktop interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from license_admin.locale_catalog import LANGUAGE_ORDER, MESSAGES


@dataclass(frozen=True, slots=True)
class LanguageOption:
    code: str
    native_name: str
    country_code: str


LANGUAGES = (
    LanguageOption("en", "English", "us"),
    LanguageOption("vi", "Tiếng Việt", "vn"),
    LanguageOption("es", "Español", "es"),
    LanguageOption("ja", "日本語", "jp"),
    LanguageOption("zh", "中文", "cn"),
    LanguageOption("ko", "한국어", "kr"),
    LanguageOption("pt", "Português", "pt"),
)
SUPPORTED_LANGUAGE_CODES = frozenset(option.code for option in LANGUAGES)
DEFAULT_LANGUAGE = "en"
_current_language = DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    """Set the process UI language, falling back to English."""
    global _current_language
    normalized = code.strip().casefold()
    _current_language = (
        normalized if normalized in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE
    )
    return _current_language


def current_language() -> str:
    return _current_language


def text(key: str, **values: Any) -> str:
    """Translate a key and safely format named placeholders."""
    messages = MESSAGES.get(key)
    if messages is None:
        return key
    index = LANGUAGE_ORDER.index(_current_language)
    template = messages[index] or messages[0]
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def language_option(code: str) -> LanguageOption:
    normalized = code.strip().casefold()
    return next(
        (option for option in LANGUAGES if option.code == normalized),
        LANGUAGES[0],
    )
