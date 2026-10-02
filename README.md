# License Admin

Ứng dụng desktop độc lập để phát hành và quản lý license RS256 cho nhiều sản
phẩm. License Manager chỉ làm việc với project profile, cặp RSA key, dữ liệu
license cục bộ và Google Sheet.

Ứng dụng không đọc, import hoặc sửa mã nguồn của bất kỳ ứng dụng khách nào.
Ứng dụng khách cũng không cần biết License Manager được đặt ở đâu; hai phía chỉ
cần thống nhất public key, issuer, audience và định dạng feed đã publish.

## Chạy ứng dụng

```powershell
python -m pip install -r requirements.txt
python -m license_admin
```

Trên Windows có thể double-click `run_license_admin.cmd` hoặc
`license_admin_gui.pyw`.

## Quản lý nhiều dự án

Mỗi thư mục `projects/<project-id>/` là một profile độc lập, gồm:

- `project.json`: cấu hình có version riêng của dự án, gồm tên, đường dẫn dữ
  liệu/key, issuer, audience và Google Sheet.
- `private.pem`: khóa ký bí mật, chỉ nằm trên máy quản trị.
- `public.pem`: khóa công khai tương ứng, phải trùng với khóa nhúng trong app.
- `service-account.json`: credential Google riêng của project (nếu dùng đồng bộ
  có quyền ghi).
- `license_admin_data.csv`: dữ liệu quản trị cục bộ.

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
4. cảnh báo nếu cặp key mới làm license hiện có không còn hợp lệ;
5. ghi nguyên tử vào `projects/<project-id>/private.pem` và `public.pem`, có
rollback nếu một bước ghi thất bại.

Bạn cũng có thể trỏ profile tới key ở vị trí khác trong **Cài đặt**; khi lưu,
ứng dụng vẫn xác minh cặp key trước khi chấp nhận. Cách import được khuyến nghị
vì giữ từng project tự chứa và giảm nguy cơ chọn nhầm key.

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

Docker chạy ứng dụng desktop trong màn hình ảo và cung cấp giao diện qua noVNC,
do đó chỉ cần trình duyệt để sử dụng:

```powershell
Copy-Item .env.example .env
# Sửa ACTIVO_VNC_PASSWORD trong .env trước khi chạy
docker compose up -d --build
```

Mở `http://localhost:6080/vnc.html?autoconnect=1&resize=scale`, sau đó nhập mật
khẩu trong `.env`. Có thể đổi cổng bằng `ACTIVO_PORT` và độ phân giải bằng
`ACTIVO_SCREEN`.

Volume `activo-data` giữ toàn bộ project và QSettings tại `/data`, nên rebuild
container không làm mất key, credential, settings, CSV hoặc cache icon ngôn
ngữ. Khi triển khai ra
Internet, đặt dịch vụ sau reverse proxy HTTPS/firewall; không công khai trực
tiếp cổng noVNC. Sao lưu volume này như một kho bí mật vì nó chứa private key
và Google credential.

Để tái sử dụng License Manager cho sản phẩm khác, chỉ cần tạo profile mới và
cấu hình cặp key, claims, Sheet/service account của sản phẩm đó. Không cần và
không nên thêm liên kết mã nguồn giữa License Manager với ứng dụng khách.

## Chức năng

- Xem, tìm kiếm, lọc, sắp xếp và kiểm tra chữ ký toàn bộ license.
- Tạo, gia hạn, sửa và thu hồi license.
- Nhập signed CSV, chuyển đổi legacy CSV và xuất signed CSV.
- Tải/đồng bộ Google Sheet, phát hiện xung đột và format worksheet.
- Hỗ trợ private key PEM có mật khẩu; mật khẩu không được lưu.
- Nhập và xác minh cặp RSA key riêng cho từng project, có chống ghi đè nhầm và
  rollback khi ghi lỗi.
- Nhập Google service-account JSON riêng cho từng project, có kiểm tra cấu trúc
  và private key trước khi lưu.
- Nhập/xuất cấu hình di động mà không trộn key, credential hoặc dữ liệu giữa
  các project.
- Đổi trực tiếp giữa English, Tiếng Việt, Español, 日本語, 中文, 한국어 và
  Português; lựa chọn được lưu lại. Flag được tải bất đồng bộ từ FlagCDN, cache
  cục bộ và có placeholder khi offline.
- Self-host giao diện bằng Docker/noVNC với volume lưu dữ liệu bền vững.

## Bảo mật

`private.pem`, service-account JSON và CSV quản trị đều được `.gitignore`.
Không commit, gửi, đưa lên Drive hoặc đóng gói những file này. Mỗi sản phẩm nên
dùng một cặp RSA key, issuer, audience và Google Sheet riêng.

## CLI

```powershell
python issue_license.py --key projects/my-product/private.pem --username "Customer" --hwid <64-char-hwid> --days 365 --issuer my-product-license-server --audience my-product-desktop
python migrate_license_csv.py --key projects/my-product/private.pem --input legacy.csv --output signed.csv --issuer my-product-license-server --audience my-product-desktop
```
