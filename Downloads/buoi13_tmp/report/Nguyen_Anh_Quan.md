# Báo Cáo Cá Nhân - Nguyễn Anh Quân

## Thông Tin Cá Nhân

| Trường | Giá Trị |
|--------|---------|
| Họ và Tên | Nguyễn Anh Quân |
| MSSV | 2A202600132 |
| Vai Trò | Logging + PII + Middleware |
| Nhóm | Day13_Group06_E402 |

---

## 1. Tổng Quan Phần Việc

Trong bài lab Day 13, tôi đảm nhận phần **Logging, PII Scrubbing và Middleware**. Mục tiêu chính là đảm bảo mỗi HTTP request được gắn một correlation ID duy nhất, tất cả log events được xuất ra theo định dạng JSON schema chuẩn, và các dữ liệu nhạy cảm (PII) được tự động che đi trước khi ghi log.

---

## 2. Chi Tiết Phần Việc Đã Thực Hiện

### 2.1. Middleware - Correlation ID (`app/middleware.py`)

**Mục tiêu:** Mỗi request HTTP phải có một `correlation_id` (hay `request_id`) duy nhất, được propagate xuyên suốt từ lúc request đến cho đến khi response được trả về.

**Cách hoạt động:**

Tôi đã đọc và hiểu `CorrelationIdMiddleware` trong `app/middleware.py`. Đây là một `BaseHTTPMiddleware` của Starlette, hoạt động theo cơ chế:

1. **Tạo Correlation ID:**
   - Kiểm tra header `x-request-id` trong request. Nếu có, dùng giá trị đó.
   - Nếu không có, tạo mới một UUID hex (36 ký tự) bằng `uuid.uuid4().hex`.
2. **Bind context vars:**
   - Dùng `bind_contextvars` từ `structlog` để gắn các thông tin vào context của request hiện tại:
     - `correlation_id`, `request_id`: ID duy nhất của request.
     - `http_method`: GET, POST, ...
     - `path`: Đường dẫn URL.
     - `client_ip`: IP của client.
     - `user_agent`: User-Agent header.
3. **Đo thời gian:**
   - Dùng `time.perf_counter()` để đo thời gian xử lý request.
4. **Trả về response:**
   - Thêm header `x-request-id` vào response để client có thể trace.
   - Thêm header `x-response-time-ms` để client biết thời gian xử lý.

**Code minh họa (tóm tắt logic chính):**

```python
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()  # Reset context cho request mới

        incoming_id = request.headers.get("x-request-id")
        correlation_id = incoming_id or uuid.uuid4().hex

        bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,
            http_method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = str(elapsed_ms)

        return response
```

**Điểm quan trọng:** Nhờ `structlog.contextvars.merge_contextvars`, tất cả các log events được tạo trong suốt vòng đời của một request đều tự động được gắn `correlation_id` mà không cần truyền thủ công.

---

### 2.2. Logging Config - Structured JSON Logging (`app/logging_config.py`)

**Mục tiêu:** Cấu hình structlog để xuất log theo JSON schema chuẩn, đồng thời tách riêng audit events.

**Cách hoạt động:**

Tôi đã đọc và hiểu pipeline xử lý log trong `app/logging_config.py`. Structlog được cấu hình với chuỗi processors sau:

1. **`merge_contextvars`**: Merge các biến context đã bind (correlation_id, user_id_hash, ...) vào mỗi log event.
2. **`add_log_level`**: Thêm trường `level` (info, warning, error, ...).
3. **`TimeStamper`**: Thêm trường `ts` theo định dạng ISO 8601, UTC.
4. **`scrub_event`**: Gọi hàm `scrub_value` để che PII trong event trước khi ghi.
5. **`StackInfoRenderer`** và **`format_exc_info`**: Render stack trace khi có exception.
6. **`AuditLogProcessor`**: Nếu event thuộc nhóm audit events (`request_received`, `response_sent`, `incident_enabled`, `incident_disabled`), ghi vào `data/audit.jsonl`.
7. **`JsonlFileProcessor`**: Ghi tất cả events vào `data/logs.jsonl`.
8. **`JSONRenderer`**: Render event dict thành chuỗi JSON.

**Điểm đáng chú ý:** Audit logs được tách riêng vào `data/audit.jsonl` (bonus point). Điều này giúp tách biệt rõ ràng giữa log nghiệp vụ thông thường và audit log phục vụ compliance.

---

### 2.3. PII Scrubbing (`app/pii.py`)

**Mục tiêu:** Tự động phát hiện và che giấu các dữ liệu nhạy cảm (PII) trong log output.

**Các patterns PII được xử lý:**

| Pattern | Mô Tả | Ví Dụ |
|---------|--------|--------|
| `email` | Email address | `student@vinuni.edu.vn` |
| `cccd` | Căn cước công dân (12 số) | `012345678901` |
| `phone_vn` | Số điện thoại VN | `090 123 4567`, `+84901234567` |
| `credit_card` | Số thẻ tín dụng | `4111-1111-1111-1111` |
| `token` | Bearer token, API key | `sk-abc123...` |
| `api_key` | API key dạng key=value | `api_key=abc123` |

**Ngoài ra, các keys nhạy cảm** như `email`, `phone`, `token`, `api_key`, `secret`, `password`, `authorization`, ... cũng được che giấu theo giá trị.

**Cách hoạt động của `scrub_text`:**
- Duyệt qua tất cả các regex patterns trong `PII_PATTERNS`.
- Thay thế các match bằng nhãn ví dụ: `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`.
- Hỗ trợ đệ quy cho nested objects và lists qua `scrub_value`.

**Các hàm chính:**

- `scrub_text(text)`: Scrub PII trong một chuỗi văn bản.
- `scrub_value(value)`: Scrub PII trong bất kỳ giá trị nào (str, dict, list).
- `_redact_key(key, value)`: Che giấu giá trị nếu key thuộc danh sách `SENSITIVE_KEYS`.
- `hash_user_id(user_id)`: Hash user_id bằng SHA256, lấy 12 ký tự đầu (để trace mà không lộ PII).
- `summarize_text(text, max_len=80)`: Cắt ngắn text, scrub PII, thay newline bằng space.

**Ví dụ scrub:**

```
Input:  "Email me at student@vinuni.edu.vn or call 0901234567"
Output: "Email me at [REDACTED_EMAIL] or call [REDACTED_PHONE_VN]"
```

---

### 2.4. JSON Schema cho Log (`config/logging_schema.json`)

Tôi đã đọc schema yêu cầu trong `config/logging_schema.json`. Mỗi log event phải có các trường bắt buộc:

- `ts`: ISO timestamp.
- `level`: info, warning, error, ...
- `service`: Tên service.
- `event`: Tên event (request_received, response_sent, ...).
- `correlation_id`: UUID của request.

Các trường enrichment (tùy chọn, tùy loại event):
- `env`, `user_id_hash`, `session_id`, `feature`, `model`.
- `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`.
- `error_type`, `tool_name`, `payload`.

---

## 3. Test và Validation

### 3.1. Chạy pytest

```bash
pytest tests/test_pii.py -v
```

Tôi đã chạy các test cases trong `tests/test_pii.py`:

- `test_scrub_email`: Kiểm tra email được redact thành `[REDACTED_EMAIL]`.
- `test_scrub_phone_and_id`: Kiểm tra phone VN và CCCD được redact.
- `test_scrub_nested_values`: Kiểm tra scrub đệ quy trong dict và list.

**Kết quả:** Tất cả tests passed.

### 3.2. Chạy validate_logs.py

```bash
python scripts/validate_logs.py
```

Script này kiểm tra:
- Các trường bắt buộc (`ts`, `level`, `event`) có trong mỗi log.
- `correlation_id` có trong mỗi API request log.
- Các trường enrichment (`user_id_hash`, `session_id`, `feature`) có trong mỗi API request log.
- Không có PII leak (không có `@` hay `4111` trong raw JSON log).

**Kết quả:** Score = 100/100.

---

## 4. Evidence - Minh Chứng Công Việc

| Evidence | Mô Tả | File |
|----------|--------|------|
| Correlation ID | Mỗi request có UUID duy nhất | `data/logs.jsonl` |
| PII Redacted | Email, phone, CCCD được redact | `data/logs.jsonl` |
| JSON Schema | Log theo schema chuẩn | `data/logs.jsonl` |
| Audit Logs | Events được tách vào file riêng | `data/audit.jsonl` |
| Test Passed | Pytest chạy thành công | `tests/test_pii.py` |

---

## 5. Bài Học và Kiến Thức Rút Ra

### 5.1. Tại sao cần Correlation ID?

Trong một hệ thống phân tán (distributed system), một request có thể đi qua nhiều services khác nhau (API Gateway, Auth Service, RAG Service, LLM Service, ...). Không có correlation ID, rất khó để trace một request cụ thể xuyên qua tất cả các logs của các services khác nhau.

Correlation ID giống như một "sợi chỉ đỏ" (red thread) xuyên suốt tất cả logs, giúp:
- **Debugging nhanh hơn:** Tìm tất cả log events liên quan đến một request chỉ bằng một lệnh grep.
- **Distributed tracing:** Khi kết hợp với Langfuse, correlation ID giúp reconstruct waterfall của một request.
- **Incident analysis:** Khi xảy ra incident, correlation ID giúp tách biệt rõ request bị lỗi với các request bình thường.

### 5.2. Tại sao cần PII Scrubbing?

Log files thường được lưu trữ ở nhiều nơi: local disk, cloud storage, SIEM systems, hoặc được gửi qua third-party monitoring tools. Nếu PII lọt vào log mà không được che:
- **Vi phạm GDPR, PDPD:** Lưu trữ và xử lý dữ liệu cá nhân mà không có consent là bất hợp pháp.
- **Rủi ro bảo mật:** Nếu log storage bị leak, toàn bộ PII của users bị lộ.
- **Chi phí tuân thủ:** Phạt GDPR có thể lên tới 4% doanh thu toàn cầu hoặc €20 triệu.

### 5.3. Regex Patterns cho PII

Tôi hiểu cách các regex patterns được xây dựng:
- `cccd`: `\b\d{12}\b` - Đúng 12 chữ số liên tiếp (CCCD VN).
- `phone_vn`: `(?:\+84|0)(?:[ .-]?\d){8,10}` - Bắt đầu bằng +84 hoặc 0, theo sau 8-10 chữ số (có thể có dấu cách hoặc dấu chấm ở giữa).
- `credit_card`: `\b(?:\d{4}[- ]?){3}\d{4}\b` - 16 chữ số chia thành 4 nhóm 4 (có hoặc không có dấu ngăn cách).

---

## 6. Tự Đánh Giá

| Tiêu Chí | Điểm Max | Tự Đánh Giá | Ghi Chú |
|----------|----------|-------------|---------|
| Hiểu Logging Pipeline | 5 | 5 | Giải thích được structlog processors |
| Middleware hoạt động | 5 | 5 | Correlation ID xuyên suốt |
| PII Scrubbing đúng | 5 | 5 | Không có PII leak |
| Audit Logs tách riêng | 2 | 2 | Bonus - data/audit.jsonl |
| Test Passed | 3 | 3 | pytest không lỗi |
| **Tổng** | **20** | **20** | |

