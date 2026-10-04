"""Product documents kept separate from their modal presentation."""

from __future__ import annotations

from dataclasses import dataclass

from license_admin.localization import current_language
from license_admin.privacy_policy import PRIVACY_SECTIONS


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
            ),
        ),
    },
    "policy": {
        "en": InformationContent(
            "Privacy policy",
            "Updated 4 October 2026. This notice explains readable token data, publication destinations, retention, clipboard use and how to request corrections or removal.",
            PRIVACY_SECTIONS["en"],
        ),
        "vi": InformationContent(
            "Chính sách riêng tư & minh bạch",
            "Cập nhật 04/10/2026. Thông báo giải thích dữ liệu đọc được trong token, nơi publish, thời gian lưu, clipboard và cách yêu cầu cập nhật hoặc xóa dữ liệu.",
            PRIVACY_SECTIONS["vi"],
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


def document_content(document: str) -> tuple[InformationContent, bool]:
    translations = _CONTENT[document]
    language = current_language()
    return translations.get(language, translations["en"]), language not in translations
