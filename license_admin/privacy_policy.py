"""Privacy disclosures audited against token, feed, storage and clipboard code."""

from __future__ import annotations


# This is a disclosure contract, checked against a token issued by the real signer.
LICENSE_TOKEN_CLAIMS = ("username", "hwid", "jti", "iat", "exp", "iss", "aud")

_CLAIM_DESCRIPTIONS = {
    "en": (
        "the operator-supplied customer name or identifier",
        "the device identifier supplied to the application",
        "a unique license identifier",
        "the issue time",
        "the expiry time",
        "the configured issuer",
        "the configured product/audience",
    ),
    "vi": (
        "tên hoặc mã khách hàng do người vận hành nhập",
        "mã thiết bị được cung cấp cho ứng dụng",
        "mã định danh duy nhất của license",
        "thời điểm phát hành",
        "thời điểm hết hạn",
        "issuer đã cấu hình",
        "sản phẩm/audience đã cấu hình",
    ),
}


def _claims(language: str) -> str:
    return "; ".join(
        f"{name} ({description})"
        for name, description in zip(LICENSE_TOKEN_CLAIMS, _CLAIM_DESCRIPTIONS[language], strict=True)
    )


PRIVACY_SECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "en": (
        (
            "Data stored locally",
            "The operator chooses the storage locations for project settings, signing keys, Google credentials, license records and revocation journals. License records contain HWIDs and tokens; revocation journals can retain the username, HWID, license identifier, revocation time and publication state. License CSV files, journals and exported feeds are not encrypted by this application. License Admin does not include advertising or behavioral analytics.",
        ),
        (
            "Readable license tokens",
            "License JWTs are signed with RS256, not encrypted. Anyone with a token can decode its header and payload without a private key. The signature allows verification of the issuer and integrity; it does not hide personal data. Tokens created by this version contain: "
            + _claims("en")
            + ". Times are UTC Unix timestamps. The header also contains alg, typ and kid (the signing-key identifier). Imported tokens may contain additional claims, which remain readable when copied or exported.",
        ),
        (
            "Feed contents and publication destinations",
            "Export writes a signed CSV feed to the file you choose. Sync writes the feed to the configured Google Sheet, including temporary staging worksheets during publication. License rows contain HWID, token and JTI; revocation rows contain HWID, JTI when available and revoked_at. The readable signed manifest includes issuer, audience, schema, revision, generation/expiry times, record counts and content hashes. Exported files can be distributed wherever you place them. If its owner grants public access or publishes it to the web, a Sheet's feed may be readable through a public CSV URL, subject to account and sharing settings. License Admin does not enable Google's public sharing or Publish to web setting for you; the owner controls those settings.",
        ),
        (
            "Third-party services",
            "Operator-requested Sheet actions send authentication requests and, when syncing, feed data to Google services. Google processes that data under the configured account, sharing settings and its applicable policies. Reading a public feed contacts the configured URL's host. FlagCDN flag icons may be downloaded automatically at startup when not cached; those requests reveal the requested flag codes and normal network metadata, such as the IP address, but do not include license records or signing credentials.",
        ),
        (
            "Retention and historical copies",
            "The application has no automatic retention period or age-based purge for license records, revocation journals, their versioned .backups, or exported feeds. Expiry, renewal and revocation do not automatically erase historical copies. The operator manages retention and removal of local files, exports and backups. Google and any other host or recipient control retention of their own copies, caches and version history. Changing the current feed cannot guarantee removal of copies already downloaded or shared.",
        ),
        (
            "Clipboard behavior",
            "Copy HWID and Copy token write the selected value to the operating-system clipboard when you invoke them. Copy diagnostics writes app/runtime/display information only, excluding credentials, project paths and license records. Normal text copy/paste also uses the system clipboard. License Admin does not monitor the clipboard in the background or automatically clear copied data on a timer or on exit. Other applications, clipboard history and clipboard synchronization may access or retain it according to your system settings; manage those copies through the operating system.",
        ),
        (
            "Signing keys and credentials",
            "Signing keys and service-account private keys are used locally for signing or authentication. They are not included in license/feed payloads or exported project settings. On Windows, keys and credentials installed through the application's import flow are protected for the current user. This protection does not modify selected source files or encrypt license records; JWT signing does not make records confidential.",
        ),
        (
            "Requests to update or remove data",
            "Contact the license issuer or project owner who manages your record, identify the affected license/project and describe the correction or removal requested. Do not send private keys or credentials. The operator can use Renew / edit to issue a corrected token, then review and sync the updated feed. A removal request requires review of local records, revocation journals, .backups, exports, Sheet sharing/publication and any provider-held copies; there is no one-click erasure across these locations. Revocation controls access and retains a tombstone; it is not data erasure. Preserve revocation enforcement when handling removal. For questions about this application's behavior, use Contact in About; application support cannot directly erase an issuer's locally managed records.",
        ),
        (
            "Transparency and notice changes",
            "This notice describes the application's current behavior and was updated on 4 October 2026. We aim to make network actions explicit and update the notice when data handling materially changes. The operator remains responsible for choosing what customer information to place in tokens and for reviewing access to each publication destination.",
        ),
    ),
    "vi": (
        (
            "Dữ liệu lưu cục bộ",
            "Người vận hành chọn vị trí lưu cấu hình project, khóa ký, credential Google, bản ghi license và journal thu hồi. Bản ghi license chứa HWID và token; journal thu hồi có thể giữ username, HWID, mã license, thời điểm thu hồi và trạng thái publish. File CSV license, journal và feed xuất ra không được ứng dụng này mã hóa. License Admin không tích hợp quảng cáo hay phân tích hành vi.",
        ),
        (
            "Token license có thể đọc được",
            "JWT license được ký bằng RS256, không được mã hóa. Bất kỳ ai có token đều có thể đọc phần header và payload bằng cách decode Base64url mà không cần private key. Chữ ký cho phép xác minh bên phát hành và tính toàn vẹn; không che giấu dữ liệu cá nhân. Token do phiên bản này tạo chứa: "
            + _claims("vi")
            + ". Thời gian dùng Unix timestamp UTC. Header còn chứa alg, typ và kid (mã khóa ký). Token được import có thể chứa claim bổ sung; chúng vẫn đọc được khi sao chép hoặc xuất.",
        ),
        (
            "Nội dung feed và nơi publish",
            "Thao tác xuất ghi feed CSV đã ký vào file bạn chọn. Đồng bộ ghi feed lên Google Sheet đã cấu hình, bao gồm worksheet staging tạm thời trong quá trình publish. Dòng license chứa HWID, token và JTI; dòng thu hồi chứa HWID, JTI nếu có và revoked_at. Manifest đã ký vẫn đọc được, gồm issuer, audience, schema, revision, thời điểm tạo/hết hạn, số bản ghi và hash nội dung. File export có thể được phân phối tại nơi bạn đưa lên. Nếu chủ sở hữu cấp quyền truy cập công khai hoặc publish Sheet lên web, feed có thể đọc được qua URL CSV công khai, tùy thiết lập tài khoản và chia sẻ. License Admin không tự bật quyền chia sẻ công khai hay Publish to web của Google; chủ sở hữu kiểm soát các thiết lập đó.",
        ),
        (
            "Dịch vụ bên thứ ba",
            "Thao tác Sheet do người vận hành yêu cầu gửi request xác thực và, khi đồng bộ, dữ liệu feed tới dịch vụ Google. Google xử lý dữ liệu theo tài khoản đã cấu hình, quyền chia sẻ và chính sách áp dụng của họ. Đọc feed công khai sẽ kết nối host của URL đã cấu hình. Icon cờ FlagCDN có thể tự tải lúc khởi động nếu chưa được cache; request thể hiện mã cờ được yêu cầu và thông tin mạng thông thường như địa chỉ IP, nhưng không chứa bản ghi license hay credential ký.",
        ),
        (
            "Thời gian lưu và bản sao lịch sử",
            "Ứng dụng không đặt thời hạn lưu tự động hay tự xóa theo tuổi dữ liệu đối với bản ghi license, journal thu hồi, các bản sao có phiên bản trong .backups hoặc feed export. Hết hạn, gia hạn và thu hồi không tự xóa bản sao lịch sử. Người vận hành quản lý việc lưu và xóa file local, export và backup. Google cùng các host hoặc bên nhận khác kiểm soát thời gian giữ bản sao, cache và lịch sử phiên bản của họ. Thay đổi feed hiện tại không bảo đảm xóa được bản sao đã tải xuống hoặc chia sẻ.",
        ),
        (
            "Hành vi clipboard",
            "Sao chép HWID và Sao chép token ghi giá trị được chọn vào clipboard hệ điều hành khi bạn gọi thao tác đó. Sao chép chẩn đoán chỉ ghi thông tin ứng dụng, môi trường chạy và màn hình; không gồm credential, đường dẫn project hay bản ghi license. Sao chép/dán văn bản thông thường cũng dùng clipboard hệ thống. License Admin không theo dõi clipboard ở nền và không tự dọn dữ liệu đã sao chép theo timer hoặc khi thoát. Ứng dụng khác, lịch sử clipboard và đồng bộ clipboard có thể truy cập hoặc giữ dữ liệu theo thiết lập hệ thống; hãy quản lý các bản sao đó qua hệ điều hành.",
        ),
        (
            "Khóa ký và credential",
            "Khóa ký và private key của service account được dùng cục bộ để ký hoặc xác thực. Chúng không nằm trong payload license/feed hay file cấu hình project được xuất. Trên Windows, khóa và credential được cài qua luồng import của ứng dụng được bảo vệ cho user hiện tại. Cơ chế này không sửa file nguồn đã chọn hay mã hóa bản ghi license; chữ ký JWT không giữ bí mật nội dung bản ghi.",
        ),
        (
            "Yêu cầu cập nhật hoặc xóa dữ liệu",
            "Liên hệ bên phát hành license hoặc chủ project đang quản lý bản ghi của bạn, xác định license/project liên quan và mô tả nội dung cần sửa hoặc xóa. Không gửi private key hay credential. Người vận hành có thể dùng Gia hạn / sửa để phát hành token đã cập nhật, rồi kiểm tra và đồng bộ feed mới. Yêu cầu xóa cần rà soát bản ghi local, journal thu hồi, .backups, export, quyền chia sẻ/publish Sheet và bản sao do nhà cung cấp giữ; không có thao tác xóa một lần cho tất cả vị trí. Thu hồi kiểm soát quyền truy cập và giữ tombstone; không đồng nghĩa xóa dữ liệu. Cần duy trì hiệu lực thu hồi khi xử lý yêu cầu xóa. Với câu hỏi về hành vi ứng dụng, dùng Liên hệ trong Giới thiệu; hỗ trợ ứng dụng không thể trực tiếp xóa bản ghi local do bên phát hành quản lý.",
        ),
        (
            "Minh bạch và cập nhật thông báo",
            "Thông báo mô tả hành vi hiện tại của ứng dụng và được cập nhật ngày 04/10/2026. Chúng tôi hướng tới việc thể hiện rõ thao tác mạng và cập nhật thông báo khi cách xử lý dữ liệu thay đổi đáng kể. Người vận hành chịu trách nhiệm chọn thông tin khách hàng đưa vào token và kiểm tra quyền truy cập tại từng nơi publish.",
        ),
    ),
}
