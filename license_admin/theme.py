"""Dark and light application themes shared by windows and dialogs."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from license_admin.ui_metrics import (
    BUTTON_CONTENT_HEIGHT,
    INPUT_CONTENT_HEIGHT,
)

ADMIN_STYLESHEET = """
QWidget {
    color: #eef4fb;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow { background: transparent; }
QDialog { background: #07111b; }
QWidget#appShell, QWidget#mainSurface, QWidget#contentSurface { background: #07111b; }
QWidget#appShell { border: 1px solid #1b2a38; border-radius: 12px; }
QFrame#sidebar {
    background: #091620;
    border-right: 1px solid #1b2a38;
}
QFrame#windowChrome {
    background: #091620;
    border: 0;
    border-bottom: 1px solid #1a2937;
}
QPushButton#trafficClose, QPushButton#trafficMinimize, QPushButton#trafficMaximize {
    border: 0;
    border-radius: 6px;
    padding: 0;
    min-width: 12px;
    max-width: 12px;
    min-height: 12px;
    max-height: 12px;
}
QPushButton#trafficClose { background: #ff5f57; }
QPushButton#trafficMinimize { background: #febc2e; }
QPushButton#trafficMaximize { background: #28c840; }
QPushButton#trafficClose:hover { background: #ff756e; }
QPushButton#trafficMinimize:hover { background: #ffca4b; }
QPushButton#trafficMaximize:hover { background: #45d45a; }
QWidget#headerBrand { background: transparent; }
QLabel#brandName { color: #f6f9fc; font-size: 11px; font-weight: 750; }
QLabel#navSection { color: #526273; font-size: 9px; font-weight: 700; padding: 5px 9px; }
QPushButton#sidebarButton, QToolButton#sidebarButton {
    background: transparent;
    color: #a8b4c0;
    border: 0;
    border-radius: 8px;
    padding: 0 12px;
    min-height: 42px;
    max-height: 42px;
    text-align: left;
    font-weight: 600;
}
QToolButton#sidebarButton { padding-right: 28px; }
QPushButton#sidebarButton:hover, QToolButton#sidebarButton:hover {
    background: #112534;
    color: #eff8ff;
}
QPushButton#sidebarButton[active="true"], QToolButton#sidebarButton[active="true"] {
    background: #172b3a;
    color: #f8fbff;
}
QFrame#activeNavIndicator { background: #19c2ef; border: 0; border-radius: 1px; }
QToolButton#sidebarButton::menu-indicator { image: none; width: 0; }
QToolButton#projectSelector {
    background: #0b1b28;
    border: 1px solid #1b3041;
    border-radius: 9px;
    padding: 0;
    min-height: 40px;
    max-height: 40px;
}
QToolButton#projectSelector:hover {
    background: #102536;
    border-color: #28516a;
}
QLabel#projectSelectorAvatar {
    background: #0b2b3d;
    color: #18bcea;
    border: 1px solid #16445b;
    border-radius: 15px;
    font-weight: 800;
}
QLabel#projectSelectorName { color: #f2f7fb; font-size: 11px; font-weight: 700; }
QLabel#projectSelectorId { color: #637386; font-size: 9px; }
QFrame#topBar {
    background: #08121c;
    border-bottom: 1px solid #1a2937;
}
QFrame#metricCard, QFrame#tablePanel {
    background: #0e1824;
    border: 1px solid #1b2a39;
    border-radius: 11px;
}
QFrame#metricCard:hover { border-color: #284154; background: #101d2a; }
QLabel#metricTitle { color: #7f8c9b; font-size: 11px; }
QLabel#metricValue { color: #f4f8fc; font-size: 23px; font-weight: 750; }
QLabel#metricNote { color: #536476; font-size: 9px; }
QLabel#muted { color: #7f8b99; }
QLabel#warning { color: #f8bf48; }
QLabel#danger { color: #f87171; }
QLabel#syncBadge {
    background: #2b2212;
    color: #f5c451;
    border: 1px solid #5f4820;
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#syncBadge[synced="true"] {
    background: #0d2b22;
    color: #38d996;
    border-color: #175b43;
}
QPushButton {
    background: #142332;
    color: #edf5fb;
    border: 1px solid #294052;
    border-radius: 7px;
    padding: 4px 9px;
    min-height: 18px;
    font-weight: 600;
}
QPushButton:hover { background: #193044; border-color: #35617c; }
QPushButton:pressed { background: #10202d; }
QPushButton:disabled { color: #4c5b69; background: #0d1720; border-color: #182632; }
QPushButton#primaryButton {
    background: #12ace0;
    color: #02131c;
    border: 1px solid #28c3ef;
    padding: 4px 10px;
    font-weight: 750;
}
QPushButton#primaryButton:hover { background: #2fc5ef; }
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {
    background: #0b1621;
    color: #eaf2f8;
    border: 1px solid #253544;
    border-radius: 7px;
    padding: 6px 9px;
    min-height: 22px;
    selection-background-color: #0d88b4;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover, QSpinBox:hover {
    border-color: #355166;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QSpinBox:focus {
    border-color: #12aeda;
}
QCalendarWidget {
    background: #0b1520;
    border: 1px solid #253544;
    border-radius: 7px;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #0d1b28;
    border-bottom: 1px solid #253544;
}
QCalendarWidget QToolButton {
    background: transparent;
    color: #eaf2f8;
    border: 0;
    border-radius: 5px;
    padding: 4px 7px;
    font-weight: 650;
}
QCalendarWidget QToolButton:hover { background: #173348; }
QCalendarWidget QAbstractItemView:enabled {
    background: #0b1520;
    alternate-background-color: #0e1a26;
    color: #dce5ec;
    selection-background-color: #0f789e;
    selection-color: #ffffff;
    border: 0;
    outline: 0;
}
QCalendarWidget QAbstractItemView:disabled { color: #4c5b69; }
QLineEdit#dashboardSearch { padding-left: 11px; }
QLineEdit QToolButton {
    background: transparent;
    border: 0;
    padding: 0;
    margin: 0 3px 0 0;
    min-width: 16px;
    min-height: 16px;
    max-width: 16px;
    max-height: 16px;
}
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView {
    background: #0d1b28;
    color: #eef4fb;
    border: 1px solid #294052;
    selection-background-color: #173348;
    padding: 4px;
}
QMenu {
    background: #0d1a26;
    color: #eaf2f8;
    border: 1px solid #2a3d4d;
    border-radius: 7px;
    padding: 5px;
}
QMenu#roundedPopover {
    background: #0d1a26;
    border: 1px solid #2a3d4d;
    border-radius: 10px;
    padding: 4px;
}
QMenu#roundedPopover::item {
    padding: 5px 20px 5px 10px;
    border-radius: 5px;
}
QMenu#roundedPopover::indicator {
    width: 26px;
    height: 14px;
}
QMenu#roundedPopover::item:selected { background: #173b52; color: #ffffff; }
QMenu#roundedPopover::item:checked { background: #0f789e; color: #ffffff; }
QMenu::item { padding: 7px 28px 7px 10px; border-radius: 5px; }
QMenu::item:selected { background: #173247; color: #ffffff; }
QMenu::item:disabled { background: transparent; color: #3e4c59; }
QMenu::separator { height: 1px; background: #243543; margin: 5px 7px; }
QToolButton[popover="true"] {
    background: #0b1621;
    color: #eaf2f8;
    border: 1px solid #253544;
    border-radius: 7px;
    padding: 4px 26px 4px 10px;
    min-height: 26px;
    text-align: left;
    font-weight: 600;
}
QToolButton[popover="true"]:hover {
    background: #10202d;
    border-color: #355166;
}
QToolButton[popover="true"]:disabled {
    color: #4c5b69;
    background: #0d1720;
    border-color: #182632;
}
QToolButton[popover="true"]::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 8px;
    width: 12px;
    height: 12px;
}
QToolButton#languageSelect {
    background: #0b1b28;
    border-color: #1b3041;
    border-radius: 8px;
    padding: 4px 26px 4px 7px;
    font-size: 11px;
}
QFrame#themeTabs {
    background: #101d29;
    border: 1px solid #243646;
    border-radius: 8px;
}
QPushButton#themeLightTab, QPushButton#themeDarkTab {
    background: transparent;
    color: #7f8e9e;
    border: 0;
    border-radius: 6px;
    padding: 0 6px;
    font-size: 11px;
    font-weight: 650;
}
QPushButton#themeLightTab:hover, QPushButton#themeDarkTab:hover {
    background: #172838;
    color: #dce7ef;
}
QPushButton#themeLightTab[active="true"], QPushButton#themeDarkTab[active="true"] {
    background: #263a4b;
    color: #ffffff;
}
QTableView {
    background: #0b1520;
    alternate-background-color: #0e1a26;
    color: #dce5ec;
    border: 0;
    gridline-color: #1a2936;
    selection-background-color: #153c54;
    selection-color: #ffffff;
    outline: 0;
}
QTableView::item { padding: 6px 7px; border-bottom: 1px solid #162532; }
QTableView::item:hover { background: #122535; }
QHeaderView::section {
    background: #09131d;
    color: #758597;
    border: 0;
    border-bottom: 1px solid #233443;
    padding: 8px 7px;
    font-size: 10px;
    font-weight: 700;
}
QHeaderView::section:vertical {
    background: #0b1520;
    color: #536274;
    border-right: 1px solid #1c2b38;
}
QTableCornerButton::section {
    background: #09131d;
    border: 0;
    border-right: 1px solid #233443;
    border-bottom: 1px solid #233443;
}
QScrollBar:vertical {
    background: #0a141e;
    width: 9px;
    margin: 3px 2px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2b4559;
    border-radius: 4px;
    min-height: 34px;
}
QScrollBar::handle:vertical:hover { background: #3c617b; }
QScrollBar:horizontal {
    background: #0a141e;
    height: 9px;
    margin: 2px 3px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #2b4559;
    border-radius: 4px;
    min-width: 34px;
}
QScrollBar::handle:horizontal:hover { background: #3c617b; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QFrame#toast { background: #0c3025; border: 1px solid #1a6a4c; border-radius: 9px; }
QFrame#toast[tone="info"] { background: #0c2638; border-color: #176386; }
QFrame#toast QLabel { background: transparent; }
QLabel#toastMessage { color: #f1f7fa; }
QTabWidget::pane { border: 1px solid #263746; border-radius: 7px; top: -1px; }
QTabBar::tab {
    background: #0b1621;
    color: #798899;
    padding: 8px 14px;
    border: 1px solid #263746;
}
QTabBar::tab:selected { color: #ffffff; background: #122332; border-bottom-color: #122332; }
QDialog#settingsDialog {
    background: #07111b;
    border: 1px solid #2a3d4d;
    border-radius: 11px;
}
QWidget#settingsBody {
    background: #07111b;
    border-bottom-left-radius: 11px;
    border-bottom-right-radius: 11px;
}
QFrame#settingsHeader {
    background: #091620;
    border: 0;
    border-bottom: 1px solid #263746;
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
}
QTabBar#settingsTabBar { background: transparent; }
QTabBar#settingsTabBar::tab {
    background: transparent;
    color: #7f8d9c;
    border: 0;
    border-right: 1px solid #263746;
    border-bottom: 2px solid transparent;
    padding: 11px 16px 9px 16px;
}
QTabBar#settingsTabBar::tab:hover { color: #dbe7ef; background: #0d1c29; }
QTabBar#settingsTabBar::tab:selected {
    color: #ffffff;
    background: #102230;
    border-bottom: 2px solid #19bdea;
}
QStackedWidget#settingsPages {
    background: transparent;
    border: 0;
    border-radius: 0;
}
QToolButton#modalCloseButton {
    background: transparent;
    color: #8291a0;
    border: 0;
    border-radius: 6px;
    font-size: 20px;
    font-weight: 400;
}
QToolButton#modalCloseButton:hover { background: #3b1d25; color: #ff7b82; }
QDialogButtonBox { background: transparent; }
QFrame#modalBackdrop {
    background: rgba(2, 8, 13, 148);
    border: 0;
    border-radius: 12px;
}
QToolTip { background: #132433; color: #eef4fb; border: 1px solid #365064; padding: 4px; }
"""

_DOWN_ARROW_URL = (
    Path(__file__).with_name("assets") / "chevron-down.svg"
).as_posix()
_MENU_CHECK_URL = (
    Path(__file__).with_name("assets") / "menu-check.svg"
).as_posix()
_MENU_CHECK_LIGHT_URL = (
    Path(__file__).with_name("assets") / "menu-check-light.svg"
).as_posix()
ADMIN_STYLESHEET += f"""
QComboBox::down-arrow, QDateEdit::down-arrow,
QToolButton[popover="true"]::menu-indicator {{
    image: url(\"{_DOWN_ARROW_URL}\");
    width: 12px;
    height: 12px;
}}
QMenu#roundedPopover::indicator:checked {{
    image: url("{_MENU_CHECK_URL}");
}}
QPushButton {{
    min-height: {BUTTON_CONTENT_HEIGHT}px;
    max-height: {BUTTON_CONTENT_HEIGHT}px;
}}
QLineEdit, QComboBox, QDateEdit, QSpinBox {{
    min-height: {INPUT_CONTENT_HEIGHT}px;
    max-height: {INPUT_CONTENT_HEIGHT}px;
}}
QToolButton[popover="true"] {{
    min-height: {BUTTON_CONTENT_HEIGHT}px;
    max-height: {BUTTON_CONTENT_HEIGHT}px;
}}
"""

DARK_STYLESHEET = ADMIN_STYLESHEET
LIGHT_OVERRIDES = """
QWidget { color: #243244; }
QDialog,
QWidget#appShell, QWidget#mainSurface, QWidget#contentSurface {
    background: #f6f8fb;
}
QWidget#appShell { border-color: #cfd7e2; }
QFrame#sidebar, QFrame#windowChrome {
    background: #eef2f7;
    border-color: #d4dce6;
}
QLabel#brandName { color: #1f2c3d; }
QLabel#navSection { color: #77869a; }
QPushButton#sidebarButton, QToolButton#sidebarButton { color: #526276; }
QPushButton#sidebarButton:hover, QToolButton#sidebarButton:hover {
    background: #e1e8f0;
    color: #172435;
}
QPushButton#sidebarButton[active="true"],
QToolButton#sidebarButton[active="true"] {
    background: #dce7f1;
    color: #172435;
}
QToolButton#projectSelector {
    background: #f7f9fc;
    border-color: #cfd9e4;
}
QToolButton#projectSelector:hover { background: #ffffff; border-color: #aebdcb; }
QLabel#projectSelectorAvatar {
    background: #e4f6fc;
    color: #0788b1;
    border-color: #b7deeb;
}
QLabel#projectSelectorName { color: #1e2b3b; }
QLabel#projectSelectorId { color: #77869a; }
QFrame#topBar {
    background: #f7f9fc;
    border-color: #d4dce6;
}
QFrame#metricCard, QFrame#tablePanel {
    background: #ffffff;
    border-color: #d8e0e9;
}
QFrame#metricCard:hover { background: #fbfcfe; border-color: #becbd8; }
QLabel#metricTitle, QLabel#muted { color: #718096; }
QLabel#metricValue { color: #1e293b; }
QLabel#metricNote { color: #8794a6; }
QLabel#warning { color: #966600; }
QLabel#danger { color: #c93d4f; }
QLabel#syncBadge {
    background: #fff4cf;
    color: #805b00;
    border-color: #e5c65f;
}
QLabel#syncBadge[synced="true"] {
    background: #dff7ec;
    color: #147552;
    border-color: #99d8be;
}
QPushButton {
    background: #ffffff;
    color: #2f3d4e;
    border-color: #cbd5e1;
}
QPushButton:hover { background: #f0f5f9; border-color: #9fb0c1; }
QPushButton:pressed { background: #e4ebf2; }
QPushButton:disabled { color: #a1adba; background: #f1f4f7; border-color: #d9e0e7; }
QPushButton#primaryButton {
    background: #15b8e8;
    color: #04212c;
    border-color: #0ca6d2;
}
QPushButton#primaryButton:hover { background: #35c5ed; }
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox,
QToolButton[popover="true"] {
    background: #ffffff;
    color: #263648;
    border-color: #cbd5e1;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QTextEdit:hover,
QSpinBox:hover, QToolButton[popover="true"]:hover { border-color: #9aabba; }
QCalendarWidget {
    background: #ffffff;
    border-color: #cbd5e1;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #eef2f7;
    border-bottom-color: #d4dce6;
}
QCalendarWidget QToolButton { color: #263648; }
QCalendarWidget QToolButton:hover { background: #dce7f1; }
QCalendarWidget QAbstractItemView:enabled {
    background: #ffffff;
    alternate-background-color: #f7f9fc;
    color: #263648;
    selection-background-color: #ccecf7;
    selection-color: #102a38;
}
QCalendarWidget QAbstractItemView:disabled { color: #a1adba; }
QComboBox QAbstractItemView,
QMenu, QMenu#roundedPopover {
    background: #ffffff;
    color: #273548;
    border-color: #cbd5e1;
}
QMenu#roundedPopover::item:selected, QMenu::item:selected {
    background: #e4f3f9;
    color: #172435;
}
QMenu#roundedPopover::item:checked { background: #ccecf7; color: #102a38; }
QMenu::item:disabled { color: #a3afbc; }
QMenu::separator { background: #dce3eb; }
QToolButton#languageSelect { background: #ffffff; border-color: #cbd5e1; }
QTableView {
    background: #ffffff;
    alternate-background-color: #f7f9fc;
    color: #263648;
    gridline-color: #e0e6ed;
    selection-background-color: #d9edf7;
    selection-color: #172435;
}
QTableView::item { border-bottom-color: #e6ebf0; }
QTableView::item:hover { background: #edf5fa; }
QHeaderView::section, QTableCornerButton::section {
    background: #f2f5f8;
    color: #65758a;
    border-color: #d8e0e8;
}
QHeaderView::section:vertical { background: #f7f9fc; color: #8996a6; }
QScrollBar:vertical, QScrollBar:horizontal { background: #eef2f6; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #b5c1ce; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #94a4b5; }
QTabWidget::pane { border-color: #d1dae4; }
QTabBar::tab { background: #edf1f5; color: #68788c; border-color: #d1dae4; }
QTabBar::tab:selected { background: #ffffff; color: #1f2c3d; border-bottom-color: #ffffff; }
QDialog#settingsDialog { background: #f7f9fc; border-color: #cbd5e1; }
QWidget#settingsBody { background: #f7f9fc; }
QFrame#settingsHeader { background: #eef2f7; border-color: #d4dce6; }
QTabBar#settingsTabBar::tab { color: #68788c; border-right-color: #d4dce6; }
QTabBar#settingsTabBar::tab:hover { color: #243244; background: #e4eaf1; }
QTabBar#settingsTabBar::tab:selected { color: #152536; background: #ffffff; }
QToolButton#modalCloseButton { color: #6f7e90; }
QToolButton#modalCloseButton:hover { background: #f9dfe3; color: #bd3345; }
QFrame#themeTabs { background: #e8edf3; border: 1px solid #d2dae4; }
QPushButton#themeLightTab, QPushButton#themeDarkTab { color: #66758a; }
QPushButton#themeLightTab[active="true"], QPushButton#themeDarkTab[active="true"] {
    background: #ffffff;
    color: #263648;
}
QToolTip { background: #ffffff; color: #263648; border-color: #b9c5d1; }
"""
LIGHT_OVERRIDES += f"""
QMenu#roundedPopover::indicator:checked {{
    image: url("{_MENU_CHECK_LIGHT_URL}");
}}
"""

THEME_MODES = frozenset(("light", "dark"))
DEFAULT_THEME = "dark"


def normalize_theme(mode: str) -> str:
    normalized = mode.strip().casefold()
    return normalized if normalized in THEME_MODES else DEFAULT_THEME


def stylesheet_for(mode: str) -> str:
    if normalize_theme(mode) == "light":
        return DARK_STYLESHEET + LIGHT_OVERRIDES
    return DARK_STYLESHEET


def apply_theme(mode: str) -> str:
    normalized = normalize_theme(mode)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyleSheet(stylesheet_for(normalized))
    return normalized
