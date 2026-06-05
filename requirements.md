# Yêu Cầu Hệ Thống — Automated Video Translator & Reup Optimizer

## 1. Tổng Quan
Hệ thống tự động tải video từ TikTok/Douyin/YouTube Shorts, dịch thuật lồng tiếng Việt, chỉnh sửa lách bản quyền và quản lý bản quyền phần mềm qua Telegram Bot.

## 2. Yêu Cầu Chức Năng (Functional Requirements)

### FR-01: Tải Video
- Nhập URL TikTok/Douyin/YouTube Shorts
- Tự động bóc tách & tải video không logo (no-watermark)
- Hỗ trợ tải hàng đợi qua Celery background tasks
- Trả trạng thái real-time về Dashboard

### FR-02: AI Pipeline Xử Lý
- **STT**: faster-whisper hoặc OpenAI Whisper API — nhận diện giọng nói + timestamps
- **Dịch thuật**: Gemini 1.5 Flash API — dịch sát nghĩa, giữ nguyên timestamps, trả JSON
- **TTS**: Edge-TTS — giọng Nam Minh/Hoài Nam, tự động điều chỉnh tốc độ theo duration gốc

### FR-03: Chỉnh Sửa Video & Lách Bản Quyền
- Hạ âm lượng gốc còn 10%, chèn lồng tiếng Việt đúng timestamps
- Lật hình (Mirror) — tuỳ chọn bật/tắt
- Thay đổi tốc độ 1.05x / 1.1x
- Blur padding khi đổi tỷ lệ ngang→dọc
- Chèn watermark logo .png tuỳ chỉnh
- Upload thành phẩm lên Cloudinary

### FR-04: Quản Lý License
- 4 gói: 1 ngày, 1 tháng, 2 tháng, 3 tháng
- Sinh mã Key UUID, lưu vào DB
- Device Lock: khoá key với HWID (MAC/Serial)
- Kiểm tra hạn mỗi khi khởi động / trước khi dịch

### FR-05: Telegram Bot
- Hiển thị gói dịch vụ + thông tin tài khoản
- Nhận ảnh bill → Forward đến Admin Group
- Admin bấm Duyệt/Từ chối → Bot gửi key hoặc thông báo

### FR-06: Frontend Desktop
- Dashboard hiển thị danh sách video + trạng thái
- Checkbox tuỳ chọn chỉnh sửa (Mirror, Speed, Watermark, Blur)
- Nhập URL, theo dõi tiến trình real-time

## 3. Yêu Cầu Phi Chức Năng (Non-Functional Requirements)

### NFR-01: Hiệu Năng
- Xử lý bất đồng bộ (Asyncio + Celery)
- Không block UI khi xử lý video nặng
- Hàng đợi Redis chịu tải concurrent

### NFR-02: Bảo Mật
- Mã hoá HWID khi lưu vào DB
- Key license không thể đoán trước (UUID4)
- Kiểm tra hết hạn trước mọi tác vụ

### NFR-03: Khả Năng Mở Rộng
- Database linh hoạt SQLite (dev) ↔ MySQL (prod)
- Cấu hình qua biến môi trường
- Worker Celery scale ngang

### NFR-04: Độ Tin Cậy
- Xử lý ngoại lệ toàn bộ pipeline — không crash vì lỗi API thứ ba
- Retry mechanism cho API calls
- Ghi log đầy đủ

## 4. Yêu Cầu Công Nghệ (Tech Stack)
- **Backend**: Python 3.11+, FastAPI, Celery, Redis
- **Database**: SQLAlchemy ORM + SQLite/MySQL
- **AI**: faster-whisper, Google Gemini API, Edge-TTS
- **Media**: yt-dlp, FFmpeg
- **Bot**: python-telegram-bot v20+
- **Frontend**: Tauri (React) hoặc PyQt6
- **Cloud**: Cloudinary (lưu video thành phẩm)

## 5. Ràng Buộc
- Mã nguồn Python >= 3.10
- FFmpeg phải được cài sẵn trên hệ thống (PATH)
- yt-dlp phiên bản mới nhất
- Redis server chạy cho Celery broker
