# -*- coding: utf-8 -*-
"""
DichAudio WebUI — Streamlit Dashboard
Thay thế PyQt6 desktop app, chạy trên trình duyệt.
"""
import hashlib, json, platform, re, subprocess, time, uuid
from pathlib import Path

import requests
import streamlit as st

# ── Cấu hình trang ──
st.set_page_config(
    page_title="DichAudio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://127.0.0.1:8002/api/v1"
CONFIG_FILE = Path.home() / ".dichaudio" / "webui_config.json"

# ── Màu sắc ──
C = {
    "bg": "#0f172a", "card": "#1e293b", "border": "#334155",
    "text": "#e2e8f0", "muted": "#64748b", "accent": "#3b82f6",
    "green": "#22c55e", "red": "#ef4444", "yellow": "#f59e0b",
}


# ── TIỆN ÍCH ──

def get_hwid() -> str:
    components = []
    try:
        if platform.system() == "Windows":
            for cmd, idx in [
                ("wmic cpu get processorid", 1),
                ("wmic baseboard get serialnumber", 1),
                ("wmic diskdrive get serialnumber", 1),
            ]:
                r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=5)
                if r.returncode == 0:
                    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
                    if len(lines) > idx: components.append(lines[idx])
            mac_r = subprocess.run("wmic nic where 'NetEnabled=True' get MACAddress",
                                   capture_output=True, text=True, shell=True, timeout=5)
            if mac_r.returncode == 0:
                for line in mac_r.stdout.strip().split("\n"):
                    m = line.strip()
                    if m and re.match(r"^([0-9A-Fa-f]{2}[:-]){5}", m):
                        components.append(m); break
    except: pass
    if not components: components.append(str(uuid.uuid1().node))
    return hashlib.sha256("|".join(components).encode()).hexdigest()


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text("utf-8"))
        except: pass
    return {}

def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")

def api_call(method: str, path: str, data=None) -> dict:
    url = f"{API_BASE}{path}"
    kwargs = {"timeout": 10}
    if data is not None: kwargs["json"] = data
    try:
        if method == "GET": r = requests.get(url, **kwargs)
        else: r = requests.post(url, **kwargs)
        if r.status_code >= 400:
            return {"error": r.json().get("detail", f"HTTP {r.status_code}")}
        return r.json()
    except requests.ConnectionError:
        return {"error": "Không thể kết nối server (port 8002)"}
    except Exception as e: return {"error": str(e)}


STATUS_ICON = {
    "PENDING": "⏳", "DOWNLOADING": "⬇️", "EXTRACTING_AUDIO": "🎵",
    "TRANSCRIBING": "📝", "TRANSLATING": "🌐", "GENERATING_VOICE": "🗣️",
    "EDITING_AND_MERGING": "🎬", "UPLOADING": "☁️",
    "COMPLETED": "✅", "FAILED": "❌",
}
STATUS_VN = {
    "PENDING": "Chờ xử lý", "DOWNLOADING": "Đang tải video",
    "EXTRACTING_AUDIO": "Tách âm thanh", "TRANSCRIBING": "Nhận diện giọng nói",
    "TRANSLATING": "Đang dịch thuật", "GENERATING_VOICE": "Tạo giọng đọc",
    "EDITING_AND_MERGING": "Ghép video", "UPLOADING": "Đang tải lên",
    "COMPLETED": "Hoàn thành", "FAILED": "Thất bại",
}


# ── CSS ──

st.markdown(f"""
<style>
    .stApp {{ background: {C['bg']}; }}
    .main > div {{ padding: 1rem 2rem; }}
    h1, h2, h3, p, label {{ color: {C['text']} !important; }}
    .st-emotion-cache-1v0mbdj {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 12px; padding: 1.2rem; }}
    .stTextInput>div>div>input {{ background: {C['bg']}; color: {C['text']}; border: 1px solid {C['border']}; }}
    .stSelectbox>div>div {{ background: {C['bg']}; color: {C['text']}; }}
    .stCheckbox {{ color: {C['text']}; }}
    .stButton>button {{ border: none; border-radius: 8px; padding: 0.5rem 1.5rem; font-weight: 600; }}
    .stButton>button[kind="primary"] {{ background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; }}
    .stAlert {{ border-radius: 8px; }}
    div[data-testid="stSidebar"] {{ background: {C['card']}; border-right: 1px solid {C['border']}; }}
    div[data-testid="stSidebar"] .sidebar-content {{ color: {C['text']}; }}
    .task-card {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 1rem; margin-bottom: 0.5rem; }}
    .log-entry {{ color: {C['muted']}; font-size: 0.85rem; font-family: monospace; padding: 2px 0; border-bottom: 1px solid {C['bg']}; }}
    .metric-card {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 1rem; text-align: center; }}
    .metric-value {{ font-size: 1.8rem; font-weight: bold; color: {C['accent']}; }}
    .metric-label {{ font-size: 0.8rem; color: {C['muted']}; }}
    .license-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)


# ── SESSION STATE ──

if "cfg" not in st.session_state:
    st.session_state.cfg = load_config()
if "log" not in st.session_state:
    st.session_state.log = []
if "tasks" not in st.session_state:
    st.session_state.tasks = load_config().get("tasks", [])


def log(msg):
    ts = time.strftime("%H:%M:%S")
    st.session_state.log.insert(0, f"[{ts}] {msg}")
    st.session_state.log = st.session_state.log[:100]


def check_license():
    cfg = st.session_state.cfg
    if not cfg.get("license_key") or not cfg.get("device_id"):
        return None
    return api_call("POST", "/license/check", {
        "license_key": cfg["license_key"],
        "device_id": cfg["device_id"],
    })


# ── SIDEBAR — LICENSE ──

with st.sidebar:
    st.markdown("## 🎬 DichAudio")
    st.markdown("---")

    lic = check_license()
    if lic and lic.get("valid"):
        days = lic.get("remaining_days", 0)
        hours = lic.get("remaining_hours", 0)
        if days >= 1:
            badge_text = f"License: còn {days} ngày"
        elif hours > 0:
            badge_text = f"License: còn {hours} giờ"
        else:
            badge_text = "License: sắp hết hạn"
        st.markdown(f"""
        <div class="license-badge" style="background:#22c55e22;color:#4ade80;border:1px solid #22c55e44;">
            ✅ {badge_text}
        </div>
        """, unsafe_allow_html=True)
    elif lic and "error" in lic:
        st.error(f"⚠️ {lic['error']}")
    else:
        st.warning("🔑 Chưa có license")

    with st.expander("🔑 Kích hoạt License", expanded=not (lic and lic.get("valid"))):
        key_input = st.text_input("License Key", placeholder="XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
                                  label_visibility="collapsed", key="lic_key_input")
        if st.button("Kích hoạt", use_container_width=True, type="primary"):
            if not key_input.strip():
                st.error("Nhập License Key")
            else:
                hwid = get_hwid()
                res = api_call("POST", "/license/activate", {
                    "license_key": key_input.strip(),
                    "device_id": hwid,
                })
                if "error" in res:
                    st.error(res["error"])
                elif res.get("success"):
                    cfg = load_config()
                    cfg.update(license_key=key_input.strip(), device_id=hwid,
                               expired_at=res.get("expired_at"), remaining_days=res["remaining_days"])
                    save_config(cfg)
                    st.session_state.cfg = cfg
                    st.success(f"✅ Còn {res['remaining_days']} ngày")
                    log(f"License activated: {res['remaining_days']} days")
                    st.rerun()

    st.markdown("---")
    st.markdown(f"<div style='color:{C['muted']};font-size:0.8rem;'>📌 Thiết bị: {get_hwid()[:16]}...</div>", unsafe_allow_html=True)

    # ── UPLOAD VIDEO ──
    with st.expander("📤 Tải video lên từ máy", expanded=False):
        uploaded_file = st.file_uploader("Chọn file video", type=["mp4", "avi", "mov", "mkv", "webm"],
            help="Hỗ trợ: MP4, AVI, MOV, MKV, WEBM")
        if uploaded_file is not None:
            if not st.session_state.cfg.get("license_key"):
                st.error("Vui lòng kích hoạt License Key trước")
            else:
                if st.button("📤 Upload và xử lý", use_container_width=True):
                    import requests as req
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {"license_key": st.session_state.cfg["license_key"], "translation_provider": "auto"}
                    with st.spinner("Đang upload..."):
                        try:
                            r = req.post("http://127.0.0.1:8002/api/v1/upload", files=files, data=data, timeout=300)
                            res = r.json()
                            if r.status_code == 200:
                                tid = res["task_id"]
                                log(f"📤 Upload task #{tid}")
                                st.success(f"Upload thành công! Task #{tid}")
                                st.rerun()
                            else:
                                st.error(res.get("detail", str(res)))
                        except Exception as e:
                            st.error(f"Lỗi upload: {e}")

    if st.button("🔄 Làm mới", use_container_width=True):
        st.rerun()


# ── MAIN — 2 cột ──

col1, col2 = st.columns([0.35, 0.65], gap="large")

# ═══ CỘT TRÁI: Tạo task ═══

with col1:
    st.markdown("### 🎥 Dịch video mới")

    url = st.text_input("URL Video",
        placeholder="https://www.tiktok.com/@... / https://www.youtube.com/...",
        label_visibility="collapsed",
        help="Nhập link video từ TikTok, YouTube, Facebook, Douyin, Instagram...")

    opts = st.container(border=True)

    cc1, cc2 = opts.columns(2)
    provider = cc1.selectbox("🤖 AI dịch thuật",
        ["auto", "gemini", "openai", "deepseek"], index=0,
        help="Chọn AI dịch thuật: auto = tự động thử gemini -> deepseek -> giữ nguyên gốc")
    speed = cc2.select_slider("⚡ Tốc độ phát",
        options=[0.5, 0.75, 1.0, 1.05, 1.1, 1.25, 1.5, 2.0], value=1.0,
        help="Tăng/giảm tốc độ video. 1.0x = gốc, 1.05x = nhanh hơn 5% (lách bản quyền)")

    # === BASIC EFFECTS ===
    with opts.expander("📐 Hiệu ứng cơ bản", expanded=True):
        c1, c2, c3, c4 = opts.columns(4)
        mirror = c1.checkbox("🪞 Lật ngang",
            help="Lật gương video theo chiều ngang. Giúp lách bản quyền nội dung.")
        blur = c2.checkbox("🌫️ Làm mờ viền",
            help="Thêm hiệu ứng mờ ở viền khi chuyển tỷ lệ khung hình.")
        wm = c3.checkbox("💧 Chèn logo",
            help="Thêm logo/watemark vào góc video. File logo.png trong thư mục gốc.")
        sub = c4.checkbox("📝 Phụ đề dịch",
            value=True,
            help="Tự động thêm phụ đề tiếng Việt dựa trên bản dịch.")

        if blur:
            blur_intensity = opts.slider("🌫️ Độ mờ viền (sigma)", 1, 50, 10,
                help="Giá trị càng cao, viền mờ càng nhiều. Mặc định: 10")
        else:
            blur_intensity = 10

        if wm:
            wc1, wc2 = opts.columns(2)
            wm_pos = wc1.selectbox("📍 Vị trí logo",
                ["bottom_right", "bottom_left", "top_right", "top_left"],
                help="bottom_right = góc dưới phải, top_left = góc trên trái...")
            wm_scale = wc2.slider("📏 Tỷ lệ logo", 0.01, 0.3, 0.1, 0.01,
                help="Kích thước logo so với video. 0.1 = 10% chiều cao video")
        else:
            wm_pos = "bottom_right"
            wm_scale = 0.1

        if sub:
            sc1, sc2, sc3 = opts.columns(3)
            sub_size = sc1.slider("📏 Cỡ chữ phụ đề", 12, 48, 24,
                help="Kích thước font chữ phụ đề. Mặc định: 24px")
            sub_pos = sc2.selectbox("📍 Vị trí phụ đề",
                ["bottom", "top", "middle"],
                help="bottom = dưới cùng, top = trên cùng, middle = ở giữa")
            sub_color = sc3.selectbox("🎨 Màu chữ",
                ["white", "yellow", "red", "cyan", "lime"],
                help="Màu chữ phụ đề. white = trắng, yellow = vàng...")
        else:
            sub_size, sub_pos, sub_color = 24, "bottom", "white"

    # === ADVANCED EFFECTS ===
    with opts.expander("🎨 Hiệu ứng nâng cao", expanded=False):
        ac1, ac2, ac3 = opts.columns(3)
        brightness = ac1.slider("☀️ Độ sáng", -1.0, 1.0, 0.0, 0.05,
            help="Điều chỉnh độ sáng video. >0 = sáng hơn, <0 = tối hơn")
        contrast = ac2.slider("🌓 Độ tương phản", 0.0, 3.0, 1.0, 0.1,
            help="Độ tương phản màu sắc. 1.0 = gốc, >1 = rõ nét hơn")
        saturation = ac3.slider("🌈 Độ bão hòa", 0.0, 3.0, 1.0, 0.1,
            help="Độ rực rỡ màu sắc. 1.0 = gốc, 0.0 = đen trắng")

        rotate = opts.selectbox("🔄 Xoay video", [0, 90, 180, 270],
            help="Xoay video theo góc: 90 độ, 180 độ (lật ngược), 270 độ")

        cr1, cr2, cr3, cr4 = opts.columns(4)
        crop_t = cr1.number_input("✂️ Cắt trên (px)", 0, 500, 0, step=10,
            help="Số pixel cắt từ phía trên video")
        crop_b = cr2.number_input("✂️ Cắt dưới (px)", 0, 500, 0, step=10,
            help="Số pixel cắt từ phía dưới video")
        crop_l = cr3.number_input("✂️ Cắt trái (px)", 0, 500, 0, step=10,
            help="Số pixel cắt từ bên trái video")
        crop_r = cr4.number_input("✂️ Cắt phải (px)", 0, 500, 0, step=10,
            help="Số pixel cắt từ bên phải video")

    # === AUDIO ===
    with opts.expander("🔊 Âm thanh", expanded=False):
        songs_dir = Path("resource/songs")
        songs = [f.name for f in songs_dir.glob("*") if f.suffix in (".mp3", ".wav", ".m4a")] if songs_dir.exists() else []
        bg_music = opts.selectbox("🎵 Nhạc nền",
            ["Không"] + (songs if songs else []),
            help="Chọn file nhạc nền để thêm vào video. Thêm file MP3 vào resource/songs/")

        if bg_music and bg_music != "Không":
            bg_music_vol = opts.slider("🔉 Âm lượng nhạc nền", 0.0, 1.0, 0.05, 0.05,
                help="Âm lượng nhạc nền. 0.05 = 5% (chỉ đủ nghe nền)")
        else:
            bg_music_vol = 0.05

        orig_vol = opts.slider("🔊 Giữ lại âm thanh gốc", 0.0, 1.0, 0.1, 0.05,
            help="Âm lượng video gốc giữ lại. 0.1 = 10% (để lách bản quyền)")
        dubbed_vol = opts.slider("🎤 Âm lượng giọng dịch", 0.0, 1.0, 1.0, 0.05,
            help="Âm lượng giọng đọc tiếng Việt. 1.0 = 100%")

    if st.button("🚀 Dịch ngay", use_container_width=True, type="primary",
                 help="Bắt đầu xử lý video với các hiệu ứng đã chọn"):
        if not url.strip():
            st.error("Vui lòng nhập URL video")
        elif not st.session_state.cfg.get("license_key"):
            st.error("Vui lòng kích hoạt License Key trước")
        else:
            song_path = ""
            if bg_music and bg_music != "Không":
                song_path = str(songs_dir / bg_music)
            data = {
                "source_url": url.strip(),
                "license_key": st.session_state.cfg["license_key"],
                "options": {
                    "mirror": mirror, "speed": speed,
                    "blur_padding": blur, "blur_intensity": blur_intensity,
                    "watermark_url": "logo.png" if wm else None,
                    "watermark_position": wm_pos, "watermark_scale": wm_scale,
                    "subtitles": sub, "subtitle_font_size": sub_size,
                    "subtitle_position": sub_pos, "subtitle_color": sub_color,
                    "brightness": brightness, "contrast": contrast,
                    "saturation": saturation, "rotate": rotate,
                    "crop_top": crop_t, "crop_bottom": crop_b,
                    "crop_left": crop_l, "crop_right": crop_r,
                    "bg_music": song_path, "bg_music_volume": bg_music_vol,
                    "original_volume": orig_vol, "dubbed_volume": dubbed_vol,
                    "translation_provider": provider,
                },
            }
            with st.spinner("Đang gửi yêu cầu..."):
                res = api_call("POST", "/translate", data)
            if "error" in res:
                st.error(res["error"])
                log(f"Lỗi tạo task: {res['error']}")
            else:
                tid = res["task_id"]
                log(f"✅ Task #{tid} đã được tạo!")
                ts = load_config().get("tasks", [])
                ts.insert(0, {"id": tid, "status": "PENDING", "translated_url": None})
                cfg = load_config(); cfg["tasks"] = ts[:50]; save_config(cfg)
                st.session_state.tasks = ts
                st.success(f"Task #{tid} đã được tạo và đang xử lý!")
                st.rerun()

    st.markdown("### 📋 Hoạt động gần đây")
    log_container = st.container(height=250)
    with log_container:
        for entry in st.session_state.log[:30]:
            st.markdown(f"<div class='log-entry'>{entry}</div>", unsafe_allow_html=True)


# ═══ CỘT PHẢI: Danh sách task ═══

with col2:
    st.markdown("### 📋 Lịch sử dịch")

    # Refresh tasks
    ts = st.session_state.tasks
    if ts:
        changed = False
        for i, t in enumerate(ts):
            tid = t.get("id") or t.get("task_id")
            if not tid: continue
            r = api_call("GET", f"/status/{tid}")
            if "error" not in r:
                old_st = t.get("status")
                if r.get("status") != old_st:
                    log(f"{STATUS_ICON.get(r['status'],'')} Task #{tid}: {STATUS_VN.get(r['status'], r['status'])}")
                    changed = True
                t.update(r)
                ts[i] = t

        if changed:
            cfg = load_config(); cfg["tasks"] = ts; save_config(cfg)
            st.rerun()

        done = sum(1 for t in ts if t.get("status") == "COMPLETED")
        fail = sum(1 for t in ts if t.get("status") == "FAILED")
        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng", len(ts))
        m2.metric("✅ Hoàn thành", done)
        m3.metric("❌ Thất bại", fail)

        st.markdown("---")

        for t in ts[:20]:
            tid = t.get("id") or t.get("task_id")
            if not tid: continue
            s = t.get("status", "UNKNOWN")
            icon = STATUS_ICON.get(s, "⏳")
            vn = STATUS_VN.get(s, s)

            with st.container():
                cols = st.columns([0.08, 0.2, 0.4, 0.2, 0.12])
                cols[0].markdown(f"**#{tid}**")
                color = {"COMPLETED": C["green"], "FAILED": C["red"], "PENDING": C["yellow"]}.get(s, C["muted"])
                cols[1].markdown(f"<span style='color:{color}'>{icon} {vn}</span>", unsafe_allow_html=True)
                cols[2].markdown(f"<small style='color:{C['muted']}'>{t.get('created_at','')[:19] if t.get('created_at') else ''}</small>", unsafe_allow_html=True)
                cols[3].markdown(f"<small style='color:{C['muted']}'>{t.get('progress','')[:20] if t.get('progress') else ''}</small>", unsafe_allow_html=True)
                url = t.get("translated_url", "")
                if url:
                    cols[4].markdown(f"<a href='{url}' target='_blank' style='color:{C['accent']}'>▶ Xem</a>", unsafe_allow_html=True)
                else:
                    cols[4].markdown("—")
    else:
        st.info("Chưa có task nào. Nhập URL và bấm Dịch ngay.")


# ── AUTO REFRESH ──

if st.session_state.tasks:
    time.sleep(2)
    st.rerun()
