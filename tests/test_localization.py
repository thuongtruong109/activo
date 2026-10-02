from __future__ import annotations

import ast
from pathlib import Path
from string import Formatter
import unittest

from license_admin.locale_catalog import LANGUAGE_ORDER, MESSAGES
from license_admin.localization import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    current_language,
    set_language,
    text,
)


class LocalizationTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(DEFAULT_LANGUAGE)

    def test_catalog_covers_every_supported_language(self) -> None:
        self.assertEqual(
            tuple(option.code for option in LANGUAGES),
            LANGUAGE_ORDER,
        )
        for key, translations in MESSAGES.items():
            with self.subTest(key=key):
                self.assertEqual(len(translations), len(LANGUAGE_ORDER))
                self.assertTrue(all(value.strip() for value in translations))

    def test_translations_keep_the_same_format_fields(self) -> None:
        formatter = Formatter()
        for key, translations in MESSAGES.items():
            expected = {
                field_name
                for _, field_name, _, _ in formatter.parse(translations[0])
                if field_name is not None
            }
            for language, translation in zip(LANGUAGE_ORDER, translations):
                actual = {
                    field_name
                    for _, field_name, _, _ in formatter.parse(translation)
                    if field_name is not None
                }
                with self.subTest(key=key, language=language):
                    self.assertEqual(actual, expected)

    def test_literal_translation_keys_exist_in_catalog(self) -> None:
        package_root = Path(__file__).parents[1] / "license_admin"
        used_keys: set[str] = set()
        for source_path in package_root.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "text":
                    continue
                first_argument = node.args[0]
                if isinstance(first_argument, ast.Constant) and isinstance(
                    first_argument.value, str
                ):
                    used_keys.add(first_argument.value)

        self.assertEqual(used_keys - MESSAGES.keys(), set())

    def test_language_changes_and_unknown_codes_fall_back_to_english(self) -> None:
        set_language("es")
        self.assertEqual(current_language(), "es")
        self.assertEqual(text("action.new_license"), "Crear licencia")

        self.assertEqual(set_language("not-supported"), DEFAULT_LANGUAGE)
        self.assertEqual(text("action.new_license"), "Create license")


if __name__ == "__main__":
    unittest.main()
