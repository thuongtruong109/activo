"""User-facing About, privacy policy, and terms dialogs."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
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
from license_admin.icons import svg_icon
from license_admin.localization import current_language, text
from license_admin.window_chrome import DraggableFrame, enable_frameless_window


@dataclass(frozen=True, slots=True)
class InformationContent:
    title: str
    summary: str
    sections: tuple[tuple[str, str], ...]


_CONTENT: dict[str, dict[str, InformationContent]] = {
    "about": {
        "en": InformationContent(
            "About License Admin",
            "A focused desktop application for issuing and managing signed product licenses across isolated projects.",
            (
                (
                    "Purpose",
                    "License Admin helps authorized operators create, renew, revoke, verify, import, export, and synchronize license records without mixing data between projects.",
                ),
                (
                    "Designed for control",
                    "Each project keeps its own signing keys, credentials, settings, and license data. Sensitive actions remain explicit and visible to the operator.",
                ),
                (
                    "Version",
                    f"{APP_DISPLAY_NAME} {APP_VERSION}",
                ),
            ),
        ),
        "vi": InformationContent(
            "Giới thiệu License Admin",
            "Ứng dụng desktop chuyên dụng để phát hành và quản lý license đã ký cho nhiều project độc lập.",
            (
                (
                    "Mục đích",
                    "License Admin hỗ trợ người vận hành được ủy quyền tạo, gia hạn, thu hồi, xác minh, nhập, xuất và đồng bộ bản ghi license mà không trộn dữ liệu giữa các project.",
                ),
                (
                    "Được thiết kế để kiểm soát",
                    "Mỗi project giữ riêng key ký, credential, cấu hình và dữ liệu license. Các thao tác nhạy cảm đều cần hành động rõ ràng từ người vận hành.",
                ),
                (
                    "Phiên bản",
                    f"{APP_DISPLAY_NAME} {APP_VERSION}",
                ),
            ),
        ),
    },
    "policy": {
        "en": InformationContent(
            "Privacy & transparency policy",
            "Effective 3 October 2026. This policy explains what the application stores, when it connects to external services, and what remains under your control.",
            (
                (
                    "Local-first data",
                    "Project profiles, private keys, Google credentials, and local license records are stored on the device or storage location selected by the operator. License Admin does not include advertising or behavioral analytics.",
                ),
                (
                    "External connections",
                    "The application contacts Google services only for an operator-requested Sheet action. It may retrieve language flag icons from FlagCDN. Data sent to Google is governed by the configured account and Google's policies.",
                ),
                (
                    "Sensitive credentials",
                    "Private signing keys and service-account credentials are used locally for authorized signing or authentication. The application does not intentionally publish them or include them in exported project settings.",
                ),
                (
                    "Operator control",
                    "You decide which projects, files, credentials, and Sheets are configured. You can remove local project data and revoke external credentials at any time.",
                ),
                (
                    "Transparency commitment",
                    "We aim to make network actions explicit, avoid hidden data collection, report errors clearly, and update this notice when application behavior materially changes.",
                ),
            ),
        ),
        "vi": InformationContent(
            "Chính sách riêng tư & minh bạch",
            "Có hiệu lực từ 03/10/2026. Chính sách này giải thích dữ liệu ứng dụng lưu, thời điểm kết nối dịch vụ ngoài và quyền kiểm soát của bạn.",
            (
                (
                    "Dữ liệu ưu tiên lưu cục bộ",
                    "Profile project, private key, Google credential và bản ghi license cục bộ được lưu trên thiết bị hoặc vị trí do người vận hành chọn. License Admin không tích hợp quảng cáo hay phân tích hành vi.",
                ),
                (
                    "Kết nối bên ngoài",
                    "Ứng dụng chỉ kết nối dịch vụ Google khi người vận hành yêu cầu thao tác với Sheet. Ứng dụng có thể tải icon cờ ngôn ngữ từ FlagCDN. Dữ liệu gửi tới Google chịu sự điều chỉnh của tài khoản đã cấu hình và chính sách của Google.",
                ),
                (
                    "Credential nhạy cảm",
                    "Private key ký và service-account credential được dùng cục bộ cho việc ký hoặc xác thực đã được cho phép. Ứng dụng không chủ ý công khai chúng hoặc đưa chúng vào file cấu hình project được xuất.",
                ),
                (
                    "Quyền kiểm soát của người vận hành",
                    "Bạn quyết định project, file, credential và Google Sheet nào được cấu hình. Bạn có thể xóa dữ liệu project cục bộ và thu hồi credential bên ngoài bất kỳ lúc nào.",
                ),
                (
                    "Cam kết minh bạch",
                    "Chúng tôi hướng tới việc thể hiện rõ thao tác mạng, không thu thập dữ liệu ngầm, báo lỗi minh bạch và cập nhật thông báo này khi hành vi ứng dụng thay đổi đáng kể.",
                ),
            ),
        ),
    },
    "terms": {
        "en": InformationContent(
            "Terms of service",
            "Effective 3 October 2026. By using License Admin, you agree to operate it responsibly and only for projects you are authorized to manage.",
            (
                (
                    "Authorized use",
                    "Use the application only to administer licenses, keys, credentials, and data that you own or are expressly authorized to manage. Do not use it to bypass access controls or violate applicable law.",
                ),
                (
                    "Your responsibilities",
                    "You are responsible for protecting private keys and credentials, validating project settings and recipients, maintaining backups, and reviewing data before publishing it to a configured Sheet.",
                ),
                (
                    "Security and availability",
                    "No software can guarantee uninterrupted operation or absolute security. Keep the application and operating system updated, restrict device access, and revoke any credential you suspect is compromised.",
                ),
                (
                    "Data and consequences",
                    "Signing, revoking, importing, exporting, and synchronizing can affect production access. Confirm the active project and keep recoverable backups before material changes.",
                ),
                (
                    "Changes and fair notice",
                    "Material changes to these terms or the application's data behavior should be communicated clearly. Continued use after notice indicates acceptance of the updated terms.",
                ),
            ),
        ),
        "vi": InformationContent(
            "Điều khoản dịch vụ",
            "Có hiệu lực từ 03/10/2026. Khi sử dụng License Admin, bạn đồng ý vận hành có trách nhiệm và chỉ quản lý những project mình được ủy quyền.",
            (
                (
                    "Sử dụng được ủy quyền",
                    "Chỉ dùng ứng dụng để quản trị license, key, credential và dữ liệu thuộc sở hữu của bạn hoặc được ủy quyền rõ ràng. Không dùng ứng dụng để vượt kiểm soát truy cập hoặc vi phạm pháp luật áp dụng.",
                ),
                (
                    "Trách nhiệm của bạn",
                    "Bạn chịu trách nhiệm bảo vệ private key và credential, xác minh cấu hình project và đối tượng nhận, duy trì bản sao lưu, đồng thời kiểm tra dữ liệu trước khi publish lên Sheet đã cấu hình.",
                ),
                (
                    "Bảo mật và tính sẵn sàng",
                    "Không phần mềm nào có thể bảo đảm hoạt động liên tục hoặc an toàn tuyệt đối. Hãy cập nhật ứng dụng và hệ điều hành, giới hạn quyền truy cập thiết bị và thu hồi credential nghi bị lộ.",
                ),
                (
                    "Dữ liệu và hệ quả",
                    "Việc ký, thu hồi, nhập, xuất và đồng bộ có thể ảnh hưởng quyền truy cập thực tế. Hãy xác nhận đúng project đang hoạt động và giữ bản sao lưu có thể khôi phục trước thay đổi quan trọng.",
                ),
                (
                    "Thay đổi và thông báo công bằng",
                    "Mọi thay đổi quan trọng đối với điều khoản hoặc hành vi dữ liệu của ứng dụng cần được thông báo rõ ràng. Việc tiếp tục sử dụng sau thông báo đồng nghĩa chấp nhận điều khoản cập nhật.",
                ),
            ),
        ),
    },
}


def _localized_content(document: str) -> InformationContent:
    translations = _CONTENT[document]
    return translations.get(current_language(), translations["en"])


class InformationDialog(QDialog):
    """Compact, scrollable modal for user-facing product documents."""

    _DOCUMENT_ICONS = {
        "about": "about",
        "policy": "shield",
        "terms": "document",
    }

    def __init__(self, parent: QWidget, document: str) -> None:
        super().__init__(parent)
        content = _localized_content(document)
        enable_frameless_window(self)
        self.setObjectName("informationDialog")
        self.setWindowTitle(content.title)
        self.setModal(True)
        self.setMinimumSize(620, 520)
        self.resize(670, 570)

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
        header.setFixedHeight(72)
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

        self.section_titles: list[QLabel] = []
        self.section_bodies: list[QLabel] = []
        for index, (title, paragraph) in enumerate(content.sections, start=1):
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
            section_body = QLabel(paragraph)
            section_body.setObjectName("informationSectionBody")
            section_body.setWordWrap(True)
            section_body.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Minimum,
            )
            section_body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.section_titles.append(section_title)
            self.section_bodies.append(section_body)
            copy_layout.addWidget(section_title)
            copy_layout.addWidget(section_body)
            section_layout.addLayout(copy_layout, 1)
            body_layout.addWidget(section)
            if index < len(content.sections):
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
        footer_layout.addStretch(1)
        close_action = QPushButton(text("common.close"))
        close_action.setObjectName("informationCloseAction")
        close_action.setFixedWidth(88)
        close_action.clicked.connect(self.accept)
        footer_layout.addWidget(close_action)
        surface_layout.addWidget(footer)


class AboutDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "about")


class PolicyDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "policy")


class TermsOfServiceDialog(InformationDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, "terms")
