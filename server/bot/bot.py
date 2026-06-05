"""
Telegram Bot — Quản lý License Key bán tự động.
Flow:
  1. User bấm /start → chọn gói (1 ngày / 1 tháng / 2 tháng / 3 tháng)
  2. Bot gửi thông tin tài khoản + cú pháp chuyển khoản
  3. User gửi ảnh bill → Bot forward đến Admin Group
  4. Admin bấm [Duyệt] hoặc [Từ chối]
  5. Duyệt → Bot sinh Key, lưu DB, gửi cho user
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from server.config import TELEGRAM_BOT_TOKEN, ADMIN_GROUP_ID, TELEGRAM_PROXY_URL
from server.utils.helpers import generate_license_key

logger = logging.getLogger(__name__)

# ---------- CẤU HÌNH GÓI ----------
PLANS = {
    "1_day": {"label": "📅 1 Ngày", "days": 1, "price": "10,000 VNĐ"},
    "1_month": {"label": "📅 1 Tháng", "days": 30, "price": "100,000 VNĐ"},
    "2_months": {"label": "📅 2 Tháng", "days": 60, "price": "180,000 VNĐ"},
    "3_months": {"label": "📅 3 Tháng", "days": 90, "price": "250,000 VNĐ"},
}

# Thông tin tài khoản ngân hàng
BANK_INFO = (
    "🏦 *Thông tin chuyển khoản:*\n\n"
    "• *Ngân hàng:* TP Bank\n"
    "• *Số TK:* 07374506999\n"
    "• *Chủ TK:* HOANG VAN TU\n"
    "• *Nội dung:* DICHVIDEO_<your_telegram_id>\n\n"
    "📌 *Ví dụ:* DICHVIDEO_123456789\n\n"
    "Sau khi chuyển khoản, hãy gửi ảnh chụp bill (hóa đơn) vào đây để admin xác nhận."
)


# =====================
# DATABASE HELPERS (sync)
# =====================

def _get_session():
    """Lấy sync session — gọi khi cần."""
    from server.database import SyncSessionLocal
    return SyncSessionLocal()


def _get_or_create_user(telegram_id: str, username = None):
    """Lấy user từ DB hoặc tạo mới."""
    from server.models import User
    session = _get_session()
    try:
        user = session.query(User).filter(
            User.telegram_id == telegram_id
        ).first()
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    finally:
        session.close()


def _create_license_key(duration_days: int, user_id = None) -> str:
    """Tạo License Key và lưu vào DB."""
    from server.models import LicenseKey
    session = _get_session()
    try:
        key_code = generate_license_key()
        license_key = LicenseKey(
            key_code=key_code,
            duration_days=duration_days,
            status="AVAILABLE",
            user_id=user_id,
        )
        session.add(license_key)
        session.commit()
        return key_code
    except Exception as e:
        session.rollback()
        logger.error(f"Lỗi tạo license key: {e}")
        raise
    finally:
        session.close()


# =====================
# HANDLERS
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start — Hiển thị menu chọn gói."""
    keyboard = [
        [InlineKeyboardButton(plan["label"], callback_data=f"plan_{key}")]
        for key, plan in PLANS.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎥 *Chào mừng bạn đến với DichAudio!*\n\n"
        "Công cụ tải, dịch thuật và lồng tiếng video tự động.\n\n"
        "Vui lòng chọn *gói dịch vụ* bạn muốn mua:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi user chọn gói."""
    query = update.callback_query
    await query.answer()

    plan_key = query.data.replace("plan_", "")
    plan = PLANS.get(plan_key)
    if not plan:
        await query.edit_message_text("❌ Gói không hợp lệ.")
        return

    # Lưu lựa chọn vào context
    context.user_data["selected_plan"] = plan_key

    user_id = update.effective_user.id
    payment_info = BANK_INFO.replace(
        "<your_telegram_id>", str(user_id)
    )

    await query.edit_message_text(
        f"🛒 *Gói bạn đã chọn:* {plan['label']}\n"
        f"💰 *Giá:* {plan['price']}\n"
        f"📆 *Thời hạn:* {plan['days']} ngày\n\n"
        f"{payment_info}\n\n"
        "📸 *Sau khi chuyển khoản, hãy gửi ảnh bill vào đây!*",
        parse_mode="Markdown",
    )


async def handle_bill_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xử lý khi user gửi ảnh bill.
    Forward ảnh lên Admin Group kèm nút Duyệt/Từ chối.
    """
    plan_key = context.user_data.get("selected_plan")
    if not plan_key:
        await update.message.reply_text(
            "❌ Bạn chưa chọn gói dịch vụ. Gõ /start để chọn gói."
        )
        return

    plan = PLANS.get(plan_key)
    if not plan:
        await update.message.reply_text("❌ Gói không hợp lệ. Gõ /start.")
        return

    user = update.effective_user
    telegram_id = str(user.id)
    username = user.username or "N/A"

    # Lưu thông tin user vào context để admin biết
    context.user_data["bill_user_id"] = telegram_id
    context.user_data["bill_username"] = username
    context.user_data["bill_plan"] = plan_key

    # Lấy ảnh có độ phân giải cao nhất
    photo = update.message.photo[-1]

    # Tạo nút Duyệt / Từ chối
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ Duyệt {plan['label']}",
                callback_data=f"approve_{telegram_id}_{plan_key}"
            ),
            InlineKeyboardButton(
                "❌ Từ chối",
                callback_data=f"reject_{telegram_id}"
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        f"📥 *Yêu cầu kích hoạt mới!*\n\n"
        f"👤 *User:* [{username}](tg://user?id={user.id})\n"
        f"🆔 *Telegram ID:* `{telegram_id}`\n"
        f"📦 *Gói:* {plan['label']} ({plan['days']} ngày)\n"
        f"💰 *Giá:* {plan['price']}"
    )

    try:
        # Forward ảnh lên Admin Group
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo.file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

        await update.message.reply_text(
            "✅ *Bill của bạn đã được gửi đến Admin!*\n\n"
            "Vui lòng chờ xác nhận trong giây lát. "
            "Bạn sẽ nhận được mã kích hoạt khi admin duyệt.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Lỗi forward bill: {e}")
        await update.message.reply_text(
            "❌ Có lỗi xảy ra khi gửi bill. Vui lòng thử lại sau hoặc liên hệ admin."
        )


async def handle_approve_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi admin bấm Duyệt hoặc Từ chối."""
    query = update.callback_query
    await query.answer()

    data = query.data
    admin_id = update.effective_user.id

    if data.startswith("approve_"):
        # Parse: approve_{telegram_id}_{plan_key}
        parts = data.split("_")
        telegram_id = parts[1]
        plan_key = "_".join(parts[2:])
        plan = PLANS.get(plan_key)

        if not plan:
            await query.edit_message_caption(
                caption="❌ Gói không hợp lệ.",
                parse_mode="Markdown",
            )
            return

        try:
            # Tạo user và license key
            user = _get_or_create_user(telegram_id)
            key_code = _create_license_key(
                duration_days=plan["days"],
                user_id=user.id,
            )

            # Gửi key cho user
            user_message = (
                "🎉 *Yêu cầu của bạn đã được duyệt!*\n\n"
                f"📦 *Gói:* {plan['label']}\n"
                f"📆 *Thời hạn:* {plan['days']} ngày\n\n"
                f"🔑 *Mã kích hoạt của bạn:*\n"
                f"`{key_code}`\n\n"
                "📌 *Cách sử dụng:*\n"
                "1. Mở ứng dụng DichAudio\n"
                "2. Nhập mã kích hoạt vào ô License Key\n"
                "3. Bắt đầu dịch video!\n\n"
                "Cảm ơn bạn đã sử dụng dịch vụ! 🚀"
            )
            try:
                await context.bot.send_message(
                    chat_id=int(telegram_id),
                    text=user_message,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Không thể gửi tin nhắn cho user {telegram_id}: {e}")

            # Cập nhật message admin
            await query.edit_message_caption(
                caption=query.message.caption + (
                    f"\n\n✅ *Đã duyệt bởi Admin* `{admin_id}`\n"
                    f"🔑 Key: `{key_code[:8]}...`"
                ),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Lỗi duyệt key: {e}")
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n❌ *Lỗi khi tạo key*",
                parse_mode="Markdown",
            )

    elif data.startswith("reject_"):
        # Parse: reject_{telegram_id}
        telegram_id = data.split("_")[1]

        # Thông báo cho user
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text="❌ *Yêu cầu kích hoạt của bạn đã bị từ chối.*\n\n"
                     "Vui lòng kiểm tra lại thông tin chuyển khoản và thử lại. "
                     "Nếu cần hỗ trợ, hãy liên hệ admin.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Không thể gửi tin nhắn từ chối: {e}")

        # Cập nhật message admin
        await query.edit_message_caption(
            caption=query.message.caption + (
                f"\n\n❌ *Đã từ chối bởi Admin* `{admin_id}`"
            ),
            parse_mode="Markdown",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /help."""
    await update.message.reply_text(
        "🤖 *DichAudio Bot - Trợ giúp*\n\n"
        "*/start* — Chọn gói dịch vụ\n"
        "*/help* — Xem hướng dẫn\n"
        "*/status* — Kiểm tra license key của bạn\n\n"
        "📞 *Liên hệ admin:* 0394396228\n"
        "📧 *Email:* ahihiyeuem2303.com",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /status — Kiểm tra license key của user."""
    telegram_id = str(update.effective_user.id)

    try:
        from server.models import LicenseKey
        session = _get_session()

        keys = session.query(LicenseKey).join(
            LicenseKey.user
        ).filter(
            LicenseKey.user.has(telegram_id=telegram_id)
        ).all()

        if not keys:
            await update.message.reply_text(
                "Bạn chưa có License Key nào. Gõ /start để mua gói."
            )
            return

        msg = "📋 *Danh sách License Key của bạn:*\n\n"
        for key in keys:
            status_emoji = {
                "AVAILABLE": "🟢",
                "ACTIVATED": "🔵",
                "EXPIRED": "🔴",
            }.get(key.status.value, "⚪")

            expired = key.expired_at.strftime("%d/%m/%Y") if key.expired_at else "N/A"
            msg += (
                f"{status_emoji} `{key.key_code[:16]}...`\n"
                f"   • Trạng thái: {key.status.value}\n"
                f"   • Hạn: {expired}\n\n"
            )

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Lỗi kiểm tra status: {e}")
        await update.message.reply_text("❌ Có lỗi xảy ra. Vui lòng thử lại sau.")
    finally:
        session.close()


# =====================
# MAIN
# =====================

def run_bot():
    """Khởi chạy Telegram Bot."""
    import asyncio

    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN chưa được cấu hình.")
        return

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)

    # Dùng proxy nếu được cấu hình (cho VN/CN bị chặn Telegram)
    if TELEGRAM_PROXY_URL:
        logger.info(f"🔌 Dùng proxy: {TELEGRAM_PROXY_URL}")
        builder = builder.proxy(TELEGRAM_PROXY_URL)

    application = builder.build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(plan_callback, pattern="^plan_"))

    # Admin handlers (only if ADMIN_GROUP_ID configured)
    if ADMIN_GROUP_ID:
        application.add_handler(CallbackQueryHandler(handle_approve_reject, pattern="^(approve_|reject_)"))
        application.add_handler(MessageHandler(filters.PHOTO, handle_bill_photo))
        logger.info(f"Admin handlers registered (group: {ADMIN_GROUP_ID})")

    logger.info("🤖 DichAudio Bot started. Polling...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        application.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=())
    except Exception as e:
        logger.error(f"Bot error: {e}")


if __name__ == "__main__":
    run_bot()
