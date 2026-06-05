"""Fix indentation in webui app.py"""
import re

with open('server/webui/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find lines 361-423 and replace them
lines = content.split('\n')

# Find the section markers
start_marker = "# ====="
log_marker = "###"
footer_marker = "# ============ FOOTER"

start_idx = None
for i, line in enumerate(lines):
    if "TASK LIST & LOG" in line:
        start_idx = i
        break

if start_idx:
    # Find where the footer starts
    footer_idx = None
    for i in range(start_idx, len(lines)):
        if "FOOTER" in lines[i]:
            footer_idx = i
            break

    if footer_idx:
        # Replace the section
        new_section = [
            "# Task list (only in Lich su tab)",
            "ts = st.session_state.tasks",
            'if tools == "📋 Lịch sử":',
            "    st.divider()",
            "    if not ts:",
            '        st.info("Chưa có task nào.")',
            "    else:",
            "        for i, t in enumerate(ts):",
            '            tid = t.get("id") or t.get("task_id")',
            "            if not tid: continue",
            '            r = api_call("GET", f"/status/{tid}")',
            '            if "error" not in r:',
            '                old_st = t.get("status")',
            '                if r.get("status") != old_st:',
            "                    log(f\"{STATUS_ICON.get(r['status'],'')} Task #{tid}: {STATUS_VN.get(r['status'], r['status'])}\")",
            "                t.update(r); ts[i] = t",
            "",
            "        done = sum(1 for t in ts if t.get('status') == 'COMPLETED')",
            "        fail = sum(1 for t in ts if t.get('status') == 'FAILED')",
            "        m1, m2, m3, m4 = st.columns(4)",
            "        m1.metric('Tổng', len(ts))",
            "        m2.metric('✅ Hoàn thành', done)",
            "        m3.metric('❌ Thất bại', fail)",
            "        m4.metric('⏳ Đang xử lý', len(ts) - done - fail)",
            "",
            "        for t in ts[:15]:",
            '            tid = t.get("id") or t.get("task_id")',
            "            if not tid: continue",
            '            s = t.get("status", "UNKNOWN")',
            '            icon = STATUS_ICON.get(s, "⏳"); vn = STATUS_VN.get(s, s)',
            '            color = {"COMPLETED": C["green"], "FAILED": C["red"], "PENDING": C["yellow"]}.get(s, C["muted"])',
            '            err = t.get("error_message", "")',
            "            cols = st.columns([0.06, 0.16, 0.3, 0.2, 0.1, 0.18])",
            "            cols[0].markdown(f'**#{tid}**')",
            "            cols[1].markdown(f\"<span class='status-badge' style='background:{color}22;color:{color};border:1px solid {color}44;'>{icon} {vn}</span>\", unsafe_allow_html=True)",
            "            cols[2].markdown(f\"<small style='color:{C['muted']}'>{(t.get('created_at') or '')[:16]}</small>\", unsafe_allow_html=True)",
            "            cols[3].markdown(f\"<small style='color:{C['muted']}'>{(t.get('progress') or '')[:20]}</small>\", unsafe_allow_html=True)",
            '            url = t.get("translated_url", "")',
            "            if url: cols[4].markdown(f\"<a href='{url}' target='_blank' style='color:{C['accent']};font-size:0.85rem;'>▶ Xem</a>\", unsafe_allow_html=True)",
            '            else: cols[4].markdown("—")',
            '            if s == "FAILED":',
            '                if cols[5].button(f"🔄 Retry #{tid}", key=f"retry_{tid}"):',
            '                    rr = api_call("POST", f"/tasks/{tid}/retry")',
            '                    if "error" in rr: st.error(rr["error"])',
            '                    else: st.success(f"Retry #{tid}"); st.rerun()',
            "            if err:",
            '                st.markdown(f"<div class=\'error-detail\'>Lỗi: {err[:200]}</div>", unsafe_allow_html=True)',
            "",
            "        if fail > 0:",
            '            if st.button("🔄 Retry tất cả", key="retry_all", use_container_width=True):',
            '                rr = api_call("POST", "/tasks/retry-all")',
            '                if "error" not in rr: st.success(f"Đã retry {rr.get("retried",0)} tasks"); st.rerun()',
            "",
            "    st.markdown('### 📋 Nhật ký')",
            "    for entry in st.session_state.log[:40]:",
            "        st.markdown(f\"<div class='log-entry'>{entry}</div>\", unsafe_allow_html=True)",
        ]
        lines[start_idx:footer_idx] = new_section
        content = '\n'.join(lines)

        with open('server/webui/app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed! Replaced lines {start_idx} to {footer_idx}")
    else:
        print("Footer not found")
else:
    print("Start marker not found")
