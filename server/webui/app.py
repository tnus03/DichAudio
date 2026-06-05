# -*- coding: utf-8 -*-
"""
DichAudio WebUI — Streamlit Dashboard
"""
import hashlib, json, platform, re, subprocess, time, uuid
from pathlib import Path
import requests
import streamlit as st

st.set_page_config(page_title="DichAudio", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")

API_BASE = "http://127.0.0.1:8002/api/v1"
CONFIG_FILE = Path.home() / ".dichaudio" / "webui_config.json"

C = {"bg": "#0f172a", "card": "#1e293b", "border": "#334155", "text": "#e2e8f0",
     "muted": "#64748b", "accent": "#3b82f6", "green": "#22c55e",
     "red": "#ef4444", "yellow": "#f59e0b", "orange": "#f97316"}


def get_hwid() -> str:
    components = []
    try:
        if platform.system() == "Windows":
            for cmd, idx in [("wmic cpu get processorid", 1), ("wmic baseboard get serialnumber", 1), ("wmic diskdrive get serialnumber", 1)]:
                r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=5)
                if r.returncode == 0:
                    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
                    if len(lines) > idx: components.append(lines[idx])
            mac_r = subprocess.run("wmic nic where 'NetEnabled=True' get MACAddress", capture_output=True, text=True, shell=True, timeout=5)
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


def api_call(method: str, path: str, data: dict = None, timeout: int = 10) -> dict:
    url = f"{API_BASE}{path}"
    req_kwargs: dict = {"timeout": timeout}
    if data is not None: req_kwargs["json"] = data
    try:
        r = requests.get(url, **req_kwargs) if method == "GET" else requests.post(url, **req_kwargs)
        if r.status_code >= 400:
            return {"error": r.json().get("detail", f"HTTP {r.status_code}")}
        return r.json()
    except requests.ConnectionError:
        return {"error": "Không thể kết nối server (port 8002)"}
    except Exception as e: return {"error": str(e)}


def post_file(url_suffix: str, files: dict, data: dict, timeout: int = 300) -> dict:
    try:
        r = requests.post(f"{API_BASE}{url_suffix}", files=files, data=data, timeout=timeout)
        if r.status_code >= 400:
            return {"error": r.json().get("detail", f"HTTP {r.status_code}")}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


STATUS_ICON = {"PENDING": "⏳", "DOWNLOADING": "⬇️", "EXTRACTING_AUDIO": "🎵",
               "TRANSCRIBING": "📝", "TRANSLATING": "🌐", "GENERATING_VOICE": "🗣️",
               "EDITING_AND_MERGING": "🎬", "UPLOADING": "☁️", "COMPLETED": "✅", "FAILED": "❌"}
STATUS_VN = {"PENDING": "Chờ xử lý", "DOWNLOADING": "Đang tải video", "EXTRACTING_AUDIO": "Tách âm thanh",
             "TRANSCRIBING": "Nhận diện giọng nói", "TRANSLATING": "Đang dịch thuật",
             "GENERATING_VOICE": "Tạo giọng đọc", "EDITING_AND_MERGING": "Ghép video", "UPLOADING": "Đang tải lên",
             "COMPLETED": "Hoàn thành", "FAILED": "Thất bại"}

st.markdown(f"""
<style>
    .stApp {{ background: {C['bg']}; }}
    .main > div {{ padding: 1rem 2rem; }}
    h1, h2, h3, p, label, span {{ color: {C['text']} !important; }}
    .stTextInput>div>div>input, .stSelectbox>div>div, .stNumberInput>div>div>input {{
        background: {C['bg']} !important; color: {C['text']} !important; border: 1px solid {C['border']} !important; border-radius: 8px;
    }}
    .stSlider>div {{ padding-top: 0.5rem; }}
    .stButton>button {{ border: none; border-radius: 8px; padding: 0.5rem 1.5rem; font-weight: 600; }}
    .stButton>button[kind="primary"] {{ background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; }}
    div[data-testid="stSidebar"] {{ background: {C['card']}; border-right: 1px solid {C['border']}; }}
    .task-row {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 10px; padding: 0.8rem 1rem; margin-bottom: 0.4rem; }}
    .log-entry {{ color: {C['muted']}; font-size: 0.82rem; font-family: monospace; padding: 3px 0; border-bottom: 1px solid #1a2639; }}
    .status-badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }}
    .error-detail {{ background: #1a1a2e; border-left: 3px solid {C['red']}; padding: 0.5rem 1rem; border-radius: 0 8px 8px 0; font-size: 0.8rem; margin-top: 0.3rem; }}
</style>
""", unsafe_allow_html=True)

for key in ["cfg", "log", "tasks"]:
    if key not in st.session_state:
        st.session_state[key] = load_config().get("tasks", []) if key == "tasks" else (load_config() if key == "cfg" else [])


def log(msg):
    ts = time.strftime("%H:%M:%S")
    st.session_state.log.insert(0, f"[{ts}] {msg}")
    st.session_state.log = st.session_state.log[:100]


def check_license():
    cfg = st.session_state.cfg
    if not cfg.get("license_key") or not cfg.get("device_id"):
        return None
    return api_call("POST", "/license/check", {"license_key": cfg["license_key"], "device_id": cfg["device_id"]})


# Header
col_logo, col_status = st.columns([0.7, 0.3])
with col_logo:
    st.markdown("## 🎬 DichAudio · *Trợ lý dịch video tự động*")
with col_status:
    try:
        h = requests.get(f"{API_BASE}/health", timeout=5).json()
        st.markdown(f"<div style='text-align:right;color:{C['green']};font-size:0.9rem;'>✅ Server Online</div>", unsafe_allow_html=True)
    except:
        st.markdown(f"<div style='text-align:right;color:{C['red']};font-size:0.9rem;'>❌ Server Offline</div>", unsafe_allow_html=True)
st.divider()

# Sidebar
with st.sidebar:
    st.markdown("### 🎬 DichAudio")
    lic = check_license()
    if lic and lic.get("valid"):
        days, hours = lic.get("remaining_days", 0), lic.get("remaining_hours", 0)
        txt = f"Còn {days} ngày" if days >= 1 else (f"Còn {hours} giờ" if hours > 0 else "Sắp hết hạn")
        st.markdown(f"<div class='status-badge' style='background:{C['green']}22;color:#4ade80;border:1px solid {C['green']}44;'>✅ {txt}</div>", unsafe_allow_html=True)
    elif lic and "error" in lic:
        st.error(f"⚠️ {lic['error']}")
    else:
        st.warning("🔑 Chưa có license")
    with st.expander("🔑 Kích hoạt License", expanded=not (lic and lic.get("valid"))):
        k = st.text_input("License Key", placeholder="XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX", label_visibility="collapsed", key="lic_key")
        if st.button("Kích hoạt", use_container_width=True, type="primary"):
            if not k.strip(): st.error("Nhập License Key")
            else:
                hwid = get_hwid()
                res = api_call("POST", "/license/activate", {"license_key": k.strip(), "device_id": hwid})
                if "error" in res: st.error(res["error"])
                elif res.get("success"):
                    cfg = load_config()
                    cfg.update(license_key=k.strip(), device_id=hwid, expired_at=res.get("expired_at"), remaining_days=res["remaining_days"])
                    save_config(cfg); st.session_state.cfg = cfg
                    st.success(f"Còn {res['remaining_days']} ngày"); st.rerun()
    st.divider()
    tools = st.radio("Công cụ", ["📥 Dịch URL", "🔊 Ghép AV", "🎤 Lồng tiếng", "📋 Lịch sử"], label_visibility="collapsed")
    st.divider()
    if st.button("🔄 Làm mới", key="refresh_sidebar", use_container_width=True): st.rerun()

# Main: left = tool, right = preview
col_left, col_right = st.columns([0.45, 0.55], gap="large")

with col_left:
    if tools == "📥 Dịch URL":
        st.markdown("### 🎥 Dịch video")
        input_method = st.radio("Chọn phương thức", ["📎 Nhập link", "📤 Upload từ máy"], horizontal=True, label_visibility="collapsed")

        mode = st.radio("Chế độ xử lý", ["🎬 Video + Âm thanh (dịch đầy đủ)", "🎬 Chỉ video", "🎵 Chỉ âm thanh"], horizontal=False,
                        help="(?) Video+Âm thanh: tải về, dịch, lồng tiếng, phụ đề | Chỉ video: tải video gốc | Chỉ âm thanh: trích xuất audio")

        url = ""; uploaded_file = None
        if input_method == "📎 Nhập link":
            url = st.text_input("URL Video", placeholder="https://www.youtube.com/... / TikTok...", label_visibility="collapsed",
                                help="Nhập link video từ YouTube, TikTok, Facebook...")
        else:
            uploaded_file = st.file_uploader("Chọn file video", type=["mp4", "avi", "mov", "mkv", "webm"], key="upload_video",
                                            help="Hỗ trợ: MP4, AVI, MOV, MKV, WEBM")

        show_full = mode.startswith("🎬 Video")  # Full mode
        show_audio = mode.startswith("🎵")  # Audio only
        show_video_only = mode.startswith("🎬 Chỉ")  # Video only

        opts = st.container(border=True)

        # Mode 1: Video + Audio (full)
        if show_full:
            cc1, cc2 = opts.columns(2)
            provider = cc1.selectbox("AI dịch", ["auto", "gemini", "openai", "deepseek"], index=0, key="ai_provider",
                                     help="(?) Chọn AI dịch thuật")
            target_lang = cc2.selectbox("Ngôn ngữ đích", ["Tiếng Việt", "English", "日本語", "中文", "한국어"], index=0,
                                        help="(?) Chọn ngôn ngữ muốn dịch sang")
            cc3, cc4 = opts.columns(2)
            voice_gender = cc3.selectbox("Giọng đọc", ["Nam", "Nữ"], index=0, key="voice_gender_full",
                                          help="(?) Giọng đọc cho bản dịch: Nam (Nam Minh) hoặc Nữ (Hoài My)")
            speed = cc4.select_slider("Tốc độ", [0.5, 0.75, 1.0, 1.05, 1.1, 1.25, 1.5, 2.0], value=1.0,
                                       help="(?) Tốc độ phát video")

            with opts.expander("Hiệu ứng cơ bản", expanded=True):
                c1, c2, c3, c4 = opts.columns(4)
                mirror = c1.checkbox("Gương"); blur = c2.checkbox("Mờ viền"); wm = c3.checkbox("Logo"); sub = c4.checkbox("Phụ đề", True)
                blur_val = opts.slider("Độ mờ", 1, 50, 10) if blur else 10
                if wm:
                    wc1, wc2 = opts.columns(2)
                    wm_pos = wc1.selectbox("Vị trí logo", ["bottom_right", "bottom_left", "top_right", "top_left"])
                    wm_scale = wc2.slider("Tỷ lệ", 0.01, 0.3, 0.1)
                else: wm_pos, wm_scale = "bottom_right", 0.1
                if sub:
                    sc1, sc2, sc3 = opts.columns(3)
                    sub_size = sc1.slider("Cỡ chữ", 12, 48, 24)
                    sub_pos = sc2.selectbox("Vị trí", ["bottom", "top", "middle"])
                    sub_color = sc3.selectbox("Màu", ["white", "yellow", "red", "cyan", "lime"])
                else: sub_size, sub_pos, sub_color = 24, "bottom", "white"

            with opts.expander("Hiệu ứng nâng cao", expanded=False):
                ac1, ac2, ac3 = opts.columns(3)
                bri = ac1.slider("Độ sáng", -1.0, 1.0, 0.0, 0.05)
                con = ac2.slider("Tương phản", 0.0, 3.0, 1.0, 0.1)
                sat = ac3.slider("Bão hòa", 0.0, 3.0, 1.0, 0.1)
                rotate = opts.selectbox("Xoay", [0, 90, 180, 270])
                cr1, cr2, cr3, cr4 = opts.columns(4)
                ct = cr1.number_input("Cắt trên", 0, 500, 0, step=10)
                cb = cr2.number_input("Cắt dưới", 0, 500, 0, step=10)
                cl = cr3.number_input("Cắt trái", 0, 500, 0, step=10)
                cr = cr4.number_input("Cắt phải", 0, 500, 0, step=10)

            with opts.expander("Âm thanh", expanded=False):
                songs_dir = Path("resource/songs")
                songs = [f.name for f in songs_dir.glob("*") if f.suffix in (".mp3", ".wav", ".m4a")] if songs_dir.exists() else []
                bg_m = opts.selectbox("Nhạc nền", ["Không"] + (songs if songs else []))
                bg_v = opts.slider("Lượng nhạc nền", 0.0, 1.0, 0.05, 0.05)
                ori_v = opts.slider("Âm thanh gốc", 0.0, 1.0, 0.1, 0.05)
                dub_v = opts.slider("Âm lượng giọng dịch", 0.0, 1.0, 1.0, 0.05)

        elif show_video_only:
            # Mode 2: Chi video - co hieu ung nhung khong dich
            cc1, cc2 = opts.columns(2)
            provider = "auto"
            target_lang = "Vietnamese"
            voice_gender = "Nam"
            cc1.markdown("**Chế độ chỉ video** — áp dụng hiệu ứng, không dịch thuật")
            speed = cc2.select_slider("Tốc độ", [0.5, 0.75, 1.0, 1.05, 1.1, 1.25, 1.5, 2.0], value=1.0,
                                       help="(?) Tốc độ phát video")

            with opts.expander("Hiệu ứng cơ bản", expanded=True):
                c1, c2, c3, c4 = opts.columns(4)
                mirror = c1.checkbox("Gương"); blur = c2.checkbox("Mờ viền"); wm = c3.checkbox("Logo"); sub = c4.checkbox("Phụ đề", False)
                blur_val = opts.slider("Độ mờ", 1, 50, 10) if blur else 10
                if wm:
                    wc1, wc2 = opts.columns(2)
                    wm_pos = wc1.selectbox("Vị trí logo", ["bottom_right", "bottom_left", "top_right", "top_left"])
                    wm_scale = wc2.slider("Tỷ lệ", 0.01, 0.3, 0.1)
                else: wm_pos, wm_scale = "bottom_right", 0.1
                sub_size, sub_pos, sub_color = 24, "bottom", "white"

            with opts.expander("Hiệu ứng nâng cao", expanded=False):
                ac1, ac2, ac3 = opts.columns(3)
                bri = ac1.slider("Độ sáng", -1.0, 1.0, 0.0, 0.05)
                con = ac2.slider("Tương phản", 0.0, 3.0, 1.0, 0.1)
                sat = ac3.slider("Bão hòa", 0.0, 3.0, 1.0, 0.1)
                rotate = opts.selectbox("Xoay", [0, 90, 180, 270])
                cr1, cr2, cr3, cr4 = opts.columns(4)
                ct = cr1.number_input("Cắt trên", 0, 500, 0, step=10)
                cb = cr2.number_input("Cắt dưới", 0, 500, 0, step=10)
                cl = cr3.number_input("Cắt trái", 0, 500, 0, step=10)
                cr = cr4.number_input("Cắt phải", 0, 500, 0, step=10)

            with opts.expander("Âm thanh", expanded=False):
                songs_dir = Path("resource/songs")
                songs = [f.name for f in songs_dir.glob("*") if f.suffix in (".mp3", ".wav", ".m4a")] if songs_dir.exists() else []
                bg_m = opts.selectbox("Nhạc nền", ["Không"] + (songs if songs else []))
                bg_v = opts.slider("Lượng nhạc nền", 0.0, 1.0, 0.05, 0.05)
                ori_v = opts.slider("Âm thanh gốc", 0.0, 1.0, 0.1, 0.05)
                dub_v = opts.slider("Âm lượng giọng dịch", 0.0, 1.0, 1.0, 0.05)

        elif show_audio:
            # Mode 3: Audio only - AI + voice options
            cc1, cc2 = opts.columns(2)
            provider = cc1.selectbox("AI dịch", ["auto", "gemini", "openai", "deepseek"], index=0, key="ai_provider_audio",
                                     help="(?) Chọn AI dịch thuật")
            target_lang = cc2.selectbox("Ngôn ngữ đích", ["Tiếng Việt", "English", "日本語", "中文", "한국어"], index=0, key="target_lang_audio",
                                        help="(?) Chọn ngôn ngữ muốn dịch sang")
            voice_gender = opts.selectbox("Giọng đọc", ["Nam", "Nữ"], index=0, key="voice_gender_audio",
                                          help="(?) Giọng đọc: Nam (Nam Minh) hoặc Nữ (Hoài My)")
            speed = 1.0
            mirror = blur = wm = sub = False; blur_val = 10
            wm_pos = "bottom_right"; wm_scale = 0.1
            sub_size = 24; sub_pos = "bottom"; sub_color = "white"
            bri = con = sat = 0.0; rotate = 0; ct = cb = cl = cr = 0
            bg_m = "Không"; bg_v = 0.05; ori_v = 0.1; dub_v = 1.0
            songs_dir = Path("resource/songs")

        if st.button("🚀 Dịch ngay", use_container_width=True, type="primary"):
            has_url = bool(url.strip()) if input_method == "📎 Nhập link" else False
            has_file = uploaded_file is not None if input_method == "📤 Upload từ máy" else False
            if not has_url and not has_file: st.error("Nhập URL hoặc chọn file video")
            elif not st.session_state.cfg.get("license_key"): st.error("Kích hoạt license trước")
            else:
                song_path = str(songs_dir / bg_m) if bg_m and bg_m != "Không" else ""
                data = {"license_key": st.session_state.cfg["license_key"],
                        "options": {"mode": "video_only" if show_video_only else ("audio_only" if show_audio else "full"),
                                    "mirror": mirror, "speed": speed, "blur_padding": blur, "blur_intensity": blur_val,
                                    "watermark_url": "logo.png" if wm else None, "watermark_position": wm_pos, "watermark_scale": wm_scale,
                                    "subtitles": sub, "subtitle_font_size": sub_size, "subtitle_position": sub_pos, "subtitle_color": sub_color,
                                    "brightness": bri, "contrast": con, "saturation": sat, "rotate": rotate,
                                    "crop_top": ct, "crop_bottom": cb, "crop_left": cl, "crop_right": cr,
                                    "bg_music": song_path, "bg_music_volume": bg_v, "original_volume": ori_v, "dubbed_volume": dub_v,
                                    "translation_provider": provider,
                                    "target_language": target_lang, "voice_gender": voice_gender}}
                if input_method == "📎 Nhập link":
                    data["source_url"] = url.strip()
                    res = api_call("POST", "/translate", data, timeout=30)
                else:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    res = post_file("/upload", files, data, 600)
                if "error" in res: st.error(res["error"]); log(f"Lỗi: {res['error']}")
                else:
                    tid = res["task_id"]; log(f"Task #{tid} đã tạo")
                    ts = load_config().get("tasks", []); ts.insert(0, {"id": tid, "status": "PENDING"})
                    cfg = load_config(); cfg["tasks"] = ts[:50]; save_config(cfg)
                    st.session_state.tasks = ts; st.success(f"Task #{tid} đang xử lý!"); st.rerun()

    elif tools == "🔊 Ghép AV":
        st.markdown("### 🔊 Ghép video + audio")
        c1, c2 = st.columns(2)
        with c1: mv = st.file_uploader("Video nền", type=["mp4", "avi", "mov", "mkv"], key="mv", help="Video gốc (giữ lại hình ảnh)")
        with c2: ma = st.file_uploader("Audio thay thế", type=["mp3", "wav", "m4a"], key="ma", help="File audio thay thế âm thanh video gốc")
        if mv and ma and st.button("🔊 Ghép ngay", use_container_width=True, type="primary"):
            r = post_file("/merge", {"video": (mv.name, mv.getvalue(), mv.type), "audio": (ma.name, ma.getvalue(), ma.type)},
                          {"license_key": st.session_state.cfg.get("license_key", "")})
            if "error" in r: st.error(r["error"])
            else: st.success("Ghép thành công!"); log("🔊 Ghép AV thành công")

    elif tools == "🎤 Lồng tiếng":
        st.markdown("### 🎤 Lồng tiếng vào video khác")
        du = st.text_input("URL nguồn (có audio gốc)", placeholder="https://www.youtube.com/...",
                           help="Video này được lấy audio -> STT -> dịch -> TTS", key="dub_url_main")
        dv = st.file_uploader("Video đích (nhận giọng dịch)", type=["mp4", "avi", "mov", "mkv"], key="dv_main",
                              help="Video này được gắn giọng dịch + phụ đề từ video nguồn")
        if du and dv and st.button("🎤 Lồng tiếng", use_container_width=True, type="primary"):
            r = post_file("/dub-video", {"target_video": (dv.name, dv.getvalue(), dv.type)},
                          {"source_url": du, "license_key": st.session_state.cfg.get("license_key", ""), "translation_provider": "auto"}, 600)
            if "error" in r: st.error(r["error"])
            else: st.success(f"Task #{r['task_id']}"); log(f"🎤 Lồng tiếng: #{r['task_id']}"); st.rerun()

# Right column - preview
with col_right:
    st.markdown("### 📺 Xem trước")
    if tools == "📥 Dịch URL":
        up = st.session_state.get("upload_video")
        if up: st.video(up)
        elif url.strip(): st.markdown(f"<small style='color:{C['muted']};'>🔗 {url[:60]}... Sẵn sàng xử lý.</small>", unsafe_allow_html=True)
        else: st.info("📂 Chọn file hoặc nhập link để xem trước")
    elif tools == "🔊 Ghép AV":
        if st.session_state.get("mv"): st.video(st.session_state.mv)
        if st.session_state.get("ma"): st.audio(st.session_state.ma)
        if not st.session_state.get("mv") and not st.session_state.get("ma"): st.info("📂 Chọn video và audio để xem trước")
    elif tools == "🎤 Lồng tiếng":
        if st.session_state.get("dv_main"): st.video(st.session_state.dv_main)
        else: st.info("📂 Chọn video đích để xem trước")
    elif tools == "📋 Lịch sử":
        st.info("📋 Danh sách task ở bên dưới.")

# History tab (below columns)
if tools == "📋 Lịch sử":
    st.divider()
    ts = st.session_state.tasks
    if not ts:
        st.info("Chưa có task nào.")
    else:
        for i, t in enumerate(ts):
            tid = t.get("id") or t.get("task_id")
            if not tid: continue
            r = api_call("GET", f"/status/{tid}")
            if "error" not in r:
                old_st = t.get("status")
                if r.get("status") != old_st:
                    log(f"{STATUS_ICON.get(r['status'],'')} Task #{tid}: {STATUS_VN.get(r['status'], r['status'])}")
                t.update(r); ts[i] = t

        done = sum(1 for t in ts if t.get("status") == "COMPLETED")
        fail = sum(1 for t in ts if t.get("status") == "FAILED")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tổng", len(ts)); m2.metric("✅ Hoàn thành", done)
        m3.metric("❌ Thất bại", fail); m4.metric("⏳ Đang xử lý", len(ts) - done - fail)

        for t in ts[:15]:
            tid = t.get("id") or t.get("task_id")
            if not tid: continue
            s = t.get("status", "UNKNOWN")
            icon = STATUS_ICON.get(s, "⏳"); vn = STATUS_VN.get(s, s)
            color = {"COMPLETED": C["green"], "FAILED": C["red"], "PENDING": C["yellow"]}.get(s, C["muted"])
            err = t.get("error_message", "")
            cols = st.columns([0.06, 0.16, 0.3, 0.2, 0.1, 0.18])
            cols[0].markdown(f"**#{tid}**")
            cols[1].markdown(f"<span class='status-badge' style='background:{color}22;color:{color};border:1px solid {color}44;'>{icon} {vn}</span>", unsafe_allow_html=True)
            cols[2].markdown(f"<small style='color:{C['muted']}'>{(t.get('created_at') or '')[:16]}</small>", unsafe_allow_html=True)
            cols[3].markdown(f"<small style='color:{C['muted']}'>{(t.get('progress') or '')[:20]}</small>", unsafe_allow_html=True)
            url = t.get("translated_url", "")
            if url: cols[4].markdown(f"<a href='{url}' target='_blank' style='color:{C['accent']};font-size:0.85rem;'>▶ Xem</a>", unsafe_allow_html=True)
            else: cols[4].markdown("—")
            if s == "FAILED" and cols[5].button(f"🔄 Retry", key=f"retry_{tid}"):
                rr = api_call("POST", f"/tasks/{tid}/retry")
                if "error" in rr: st.error(rr["error"])
                else: st.success(f"Retry #{tid}"); st.rerun()
            if err: st.markdown(f"<div class='error-detail'>Lỗi: {err[:200]}</div>", unsafe_allow_html=True)

        if fail > 0 and st.button("🔄 Retry tất cả", key="retry_all", use_container_width=True):
            rr = api_call("POST", "/tasks/retry-all")
            if "error" not in rr: st.success(f'Đã retry {rr.get("retried",0)} tasks'); st.rerun()

    st.markdown("### 📋 Nhật ký")
    for entry in st.session_state.log[:40]:
        st.markdown(f"<div class='log-entry'>{entry}</div>", unsafe_allow_html=True)

# Footer
st.markdown(f"<div style='text-align:center;padding:1rem;color:{C['muted']};font-size:0.8rem;border-top:1px solid {C['border']};margin-top:1rem;'>"
            f"DichAudio · by <a href='https://github.com/tnus03' target='_blank' style='color:{C['accent']};text-decoration:none;'>@tnus03</a></div>", unsafe_allow_html=True)

# Auto refresh
if st.session_state.tasks:
    time.sleep(2)
    st.rerun()
