### 5. Private key chưa được bảo vệ đúng trên Windows

Project được lưu cạnh executable tại [settings.py](D:/Projects/activo/license_admin/settings.py:19), không phải vị trí phù hợp cho dữ liệu mutable và secret.

Kiểm tra ACL thực tế của `private.pem` cho thấy nhóm `Everyone` có quyền đọc. `chmod(0600)` trong [key_store.py](D:/Projects/activo/license_admin/key_store.py:209) không đảm bảo Windows DACL được giới hạn đúng.

Nên:

- Dữ liệu app: `%LOCALAPPDATA%\Vendor\App`.
- Secret: Windows Credential Manager hoặc DPAPI.
- Nếu vẫn lưu file, đặt DACL chỉ cho user hiện tại.
- Tách key identity khỏi project metadata.
- Có key ID, created time, rotated time, revoked time.
- Có quy trình rotate/re-sign/migrate rõ ràng.

### 6. “Revoke” chưa thực sự revoke license đã phát hành

Hiện revoke chủ yếu xóa record local tại [main_window.py](D:/Projects/activo/license_admin/main_window.py:1159). JWT đã phát hành vẫn có thể hợp lệ đến ngày hết hạn nếu client không kiểm tra feed mới.

Ngoài ra, feed CSV không có manifest version/freshness/tombstone. Một feed cũ có thể bị replay.

Cần đổi mô hình thành:

- `Active → Revocation pending → Revoked → Published`
- Signed manifest chứa revision, generated-at, expiry/freshness window.
- Danh sách revoked/tombstone rõ ràng.
- Client từ chối manifest bị rollback.
- Không hiển thị “Revoked” như đã hoàn thành nếu chưa publish thành công.

### 7. Binary chưa đạt chuẩn phát hành Windows

Bản build PyInstaller chạy thành công, nhưng:

- `LicenseAdmin.exe` hiện **NotSigned**.
- Windows VersionInfo trống: ProductName, CompanyName, FileVersion, ProductVersion, Copyright.
- Không có quy trình installer, update hoặc rollback.
- Dependency chưa lock reproducibly.
- Không thấy CI release, SBOM hoặc third-party notice.

Trước release cần:

- Nhúng multi-resolution `.ico` vào EXE/installer. Taskbar và Explorer phải dùng asset local được đóng gói, không thể phụ thuộc URL Icons8 lúc runtime.
- Thêm VersionInfo và application version.
- Ký EXE/installer bằng SHA-256 và trusted timestamp theo [Microsoft SignTool](https://learn.microsoft.com/windows/win32/seccrypto/signtool) và [Authenticode timestamping](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures).
- Lock dependency; PyPA đã có specification cho [reproducible lock files](https://packaging.python.org/en/latest/specifications/pylock-toml/).
- Sinh checksum và SBOM cho từng release.
- Test clean install, upgrade, downgrade và uninstall.

### 8. Docker configuration không nên đưa ra Internet

Cấu hình hiện tại bind cổng `6080` rộng và có thể chạy noVNC không password khi biến môi trường không được đặt tại [docker-compose.yml](D:/Projects/activo/docker-compose.yml:5) và [start-desktop.sh](D:/Projects/activo/docker/start-desktop.sh:34).

Không nên coi đây là production deployment:

- Fail closed nếu thiếu password.
- Bind localhost mặc định.
- Dùng TLS/reverse proxy.
- Không dùng desktop/noVNC như backend multi-user.
- Pin base image bằng digest và tách dev dependency khỏi runtime image.

---

## Đánh giá UI/UX chi tiết

### Những phần đã làm tốt

- Dark theme có visual hierarchy rõ.
- Header controls khá đồng nhất về chiều cao.
- Sidebar, metric cards và table có density hợp lý cho admin desktop.
- Status dùng cả text và màu, không chỉ phụ thuộc màu.
- About/Policy/Terms đã dùng chung một modal shell khá ổn.
- Contact chỉ xuất hiện trong About là đúng.
- Tab order chính tương đối logic.
- Code đã có một số component tái sử dụng tốt như `ProjectSelector`, `PopoverSelect`, `ThemeToggle`, `InformationDialog`.

### Ba button About/Policy/Terms vẫn chưa phải pattern tốt

Nhóm ba icon nhìn giống segmented selector hoặc mode switch, trong khi đây là ba action độc lập. Chúng cũng tiêu tốn không gian header và sẽ khó scale nếu sau này thêm Help, Changelog, Diagnostics hoặc Updates.

Khuyến nghị tốt nhất:

- Một button `Help / Info` duy nhất ở header.
- Popover có item kèm text:
  - About
  - Privacy & Transparency
  - Terms of Service
- Mỗi item vẫn mở modal riêng nhưng dùng chung shell.
- Contact chỉ ở About.
- About thêm version, build channel, publisher, license attribution và “Copy diagnostics”.

### Keyboard focus gần như vô hình

Runtime render cho thấy primary button, sidebar, project selector, info buttons, theme toggle, table và window controls gần như không thay đổi pixel khi nhận keyboard focus. Chỉ input có focus border tại [theme.py](D:/Projects/activo/license_admin/theme.py:179).

Cần focus ring 2 px, tương phản cao cho mọi interactive control. Table hiện còn đặt `outline: 0`.

### Screen reader metadata thiếu

Các control quan trọng chưa có accessible name đầy đủ:

- Project selector.
- Sidebar collapse toggle.
- Window minimize/maximize/close.
- Search input.
- Collapsed sidebar buttons.
- Browse buttons trong Settings.
- Toast và busy status.

Khi sidebar collapse, text bị xóa nên accessible name cũng mất tại [dashboard_widgets.py](D:/Projects/activo/license_admin/dashboard_widgets.py:42).

Qt hỗ trợ accessibility nhưng ứng dụng phải cung cấp tên, trạng thái và keyboard behavior đầy đủ; xem [Qt Accessibility](https://doc.qt.io/qt-6/accessible.html).

### Hit target window controls quá nhỏ

Window controls có kích thước chỉ khoảng 12×12 tại [window_chrome.py](D:/Projects/activo/license_admin/window_chrome.py:99). Có thể giữ dot 12 px về mặt thị giác, nhưng hit area nên ít nhất 32×32, đồng thời có:

- Glyph khi hover.
- Focus state.
- Accessible name.
- Tooltip.
- Keyboard activation.

Hiện cách dùng traffic-light màu đặt bên phải là một hybrid giữa macOS và Windows, không thật sự native cho nền tảng nào.

### Light theme thiếu contrast

Một số tỷ lệ đo được:

- Inline contact link light theme: khoảng 2.02:1.
- Metric note: khoảng 3.08:1.
- Project ID: khoảng 3.5:1.
- Một số status text: khoảng 2.15–3.76:1.
- Icon xám trên trắng: khoảng 2.23:1.

Ngoài contrast, metadata 8–9 px quá nhỏ. Nên xây semantic palette riêng cho dark/light thay vì dùng cùng một QColor cho cả hai theme.

### Project selector vẫn quá dày nội dung

Button chỉ cao khoảng 32 px nhưng đang cố chứa hai dòng: project name và project ID 8 px. Cách dễ đọc hơn:

- Button chỉ hiển thị project name một dòng.
- Project ID đưa vào tooltip hoặc popover.
- Tên dài phải elide và có tooltip.
- Khi có nhiều project: thêm search, recent, pinned.

### Thiếu các trạng thái UX quan trọng

Table rỗng hiện chỉ là khoảng trống; offscreen render còn thấy dải vertical-header sáng ở empty table.

Cần phân biệt:

- Project chưa setup.
- Không có license.
- Không có kết quả search.
- Load thất bại.
- Key sai.
- Sync lỗi.
- Offline.
- Permission denied.

Mỗi trạng thái cần message và CTA đúng ngữ cảnh, ví dụ `Create license`, `Import`, `Open Settings`, `Retry`, `Restore backup`.

### Busy state không cung cấp thông tin

`_run_operation()` truyền message, nhưng `_set_busy()` bỏ qua message tại [main_window.py](D:/Projects/activo/license_admin/main_window.py:1439). Người dùng chỉ thấy wait cursor và một số control bị disable.

Nên có persistent operation bar:

- “Pulling 1,284 licenses…”
- Bước hiện tại.
- Elapsed time.
- Cancel nếu an toàn.
- Retry khi lỗi.
- Accessibility status announcement.

### Layout chưa responsive

Main window có minimum 980×640, top bar và metric cards dùng nhiều fixed size tại [main_window.py](D:/Projects/activo/license_admin/main_window.py:111). Information modal, Settings và import dialog cũng có minimum size lớn.

Ở Windows 150–200% scaling hoặc màn hình 1024×768 sẽ dễ overflow. Qt hỗ trợ high-DPI, nhưng layout vẫn cần breakpoint và scroll container; xem [Qt High DPI](https://doc.qt.io/qt-6/highdpi.html).

### Localization chưa hoàn chỉnh

App hỗ trợ 7 locale, nhưng nội dung About/Policy/Terms chỉ có English và Vietnamese; năm ngôn ngữ còn lại âm thầm fallback sang English tại [information_dialogs.py](D:/Projects/activo/license_admin/information_dialogs.py:190).

Đối với policy/terms, silent fallback làm giảm độ tin cậy. Ít nhất phải hiển thị rõ “This document is currently available in English”, hoặc dịch đầy đủ trước release.

---

## Khả năng scale

### Desktop một người dùng

Sau khi sửa P1, kiến trúc hiện tại có thể phục vụ hợp lý khoảng vài nghìn license/project.

Nhưng giới hạn cấu hình đang không nhất quán:

- Max rows khai báo 100.000.
- File cap chỉ 5 MiB tại [limits.py](D:/Projects/activo/license_admin/limits.py:3).
- Với token thực tế hiện tại, dung lượng khả dụng chỉ khoảng 6.000–7.000 rows.

Đo filter tổng hợp trên máy hiện tại:

- 1.000 rows: khoảng 32 ms/query.
- 5.000 rows: khoảng 151 ms/query.
- 10.000 rows: khoảng 301 ms/query.

Filter chạy trên mỗi ký tự và scan cả username, HWID, JTI và token tại [qt_models.py](D:/Projects/activo/license_admin/qt_models.py:109). 300 ms mỗi keystroke đã tạo cảm giác lag rõ.

Cần debounce 150–250 ms, cache normalized fields và không search toàn bộ JWT nếu không thật sự cần.

### 10.000–50.000 records

Nên chuyển storage local sang:

- SQLite.
- WAL mode.
- Schema migration.
- Indexed fields.
- Pagination hoặc incremental model.
- Background query.
- Audit/event table.
- Backup snapshot.

Không nên tiếp tục load, verify, sort và serialize toàn bộ CSV cho mỗi thao tác.

### Multi-user hoặc nhiều máy

Google Sheets không nên là source of truth. Nó chỉ nên là publication/export adapter.

Kiến trúc phù hợp hơn:

`Desktop client → authenticated API → PostgreSQL → KMS/HSM → audit/outbox → Sheets publication adapter`

Cần thêm:

- Authentication.
- RBAC.
- Optimistic concurrency.
- Server-side signing.
- Idempotency key.
- Immutable audit.
- Tenant/project isolation.
- Rate limiting.
- Database migration.
- Backup/PITR.
- Metrics và alerting.

---

## Các tính năng nên bổ sung

### Bắt buộc trước production

- Automatic versioned backup và restore.
- Startup recovery mode.
- Single-instance/project lock.
- Atomic Settings transaction.
- Sync diff, remote revision và conflict resolution.
- Immutable audit log.
- Secure key storage và key rotation.
- Operation progress/cancel/retry.
- Signed, versioned release artifacts.
- Crash log và diagnostic bundle.
- Signed/versioned revocation feed.

### Nên có cho production UX

- First-run setup checklist.
- Empty/error/no-result/offline states.
- Inline validation, tự chuyển tới field lỗi.
- Notification center thay cho toast 3.8 giây.
- Persist window geometry, sidebar state, column order/width và filter.
- System theme và high-contrast support.
- Clipboard auto-clear cho license/token.
- Searchable project switcher.
- Column chooser và priority-based responsive columns.
- `Ctrl+F`, shortcut help.
- Copy diagnostics trong About.
- Bundle flag assets thay vì tự tải từ CDN.

### Sau khi nền tảng ổn định

- Auto-update có signed manifest và rollback.
- Project archive/trash thay vì delete ngay.
- Dashboard audit/history.
- Scheduled key rotation reminder.
- Health check cho Sheet credentials và key pair.
- Export support bundle đã loại bỏ secret.
- Backend/API nếu có nhiều operator.

---

## Privacy, license và minh bạch

JWT hiện là signed nhưng không encrypted; username, HWID và các claim khác có thể đọc được tại [issue_license.py](D:/Projects/activo/license_admin/issue_license.py:131). Policy nên nói rõ:

- Trường dữ liệu nào được nhúng trong token.
- Token/feed có thể được publish ở đâu.
- Retention.
- Clipboard behavior.
- Third-party processor như Google Sheets.
- Cách yêu cầu xóa/cập nhật dữ liệu.

Logo Icons8: nếu dùng theo license miễn phí, license của Icons8 yêu cầu attribution/link phù hợp; nên thêm “App icon by Icons8” trong About hoặc lưu bằng chứng paid license. Xem [Icons8 licensing](https://icons8.com/license).

PySide6 có các lựa chọn LGPLv3/GPLv3/commercial; cần xác định mô hình phát hành và cung cấp LICENSE/NOTICE tương ứng, không chỉ để dependency trong requirements. Xem [Qt for Python licensing](https://doc.qt.io/qtforpython-6/).

---

## Kiến trúc nên tách lại

[main_window.py](D:/Projects/activo/license_admin/main_window.py:95) hiện khoảng 1.500 dòng và đang gánh UI, project lifecycle, persistence, sync, validation, dialogs và notifications.

Nên tách thành:

- `MainWindowShell`: chỉ layout/navigation.
- `ProjectSession`: active project và lifecycle.
- `LicenseApplicationService`: create/edit/revoke/import.
- `LicenseRepository`: persistence abstraction.
- `SyncCoordinator`: pull/push/conflict state machine.
- `KeyManagementService`.
- `OperationController`: progress/cancel/error mapping.
- `SettingsTransaction`.
- `AuditService`.

UI không nên trực tiếp mutate record hoặc ghi file. Tất cả mutation phải đi qua application service có transaction boundary.
