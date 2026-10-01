"""Dark dashboard theme shared by the main window and dialogs."""

from pathlib import Path

ADMIN_STYLESHEET = """
QWidget {
    color: #eef4fb;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog { background: #07111b; }
QWidget#appShell, QWidget#mainSurface, QWidget#contentSurface { background: #07111b; }
QFrame#sidebar {
    background: #091620;
    border-right: 1px solid #1b2a38;
}
QFrame#brandBlock { background: transparent; border-bottom: 1px solid #1b2a38; }
QLabel#brandMark {
    background: #12b9e9;
    color: #ffffff;
    border-radius: 12px;
    font-size: 19px;
    font-weight: 800;
}
QLabel#brandName { color: #f6f9fc; font-size: 14px; font-weight: 700; }
QLabel#brandSubtitle { color: #607081; font-size: 9px; font-weight: 700; }
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
QFrame#projectIdentity {
    background: #0b1b28;
    border: 1px solid #1b3041;
    border-radius: 9px;
}
QLabel#projectAvatar {
    background: #0b2b3d;
    color: #18bcea;
    border: 1px solid #16445b;
    border-radius: 17px;
    font-weight: 800;
}
QLabel#projectName { color: #f2f7fb; font-size: 12px; font-weight: 700; }
QLabel#projectId { color: #637386; font-size: 9px; }
QFrame#topBar {
    background: #08121c;
    border-bottom: 1px solid #1a2937;
}
QLabel#topBarTitle { color: #f6f9fc; font-size: 13px; font-weight: 700; }
QFrame#metricCard, QFrame#tablePanel {
    background: #0e1824;
    border: 1px solid #1b2a39;
    border-radius: 11px;
}
QFrame#metricCard:hover { border-color: #284154; background: #101d2a; }
QLabel#metricTitle { color: #7f8c9b; font-size: 11px; }
QLabel#metricValue { color: #f4f8fc; font-size: 23px; font-weight: 750; }
QLabel#metricNote { color: #536476; font-size: 9px; }
QLabel#panelTitle { color: #e9eff5; font-size: 12px; font-weight: 700; }
QLabel#panelSubtitle { color: #657487; font-size: 10px; }
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
QMenu::item { padding: 7px 28px 7px 10px; border-radius: 5px; }
QMenu::item:selected { background: #173247; color: #ffffff; }
QMenu::item:disabled { background: transparent; color: #3e4c59; }
QMenu::separator { height: 1px; background: #243543; margin: 5px 7px; }
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
QDialogButtonBox { background: transparent; }
QToolTip { background: #132433; color: #eef4fb; border: 1px solid #365064; padding: 4px; }
"""

_DOWN_ARROW_URL = (
    Path(__file__).with_name("assets") / "chevron-down.svg"
).as_posix()
ADMIN_STYLESHEET += f"""
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url(\"{_DOWN_ARROW_URL}\");
    width: 12px;
    height: 12px;
}}
"""
