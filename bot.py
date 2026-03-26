import os
import requests
import base64
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
# Giữ nguyên các import cũ của sếp
from ta_engine import analyze_ta, get_ohlcv
from knowledge import save_pattern, get_patterns, list_patterns

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
CC_API_KEY = os.environ.get("CRYPTOCOMPARE_KEY")
GROK_URL = "https://api.x.ai/v1/chat/completions"

# ── Helpers Nâng Cấp ──────────────────────────────────────

def ask_grok(user_message: str, context_data: str = "", base64_image: str = None) -> str:
    try:
        patterns = get_patterns()
        pattern_text = ""
        if patterns:
            pattern_text = "\n\nKiến thức TA bổ sung:\n" + "\n".join(
                f"- [{p['name']}]: {p['description']}" for p in patterns
            )

        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và soi chart. "
            "Trả lời bằng tiếng Việt, ngắn gọn. Nếu có ảnh, hãy phân tích nến và các chỉ báo trong ảnh. "
            "Hôm nay là 26/03/2026." + pattern_text
        )

        # CẤU TRÚC VISION: Phải dùng List cho Content
        content_list = []
        
        # 1. Nếu có ảnh, nhét vào đầu tiên
        if base64_image:
            content_list.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            })

        # 2. Thêm chữ (Yêu cầu hoặc context dữ liệu)
        text_payload = f"Tin nhắn: {user_message}"
        if context_data:
            text_payload += f"\n\nDữ liệu thị trường đi kèm:\n{context_data}"
        
        content_list.append({"type": "text", "text": text_payload})

        r = requests.post(GROK_URL, headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        }, json={
            "model": "grok-4.1-fast-non-reasoning", # Dùng bản non-reasoning như sếp chốt
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_list}
            ],
            "max_tokens": 800
        }, timeout=60)
        
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Lỗi Grok Vision API: {e}"

# ── Handlers Mới ──────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi sếp gửi ảnh kèm caption"""
    msg = update.message
    photo_file = await msg.photo[-1].get_file() # Lấy ảnh nét nhất
    
    # Tải ảnh về và encode Base64
    image_bytearray = await photo_file.download_as_bytearray()
    base64_image = base64.b64encode(image_bytearray).decode('utf-8')
    
    caption = msg.caption if msg.caption else "Soi chart này giúp sếp."
    
    await msg.reply_text("⏳ Grok đang soi nến, sếp đợi tí...")
    answer = ask_grok(caption, base64_image=base64_image)
    await msg.reply_text(answer)

# ── Main Nâng Cấp ─────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Commands cũ
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ta", ta_cmd))
    
    # Handler cho Ảnh (Mới thêm)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Handler cho Chữ (Cập nhật để tránh nhận nhầm lệnh)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Bot Grok 4.1 Vision (Python) đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
