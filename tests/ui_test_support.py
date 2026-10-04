"""Load real fonts when Windows' offscreen Qt plugin has no font database."""

from pathlib import Path

from PySide6.QtGui import QFontDatabase


def load_test_fonts() -> None:
    if QFontDatabase.families():
        return
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf", "msyh.ttc", "malgun.ttf", "meiryo.ttc"):
        path = Path("C:/Windows/Fonts") / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
