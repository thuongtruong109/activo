"""User-facing About, privacy policy, and terms dialogs."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from license_admin.app_identity import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    SUPPORT_EMAIL,
)
from license_admin.accessibility import announce
from license_admin.diagnostics import (
    build_channel,
    diagnostics_text,
    third_party_notices_path,
)
from license_admin.information_content import document_content
from license_admin.responsive import fit_window_to_screen, wrap_label
from license_admin.version import APP_COMPANY_NAME
from license_admin.icons import svg_icon
from license_admin.localization import text
from license_admin.window_chrome import (
    DraggableFrame,
    FramelessResizeController,
    enable_frameless_window,
)


class InformationDialog(QDialog):
    """Compact, scrollable modal for user-facing product documents."""

    _DOCUMENT_ICONS = {
        "about": "about",
        "policy": "shield",
        "terms": "document",
    }

    def __init__(self, parent: QWidget, document: str) -> None:
        super().__init__(parent)
        content, uses_english = document_content(document)
        enable_frameless_window(self)
        self.setObjectName("informationDialog")
        self.setWindowTitle(content.title)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        self.surface = QFrame()
        self.surface.setObjectName("informationSurface")
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 115))
        self.surface.setGraphicsEffect(shadow)
        root.addWidget(self.surface)

        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        header = DraggableFrame()
        header.setObjectName("informationHeader")
        header.setMinimumHeight(72)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 12, 16, 12)
        header_layout.setSpacing(12)

        icon_badge = QLabel()
        icon_badge.setObjectName("informationIconBadge")
        icon_badge.setFixedSize(38, 38)
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setPixmap(
            svg_icon(self._DOCUMENT_ICONS[document], 18).pixmap(18, 18)
        )
        header_layout.addWidget(icon_badge)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        app_label = QLabel(APP_DISPLAY_NAME.upper())
        app_label.setObjectName("informationEyebrow")
        title_label = QLabel(content.title)
        title_label.setObjectName("informationTitle")
        title_label.setWordWrap(True)
        heading.addWidget(app_label)
        heading.addWidget(title_label)
        header_layout.addLayout(heading, 1)

        close_button = QToolButton()
        close_button.setObjectName("informationCloseButton")
        close_button.setFixedSize(30, 30)
        close_button.setIcon(svg_icon("close", 16))
        close_button.setIconSize(QSize(16, 16))
        close_button.setToolTip(text("common.close"))
        close_button.setAccessibleName(text("common.close"))
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        header_layout.addWidget(close_button)
        surface_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("informationScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("informationBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(26, 22, 20, 22)
        body_layout.setSpacing(0)

        summary = QLabel(content.summary)
        summary.setObjectName("informationSummary")
        summary.setWordWrap(True)
        body_layout.addWidget(summary)
        body_layout.addSpacing(24)

        self.language_notice = QLabel(text("info.english_notice"))
        self.language_notice.setObjectName("informationLanguageNotice")
        self.language_notice.setWordWrap(True)
        self.language_notice.setVisible(uses_english)
        if uses_english:
            body_layout.insertWidget(0, self.language_notice)
            body_layout.insertSpacing(1, 16)

        sections = content.sections
        if document == "about":
            sections = content.sections + (
                (text("info.version"), APP_VERSION),
                (
                    text("info.channel"),
                    text("info.packaged") if build_channel() == "packaged" else text("info.source"),
                ),
                (text("info.publisher"), APP_COMPANY_NAME),
                (text("info.attribution"), text("info.attribution_body")),
            )
        self.section_titles: list[QLabel] = []
        self.section_bodies: list[QLabel] = []
        for index, (title, paragraph) in enumerate(sections, start=1):
            section = QFrame()
            section.setObjectName("informationSection")
            section_layout = QHBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 4, 0)
            section_layout.setSpacing(14)

            section_index = QLabel(f"{index:02d}")
            section_index.setObjectName("informationSectionIndex")
            section_index.setFixedWidth(28)
            section_index.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            section_layout.addWidget(section_index)

            copy_layout = QVBoxLayout()
            copy_layout.setContentsMargins(0, 0, 0, 0)
            copy_layout.setSpacing(5)
            section_title = QLabel(title)
            section_title.setObjectName("informationSectionTitle")
            section_title.setWordWrap(True)
            section_body = QLabel(paragraph)
            section_body.setObjectName("informationSectionBody")
            # Size paragraphs at their actual width instead of their unwrapped size hint.
            wrap_label(section_body, vertical_policy=QSizePolicy.Policy.Preferred)
            section_body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.section_titles.append(section_title)
            self.section_bodies.append(section_body)
            copy_layout.addWidget(section_title)
            copy_layout.addWidget(section_body)
            section_layout.addLayout(copy_layout, 1)
            body_layout.addWidget(section)
            if index < len(sections):
                divider = QFrame()
                divider.setObjectName("informationDivider")
                divider.setFixedHeight(1)
                body_layout.addSpacing(18)
                body_layout.addWidget(divider)
                body_layout.addSpacing(18)

        self.contact_link: QLabel | None = None
        if document == "about":
            body_layout.addSpacing(22)
            contact = QFrame()
            contact.setObjectName("informationContact")
            contact_layout = QHBoxLayout(contact)
            contact_layout.setContentsMargins(15, 12, 15, 12)
            contact_layout.setSpacing(11)
            contact_icon = QLabel()
            contact_icon.setObjectName("informationContactIcon")
            contact_icon.setFixedSize(28, 28)
            contact_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            contact_icon.setPixmap(svg_icon("about", 16).pixmap(16, 16))
            contact_layout.addWidget(contact_icon)
            self.contact_link = QLabel(
                f'<span>{text("info.contact")}</span><br>'
                f'<a style="color:#32bde7; text-decoration:none" '
                f'href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>'
            )
            self.contact_link.setObjectName("informationContactLink")
            self.contact_link.setOpenExternalLinks(True)
            self.contact_link.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            contact_layout.addWidget(self.contact_link, 1)
            body_layout.addWidget(contact)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        surface_layout.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("informationFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 9, 20, 9)
        self.copy_diagnostics_button: QPushButton | None = None
        if document == "about":
            self.copy_diagnostics_button = QPushButton(text("info.copy_diagnostics"))
            self.copy_diagnostics_button.setToolTip(text("info.diagnostics_note"))
            self.copy_diagnostics_button.setAccessibleDescription(text("info.diagnostics_note"))
            self.copy_diagnostics_button.clicked.connect(self._copy_diagnostics)
            footer_layout.addWidget(self.copy_diagnostics_button)
            notices = third_party_notices_path()
            if notices is not None:
                notices_button = QPushButton(text("info.open_notices"))
                notices_button.clicked.connect(
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(notices)))
                )
                body_layout.insertWidget(body_layout.count() - 1, notices_button)
        footer_layout.addStretch(1)
        close_action = QPushButton(text("common.close"))
        close_action.setObjectName("informationCloseAction")
        close_action.setMinimumWidth(72)
        close_action.clicked.connect(self.accept)
        footer_layout.addWidget(close_action)
        surface_layout.addWidget(footer)
        fit_window_to_screen(self, QSize(670, 570))
        self._frameless_resize = FramelessResizeController(self)

    def _copy_diagnostics(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(diagnostics_text(self.parentWidget() or self))
        announce(self, text("info.diagnostics_copied"))
        if self.copy_diagnostics_button is not None:
            self.copy_diagnostics_button.setText(text("info.diagnostics_copied"))


class AboutDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "about")


class PolicyDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "policy")


class TermsOfServiceDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "terms")
