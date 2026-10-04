# Private Docker desktop — không phải backend production

Image chạy một phiên desktop của **một người vận hành tin cậy**, không cung cấp
API backend, tenant isolation, RBAC hay session riêng cho từng người. Ai điều khiển
desktop có thể dùng khóa ký, Google credential và đọc dữ liệu của mọi project
trong volume. Không đưa noVNC ra Internet hoặc dùng làm dịch vụ multi-user.

## Chạy trên máy riêng

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
# Điền ACTIVO_VNC_PASSWORD: đúng 8 ký tự ASCII ngẫu nhiên, không có dấu cách.
docker compose up -d --build
```

Không ghi đè `.env` đã có. File mẫu cố ý để trống mật khẩu: Compose và cả image
chạy trực tiếp đều từ chối khởi động nếu thiếu/rỗng/sai định dạng, trước khi mở
dịch vụ. Với ký tự `$`, dùng single quotes theo cú pháp `.env` của Compose để giữ
giá trị literal; quotes không thuộc password. Mật khẩu dài của cấu hình cũ cần
thay bằng giá trị mới: không tự động cắt ngắn. Classic VNC chỉ
dùng 8 ký tự và có mật mã yếu theo [RFB RFC 6143 §7.2.2](https://www.rfc-editor.org/rfc/rfc6143#section-7.2.2).
Mật khẩu này **không đủ bảo vệ truy cập từ mạng không tin cậy**; cần lớp xác thực
mạnh riêng và kênh mã hóa.

Mở `http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale` trên cùng máy.
`ACTIVO_PORT` chỉ đổi cổng, không đổi địa chỉ bind `127.0.0.1`.
`ACTIVO_SCREEN` nhận `WIDTHxHEIGHTx16` hoặc `WIDTHxHEIGHTx24` (64..8192 pixels).
Không mở firewall/router cho 6080, không publish 5900. Nếu tự dùng `docker run`,
phải khai báo `-p 127.0.0.1:6080:6080`, không dùng `-p 6080:6080`.

Dùng Docker Engine từ 28 trở lên; Docker cảnh báo bản cũ có thể để máy cùng
L2 truy cập port publish localhost. Loopback không phải authorization: các
process trên host, Docker administrator và container cùng network vẫn phải
được tin cậy. Xem [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/).
Không nối image vào shared network với workload không tin cậy.

## Truy cập từ xa: private tunnel / VPN và HTTPS proxy

Cấu hình mẫu [nginx.conf.example](../docker/reverse-proxy/nginx.conf.example)
được include vào `http {}` của **Nginx trên host**. Không bật/public proxy tự động.

1. Chọn hostname private thực, thay cả `server_name` và Origin allowlist cho đúng
   URL HTTPS (gồm port nếu không phải 443); cấu hình DNS/tunnel tương ứng.
2. Cấp certificate TLS được client tin cậy và đặt certificate/key ngoài repository
   tại đường dẫn trong mẫu. Không bỏ qua kiểm tra certificate trong browser.
3. Tạo HTTP credential riêng bằng `htpasswd -B -c /etc/nginx/activo/proxy.htpasswd operator`
   (nhập tương tác); dùng password dài ngẫu nhiên, khác password VNC. Giới hạn quyền
   file chỉ cho administrator và Nginx worker cần đọc. Có thể thay Basic Auth bằng
   authenticated proxy/SSO có MFA, nhưng phải bảo vệ **cả HTML và WebSocket**.
4. Chạy `nginx -t` trước reload. Mẫu chỉ listen `127.0.0.1:8443`; truy cập qua VPN
   gateway/tunnel có kiểm soát, không đổi sang public listener như một deployment
   production. SSH tunnel phải bind loopback phía client và xác minh host key.
5. Browser truy cập URL HTTPS đã cấu hình, xác thực proxy rồi nhập password VNC.
   Không đặt password vào URL. Không mở 6080/5900 qua tunnel công khai.

Proxy dùng TLS 1.2/1.3, xác thực riêng, forward Upgrade cho duy nhất `/websockify`
và kiểm tra Origin chính xác để giảm cross-site WebSocket hijacking. Kênh proxy
→ noVNC là HTTP loopback trên cùng host; proxy ở máy khác phải dùng tunnel mã hóa,
không đổi upstream thành IP public. Xem [Nginx WebSocket proxying](https://nginx.org/en/docs/http/websocket.html).

## Secret, dữ liệu và lifecycle

VNC auth file tạm có quyền `0600`, thư mục runtime `0700`; ứng dụng/X/VNC/proxy
chạy dưới UID 10001. Entrypoint root chỉ validate và chuẩn bị quyền volume rồi
drop privilege. VNC chỉ listen loopback trong container; X không mở TCP.
Password không được log hoặc truyền vào environment của các service con.
Tuy nhiên biến môi trường vẫn có thể bị Docker administrator đọc qua inspect;
`.env` cần quyền chỉ cho người vận hành, không commit/gửi log `compose config`
hoặc `docker inspect` có environment. Docker daemon/host là trust boundary.

Volume `activo-data` chứa `/data/projects`, settings và cache, có thể chứa private
key và Google credential. Trên Linux không có Windows DPAPI: phải bảo vệ host,
volume và backup bằng quyền truy cập, encryption at rest và quản lý khóa phù hợp.
`docker compose down` giữ dữ liệu; **`down -v` xóa volume**, không dùng để update.
Backup nhất quán khi ứng dụng dừng; test restore vào volume riêng trước nâng cấp.
`/tmp` là tmpfs trong Compose, không lưu auth file bền vững và tránh X socket cũ
sau restart. Nếu tự dùng `docker run`, dùng tmpfs tương đương Compose.

Supervisor dừng toàn phiên nếu X, window manager, VNC hoặc websockify chết.
Healthcheck kiểm tra HTTP **và** RFB bắt buộc authentication, không chỉ tải HTML.
Compose `unless-stopped` restart khi process thoát; trạng thái unhealthy riêng
không tự restart. Monitor health và điều tra lỗi; không mở cổng để chữa lỗi kết nối.

## Image và kiểm tra

Base official Python 3.12.15/bookworm được pin bằng manifest digest trong cả hai
stage. Dependency Python runtime dùng lock + hash và binary wheels; build stage
cài vào venv riêng, runtime chỉ copy venv + allowlist source/assets cần chạy.
Không có pytest, mypy, PyInstaller, release tooling, tests, project data hoặc
credential host trong image. Không dùng `COPY . .`.

Pin digest không tự nhận bản vá và **không** làm apt repository/package bit-for-bit
reproducible. Phải định kỳ review base digest/dependency và rebuild/test cập nhật
bảo mật; xem [Docker build best practices](https://docs.docker.com/build/building/best-practices/).
Đã kiểm thử Linux amd64; không suy ra mọi platform trong multi-arch index đều chạy.

```powershell
.venv-release\Scripts\python.exe -m unittest tests.test_container_runtime
docker build --target runtime -t activo-desktop-check .
.venv-release\Scripts\python.exe -m tools.docker.check_runtime --image activo-desktop-check
# Kiểm thử thêm TLS/WSS với Nginx official image đã pin (certificate/password giả):
.venv-release\Scripts\python.exe -m tools.docker.check_runtime --image activo-desktop-check --proxy-image nginx:1.30.5-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
```

Kiểm thử chỉ tạo container/volume tạm riêng, bind host loopback, không dùng `.env`
hoặc volume `activo-data`. Script dọn đúng các container nó tạo kể cả khi lỗi.
