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
