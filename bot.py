import os
import requests
import base64
import io
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)

# Giữ nguyên các file phụ của sếp
try:
    from ta_engine import analyze_ta, get_ohlcv
    from knowledge import save_pattern, get_patterns, list_patterns
except ImportError:
    # Tránh lỗi nếu sếp chưa có file phụ, bot vẫn chạy được chat thường
    print("⚠️ Cảnh báo: Thiếu file ta_engine.py hoặc knowledge.py")

# Lấy Key từ Environment Variables trên Railway
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROK_API_KEY = os.environ.get("GROK_API_KEY")
CC_API_KEY = os.environ.get("CRYPTOCOMPARE_KEY")
GROK_URL = "https://api.x.ai/v1/chat/completions"

COIN_MAP = {
    "btc": "BTC", "bitcoin": "BTC",
    "eth": "ETH", "ethereum": "ETH",
    "sol": "SOL", "solana": "SOL",
    "bnb": "BNB", "xrp": "XRP",
}

# ── Helpers ──────────────────────────────────────────────

def ask_grok(user_message: str, context_data: str = "", base64_image: str = None) -> str:
    try:
        # Lấy kiến thức đã dạy (nếu có file knowledge)
        pattern_text = ""
        try:
            patterns = get_patterns()
            if patterns:
                pattern_text = "\n\nKiến thức TA bổ sung:\n" + "\n".join(
                    f"- [{p['name']}]: {p['description']}" for p in patterns
                )
        except: pass

        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế. "
            "Nếu có ảnh chart, hãy soi nến và các chỉ báo kỹ thuật để đưa ra nhận định."
            + pattern_text
        )

        # CẤU TRÚC MESSAGE CHO VISION (BẮT BUỘC DẠNG LIST)
        content_list = []
        
        # 1. Nếu có ảnh, nhét vào đầu tiên
        if base64_image:
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                    "detail": "high"
                }
            })

        # 2. Thêm nội dung chữ
        text_payload = f"Yêu cầu: {user_message}"
        if context_data:
            text_payload += f"\n\nDữ liệu kỹ thuật đi kèm:\n{context_data}"
        
        content_list.append({"type": "text", "text": text_payload})

        # Gửi request sang xAI
        r = requests.post(GROK_URL, headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        }, json={
            "model": "grok-4.1-fast-non-reasoning", # Bản sếp có $5 và nhìn được ảnh
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_list}
            ],
            "temperature": 0.5
        }, timeout=60)
        
        res_json = r.json()
        if "choices" in res_json:
            return res_json["choices"][0]["message"]["content"]
        else:
            return f"❌ Lỗi API xAI: {res_json.get('error', {}).get('message', 'Dữ liệu không xác định')}"
            
    except Exception as e:
        return f"❌ Lỗi xử lý Grok: {str(e)}"

# ── Handlers ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Chào sếp! Gửi ảnh chart hoặc nhắn tin để em soi kèo cho nhé!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi sếp gửi ảnh"""
    msg = update.message
    await msg.reply_text("⏳ Đang tải ảnh và soi nến, sếp chờ em tí...")

    try:
        # Lấy ảnh chất lượng cao nhất
        photo_file = await msg.photo[-1].get_file()
        
        # Tải về bytearray
        img_buffer = await photo_file.download_as_bytearray()
        
        # Chuyển sang Base64
        base64_image = base64.b64encode(img_buffer).decode('utf-8')
        
        # Lấy caption của sếp (ví dụ: 'soi con này khung h1')
        caption = msg.caption if msg.caption else "Hãy phân tích hình ảnh chart này."
        
        # Gọi Grok
        answer = ask_grok(caption, base64_image=base64_image)
        await msg.reply_text(answer)

    except Exception as e:
        await msg.reply_text(f"❌ Lỗi tải ảnh: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn văn bản bình thường"""
    text = update.message.text
    await update.message.reply_text("🤖 Đang suy nghĩ...")
    answer = ask_grok(text)
    await update.message.reply_text(answer)

# ── Main ─────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        print("❌ Thiếu TELEGRAM_TOKEN trong Variables!")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Lệnh cơ bản
    app.add_handler(CommandHandler("start", start))
    
    # XỬ LÝ ẢNH (Phải có dòng này mới không bị 'im')
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # XỬ LÝ CHỮ
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Bot Grok 4.1 Vision đã sẵn sàng trên Railway!")
    app.run_polling()

if __name__ == "__main__":
    main()
