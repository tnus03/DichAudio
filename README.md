# 🎬 DichAudio - Automated Video Translator & Dubber

**DichAudio** là công cụ tự động tải video từ YouTube/TikTok, dịch thuật, lồng tiếng và chỉnh sửa video với nhiều hiệu ứng.

## ✨ Tính năng

| Tính năng | Mô tả |
|-----------|-------|
| 🌐 **Dịch đa ngôn ngữ** | STT (Whisper) → Dịch (Gemini/OpenAI/DeepSeek) → TTS (gTTS) |
| 🎬 **3 chế độ xử lý** | Video+Âm thanh (dịch đầy đủ), Chỉ video (hiệu ứng), Chỉ âm thanh |
| 🎨 **14+ hiệu ứng video** | Mirror, Speed, Blur, Watermark, Subtitles, Crop, Rotate, Brightness, Contrast, Saturation... |
| 🔊 **Ghép âm thanh** | Thay thế audio track, lồng tiếng vào video khác |
| 🤖 **AI tự động** | Tự động fallback giữa Gemini → DeepSeek → giữ nguyên gốc |
| ☁️ **Upload Cloudinary** | Lưu trữ video thành phẩm trên cloud |
| 🤖 **Telegram Bot** | Quản lý license, kiểm tra trạng thái |

## 🚀 Cài đặt & Chạy

### Yêu cầu
- Python 3.10+
- FFmpeg (cài sẵn hoặc trong PATH)

### Cài đặt

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### Chạy

**Option 1: Web (khuyên dùng)**
```bash
# Terminal 1: Backend
uvicorn server.main:app --host 127.0.0.1 --port 8002

# Terminal 2: WebUI
streamlit run server/webui/app.py --server.port=8501
```

**Option 2: Desktop App (Windows)**
Tải file `DichAudio.exe` từ [Releases](https://github.com/tnus03/DichAudio/releases) và chạy.



## 📸 Giao diện

| Màn hình | Mô tả |
|----------|-------|
| 📥 Dịch URL | Nhập link hoặc upload video + chọn hiệu ứng |
| 🔊 Ghép AV | Upload video + audio riêng → ghép |
| 🎤 Lồng tiếng | URL nguồn (lấy giọng) + video đích |
| 📋 Lịch sử | Danh sách task + retry + nhật ký |

## 🌐 Deploy lên Render (Miễn phí)

1. Push code lên GitHub
2. Vào [Render Dashboard](https://dashboard.render.com) → New Web Service
3. Chọn repo, Runtime: **Docker**
4. Thêm biến môi trường: `GEMINI_API_KEY`, `CLOUDINARY_...`, `TELEGRAM_BOT_TOKEN`
5. Deploy!

> Giữ server luôn thức: https://cron-job.org → ping mỗi 10 phút

## 🔧 API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/v1/translate` | Dịch video từ URL |
| POST | `/api/v1/upload` | Upload video từ máy |
| GET | `/api/v1/tasks` | Danh sách task |
| POST | `/api/v1/merge` | Ghép video + audio |
| POST | `/api/v1/dub-video` | Lồng tiếng vào video |
| POST | `/api/v1/tasks/{id}/retry` | Retry task |
| POST | `/api/v1/license/check` | Kiểm tra license |

## 🛠 Công nghệ

- **Backend:** FastAPI, SQLAlchemy, Celery
- **STT:** faster-whisper
- **Dịch:** Google Gemini, OpenAI, DeepSeek
- **TTS:** gTTS, Edge-TTS
- **Video:** FFmpeg, MoviePy
- **UI:** Streamlit
- **Cloud:** Cloudinary

## 👤 Tác giả

Built by [@tnus03](https://github.com/tnus03)
