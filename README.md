# License Admin

Ứng dụng desktop độc lập để phát hành và quản lý license RS256 cho nhiều sản
phẩm. License Manager chỉ làm việc với project profile, cặp RSA key, dữ liệu
license cục bộ và Google Sheet.

Ứng dụng không đọc, import hoặc sửa mã nguồn của bất kỳ ứng dụng khách nào.
Ứng dụng khách cũng không cần biết License Manager được đặt ở đâu; hai phía chỉ
cần thống nhất public key, issuer, audience và định dạng feed đã publish.

## Chạy ứng dụng

```powershell
python -m pip install --require-hashes -r requirements.txt
python -m license_admin
```

Trên Windows có thể double-click `run_license_admin.cmd` hoặc
`license_admin_gui.pyw`.

### Build file EXE trên Windows

Xem [quy trình release Windows](docs/WINDOWS_RELEASE.md) để tạo môi trường đã lock,
build EXE/installer, ký Authenticode, sinh checksum/SBOM và kiểm tra update/rollback.
Build thử nghiệm không ký phải chọn rõ `-Unsigned`; bản production yêu cầu
certificate và trusted timestamp. Không phát hành trực tiếp output PyInstaller
chưa đi qua các bước kiểm tra này.

File `dist/LicenseAdmin.exe` dùng cùng logo với header, cửa sổ, modal, taskbar
và icon hiển thị trong File Explorer. Trên Windows, dữ liệu mutable mặc định
nằm tại `%LOCALAPPDATA%\Activo\LicenseAdmin\projects`, không nằm cạnh executable.
Có thể đặt `ACTIVO_PROJECTS_ROOT` khi cần một root riêng có kiểm soát.

## Quản lý nhiều dự án

Mỗi thư mục `projects/<project-id>/` là một profile độc lập, gồm:

- `project.json`: cấu hình có version riêng của dự án, gồm tên, đường dẫn dữ
  liệu, issuer, audience và Google Sheet; không chứa key ID/lifecycle.
- `private.key` (schema cũ đã migrate) hoặc
  `.settings-assets/<generation>/private.key` (key mới import): khóa ký bí mật
  hiện hành. Trên Windows đây là DPAPI envelope ràng buộc với user đã import,
  không phải PEM plaintext.
- `public.pem`: khóa công khai tương ứng, phải trùng với khóa nhúng trong app.
- `keyring.json`: key ID và lifecycle `created_at`, `rotated_at`, `revoked_at`,
  tách khỏi project metadata và không chứa private-key material.
- `service-account.json`: credential Google riêng của project (nếu dùng đồng bộ
  có quyền ghi).
- `license_admin_data.csv`: dữ liệu quản trị cục bộ.
- `license_admin_data.revocations.json`: journal tombstone và trạng thái publish
  của từng lần thu hồi; file này được commit cùng snapshot active theo cơ chế
  fail-safe (nếu crash giữa hai file thì tombstone thắng).

Chọn **Dự án → Thêm dự án…** để tạo profile mới. Mỗi profile lưu cấu hình độc
lập; chuyển project không dùng lại CSV, key, Sheet, issuer hoặc audience của
project trước. Cửa sổ luôn hiển thị tên profile đang hoạt động để tránh ký nhầm
sản phẩm.

### Nhập key cho một project

Chọn **Dự án → Nhập cặp key…** hoặc nút **Nhập cặp key vào project…** trong
**Cài đặt**. Chọn đồng thời private key và public key nguồn. License Manager sẽ:

1. đọc PEM với giới hạn kích thước an toàn;
2. yêu cầu mật khẩu nếu private key được mã hóa nhưng không lưu mật khẩu;
3. xác minh cả hai đều là RSA từ 2048 bit và thực sự thuộc cùng một cặp;
4. bọc private key bằng DPAPI của current user trên Windows;
5. đặt Windows DACL chỉ cho current user, rồi ghi cặp key theo generation và
   atomically chuyển profile sang generation mới;
6. ghi key ID/lifecycle vào `keyring.json`; public key cũ tiếp tục được License
   Admin tin cậy cho tới khi bị revoke.

Bạn cũng có thể trỏ profile tới key ở vị trí khác trong **Cài đặt**; khi lưu,
ứng dụng vẫn xác minh cặp key trước khi chấp nhận. Cách import được khuyến nghị
vì giữ từng project tự chứa và giảm nguy cơ chọn nhầm key.

### Rotate, ký lại và revoke key

1. Sao lưu project và triển khai public key mới (hoặc cơ chế tin cậy nhiều key)
   tới ứng dụng khách trước khi phát hành token bằng key mới.
2. Chọn **Quản lý project → Nhập cặp key…**. Key cũ được ghi `rotated_at`, key
   mới trở thành active; private key generation cũ không bị ghi đè.
3. Chọn **Dữ liệu → Ký lại license đang hiệu lực…**, kiểm tra số lượng được
   ký lại, rồi push snapshot mới lên Sheet. License hết hạn/lỗi được giữ nguyên.
4. Chỉ sau khi client và feed không còn cần key cũ, chọn **Quản lý project →
   Revoke key đã rotate…**. UI hiển thị số record local còn mang key ID đó và
   yêu cầu xác nhận; thao tác ghi `revoked_at` và loại public key khỏi trust set.

Project schema v1 dùng `private.pem` được migrate khi project được mở: ứng dụng
ghi và verify `private.key` trước, atomically cập nhật profile, siết DACL của
file cũ rồi mới xóa. Lần chạy đầu với dữ liệu legacy cạnh executable sẽ sao
chép sang LocalAppData sau khi siết ACL cho cả bản mới và bản rollback cũ.

DPAPI gắn bản `private.key` đã cài với Windows user/profile. Để phục hồi sang
máy hoặc tài khoản khác, phải giữ một bản PEM nguồn được mã hóa trong kho backup
ngoại tuyến, rồi import lại bằng user đích. Mất cả Windows profile lẫn PEM nguồn
có thể khiến khóa ký không thể phục hồi.

### Nhập Google service account và cấu hình

Trong menu **Quản lý project**:

- **Nhập Google service JSON…** xác minh đúng loại `service_account`, private
  key RSA và `token_uri`, rồi sao chép nguyên tử thành
  `projects/<project-id>/service-account.json`.
- **Nhập cấu hình project…** nhận file settings JSON đã xuất hoặc một
  `project.json` có sẵn. Chỉ tên project, Sheet, worksheet, public URL, issuer
  và audience được áp dụng; ID, key, credential và CSV của project hiện tại
  không bị thay bằng đường dẫn từ project khác.
- **Xuất cấu hình project…** tạo file settings di động, không chứa private key,
  nội dung service account hoặc dữ liệu license.

Trong **Cài đặt → Google Sheets** cũng có nút **Nhập JSON vào project…**. Có
thể tiếp tục trỏ đến file ngoài project, nhưng file vẫn được kiểm tra đầy đủ
trước khi lưu settings.

## Self-host bằng Docker

Docker chỉ dành cho desktop riêng của **một người vận hành tin cậy**, không phải
backend production/multi-user và không được public noVNC ra Internet. Xem
[hướng dẫn bảo mật Docker, TLS proxy và backup](docs/DOCKER_DESKTOP.md).

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
# Điền password VNC đúng 8 ký tự ASCII ngẫu nhiên, không có dấu cách.
docker compose up -d --build
```

Mở `http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale`, sau đó nhập mật
khẩu trong `.env`. Có thể đổi cổng bằng `ACTIVO_PORT` và độ phân giải bằng
`ACTIVO_SCREEN`. Bind host luôn là localhost; thiếu/rỗng/sai định dạng password
thì image từ chối chạy. VNC chỉ dùng 8 ký tự, không thay thế TLS và xác thực mạnh
riêng tại proxy cho truy cập từ xa qua VPN/tunnel.

Volume `activo-data` giữ toàn bộ project và QSettings tại `/data`, nên rebuild
container không làm mất key, credential, settings, CSV hoặc cache icon ngôn
ngữ. Không mở firewall/router cho 6080/5900; `docker compose down -v` sẽ xóa dữ liệu.
Sao lưu volume này như một kho bí mật vì nó chứa private key
và Google credential.

Để tái sử dụng License Manager cho sản phẩm khác, chỉ cần tạo profile mới và
cấu hình cặp key, claims, Sheet/service account của sản phẩm đó. Không cần và
không nên thêm liên kết mã nguồn giữa License Manager với ứng dụng khách.

## Chức năng

- Xem, tìm kiếm, lọc, sắp xếp và kiểm tra chữ ký toàn bộ license.
- Tạo, gia hạn, sửa và thu hồi license.
- Nhập signed CSV, chuyển đổi legacy CSV và xuất signed feed v2.
- Tải/đồng bộ Google Sheet với diff preview, local revision đơn điệu, staged
  publish nguyên tử, revision CAS giữa các License Manager tương thích và
  read-back verification trước khi báo `Synced`.
- Khóa một tiến trình ghi cho mỗi project; mọi mutation xung đột bị vô hiệu hóa
  trong lúc worker đồng bộ đang chạy.
- Hỗ trợ private key PEM nguồn có mật khẩu; mật khẩu không được lưu. Private key
  đã cài được DPAPI bảo vệ theo Windows user và có DACL riêng.
- Nhập và xác minh cặp RSA key riêng cho từng project, có chống ghi đè nhầm và
  rollback khi ghi lỗi.
- Nhập Google service-account JSON riêng cho từng project, có kiểm tra cấu trúc
  và private key trước khi lưu.
- Nhập/xuất cấu hình di động mà không trộn key, credential hoặc dữ liệu giữa
  các project.
- Đổi trực tiếp giữa English, Tiếng Việt, Español, 日本語, 中文, 한국어 và
  Português; lựa chọn được lưu lại. Flag được tải bất đồng bộ từ FlagCDN, cache
  cục bộ và có placeholder khi offline.
- Chuyển nhanh giữa giao diện Light/Dark bằng segmented tab trên header; theme
  được lưu lại cho lần mở tiếp theo.
- Self-host giao diện bằng Docker/noVNC với volume lưu dữ liệu bền vững.

## Bảo mật

`private.key`, PEM nguồn, service-account JSON và CSV quản trị đều được
`.gitignore`.
Không commit, gửi, đưa lên Drive hoặc đóng gói những file này. Mỗi sản phẩm nên
dùng một cặp RSA key, issuer, audience và Google Sheet riêng.

Google Sheets API áp dụng các request trong một `batchUpdate` cùng nhau nhưng
không cung cấp conditional write cho chỉnh sửa thủ công của collaborator. Vì
vậy CAS của ứng dụng bảo vệ các writer License Manager tương thích; nên giới hạn
quyền sửa Sheet và tránh chỉnh trực tiếp worksheet đích trong lúc publish.

### Thu hồi license và signed feed v2

Thu hồi không còn đồng nghĩa với xóa một dòng local. Mỗi license đi qua trạng
thái **Active → Revocation pending → Revoked — publish pending → Published**:

1. thao tác **Thu hồi** ghi tombstone bền vững trước khi bỏ record khỏi danh
   sách active;
2. khi bắt đầu push, tombstone được chuyển sang trạng thái đã chuẩn bị thu hồi;
3. Google Sheet nhận feed qua worksheet staging và một `batchUpdate` nguyên tử;
4. chỉ sau read-back verification thành công, journal mới ghi `Published` cùng
   revision và thời điểm publish. Lỗi mạng, conflict hoặc local revision đổi
   giữa chừng đều không được hiển thị là đã publish/synced.

Feed CSV v2 có các dòng `manifest`, `active` và `revoked`. Manifest RS256 ký
digest của cả danh sách active lẫn tombstone, đồng thời chứa `schema`, revision
đơn điệu, `generated_at`, `exp`, issuer, audience, key ID và số lượng record.
Freshness mặc định là 7 ngày và không được vượt quá 31 ngày. Feed legacy không
có manifest chỉ được hỗ trợ ở đường migration; client bảo mật phải từ chối.

JWT đã phát hành chỉ thực sự bị vô hiệu trên client sau khi client tải một feed
mới còn freshness và thấy HWID hoặc JTI trong tombstone. Client phải fail closed
khi không thể có feed còn hạn theo policy của sản phẩm; không được tiếp tục tin
JWT chỉ vì chữ ký và `exp` của JWT vẫn hợp lệ.

Python client có thể dùng entry point sau để verify chữ ký/freshness, chống
rollback/equivocation bằng revision store bền vững, rồi kiểm tra tombstone:

```python
from pathlib import Path

from license_admin.feed_manifest import (
    ManifestRevisionStore,
    parse_verify_and_accept_feed,
)

feed = parse_verify_and_accept_feed(
    downloaded_csv,
    trusted_public_keys,
    issuer="my-product-license-server",
    audience="my-product-desktop",
    revision_store=ManifestRevisionStore(
        Path(user_data_dir) / "accepted-feed-revision.json"
    ),
)
if feed.is_revoked(hwid=verified_claims["hwid"], jti=verified_claims.get("jti")):
    raise LicenseError("License has been revoked")
```

`accepted-feed-revision.json` phải nằm trong vùng dữ liệu mutable bền vững của
client. Không xóa hoặc rollback file này khi cập nhật ứng dụng, nếu không client
sẽ mất mốc revision cao nhất đã chấp nhận.

## CLI

CLI nhận PEM nguồn do người vận hành quản lý; không trỏ CLI trực tiếp vào
`private.key` vì file đó là DPAPI envelope dành cho License Admin:

```powershell
python issue_license.py --key C:\secure\publisher-private.pem --username "Customer" --hwid <64-char-hwid> --days 365 --issuer my-product-license-server --audience my-product-desktop
python migrate_license_csv.py --key C:\secure\publisher-private.pem --input legacy.csv --output signed.csv --issuer my-product-license-server --audience my-product-desktop
```
