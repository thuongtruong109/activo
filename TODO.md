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
