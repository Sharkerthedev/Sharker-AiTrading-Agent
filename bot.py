import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
from ta_engine import analyze_ta, get_ohlcv
from knowledge import save_pattern, get_patterns, list_patterns

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")   # thay vì GROK_API_KEY
CC_API_KEY = os.environ.get("CRYPTOCOMPARE_KEY")

# Gemini OpenAI-compatible endpoint
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

COIN_MAP = {
    "btc": "BTC", "bitcoin": "BTC",
    "eth": "ETH", "ethereum": "ETH",
    "sol": "SOL", "solana": "SOL",
    "bnb": "BNB", "xrp": "XRP",
    "doge": "DOGE", "ada": "ADA",
    "avax": "AVAX", "dot": "DOT",
    "matic": "MATIC", "polygon": "MATIC",
    "link": "LINK", "uni": "UNI",
}

TIMEFRAME_MAP = {
    "1h": "histohour", "4h": "histohour",
    "1d": "histoday", "1w": "histoday",
}

# ── Helpers ──────────────────────────────────────────────

def get_price(symbol: str) -> str:
    try:
        url = "https://min-api.cryptocompare.com/data/pricemultifull"
        r = requests.get(url, params={
            "fsyms": symbol,
            "tsyms": "USD",
            "api_key": CC_API_KEY,
        }, timeout=10)
        raw = r.json()["RAW"][symbol]["USD"]
        price = raw["PRICE"]
        change24 = raw["CHANGEPCT24HOUR"]
        high24 = raw["HIGH24HOUR"]
        low24 = raw["LOW24HOUR"]
        vol24 = raw["VOLUME24HOURTO"]
        arrow = "▲" if change24 >= 0 else "▼"
        return (
            f"💰 {symbol}/USD\n"
            f"Giá: ${price:,.4f}\n"
            f"24h: {arrow} {abs(change24):.2f}%\n"
            f"H/L: ${high24:,.2f} / ${low24:,.2f}\n"
            f"Volume 24h: ${vol24/1e6:.1f}M"
        )
    except Exception as e:
        return f"Lỗi lấy giá {symbol}: {e}"

def get_news(symbol: str = None) -> str:
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {
            "api_key": CC_API_KEY,
            "sortOrder": "latest",
            "lang": "EN",
        }
        if symbol:
            params["categories"] = symbol
        r = requests.get(url, params=params, timeout=10)
        items = r.json().get("Data", [])[:5]
        if not items:
            return "Không có tin tức mới."
        lines = [f"📰 Crypto News{' — ' + symbol if symbol else ''}:\n"]
        for i, item in enumerate(items, 1):
            title = item.get("title", "")
            url_item = item.get("url", "")
            source = item.get("source", "")
            lines.append(f"{i}. [{source}] {title}\n{url_item}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"Lỗi lấy news: {e}"

def ask_gemini(user_message: str, context_data: str = "") -> str:
    """Gọi Gemini API với OpenAI-compatible endpoint."""
    try:
        patterns = get_patterns()
        pattern_text = ""
        if patterns:
            pattern_text = "\n\nKiến thức TA từ chủ nhân bot:\n" + "\n".join(
                f"- [{p['name']}]: {p['description']}" for p in patterns
            )

        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và phân tích kỹ thuật (TA). "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Phân tích dựa trên RSI, MACD, Bollinger Bands, EMA, support/resistance, volume. "
            "Không đưa ra lời khuyên tài chính trực tiếp. Chỉ phân tích kỹ thuật."
            + pattern_text
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if context_data:
            messages.append({"role": "user", "content": f"Dữ liệu thị trường:\n{context_data}"})
            messages.append({"role": "assistant", "content": "Đã nhận dữ liệu thị trường."})

        messages.append({"role": "user", "content": user_message})

        r = requests.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-2-0-flash",   # Có thể đổi thành gemini-2.5-flash-preview-05-20 nếu muốn
                "messages": messages,
                "max_tokens": 600,
                "temperature": 0.7,
            },
            timeout=30
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Lỗi Gemini API: {e}"

def ask_gemini_with_vision(question: str, image_url: str) -> str:
    """Gọi Gemini Vision qua OpenAI-compatible endpoint."""
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]
        r = requests.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-2.0-flash",   # vision cũng dùng model này
                "messages": messages,
                "max_tokens": 600,
                "temperature": 0.7,
            },
            timeout=30
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Lỗi Gemini Vision: {e}"

# ── Handlers ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xin chào! Tui là Crypto AI Bot v2 (Gemini).\n\n"
        "📊 Giá & Data:\n"
        "/price btc — Xem giá\n"
        "/ta btc 1h — Phân tích TA (1h/4h/1d)\n"
        "/news — Tin tức mới nhất\n"
        "/news btc — Tin về coin cụ thể\n\n"
        "🤖 AI & Học:\n"
        "/ask [câu hỏi] — Hỏi AI crypto/TA\n"
        "/teach [tên] | [mô tả] — Dạy bot pattern mới\n"
        "/patterns — Xem pattern đã dạy\n\n"
        "🖼️ Gửi ảnh (có hoặc không caption) để phân tích!\n\n"
        "Chat tự nhiên tiếng Việt cũng được!"
    )

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /price btc")
        return
    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    await update.message.reply_text(get_price(symbol))

async def ta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ta btc 1h
    Lấy OHLCV → tính TA indicators → Gemini phân tích
    """
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /ta btc 1h  (timeframe: 1h, 4h, 1d)")
        return

    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    tf = args[1].lower() if len(args) > 1 else "1h"
    limit = 4 if tf == "4h" else 1

    await update.message.reply_text(f"⏳ Đang phân tích {symbol} {tf}...")

    endpoint = TIMEFRAME_MAP.get(tf, "histohour")
    df = get_ohlcv(symbol, endpoint, limit=200, cc_key=CC_API_KEY)
    if df is None:
        await update.message.reply_text("Không lấy được dữ liệu OHLCV.")
        return

    ta_summary = analyze_ta(df)
    await update.message.reply_text(ta_summary["text"])

    gemini_answer = ask_gemini(
        f"Phân tích kỹ thuật {symbol} timeframe {tf}. "
        "Xu hướng hiện tại? Vùng support/resistance quan trọng? Nên chờ gì?",
        context_data=ta_summary["data_for_grok"]
    )
    await update.message.reply_text(f"🤖 Gemini phân tích:\n\n{gemini_answer}")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = None
    if context.args:
        symbol = COIN_MAP.get(context.args[0].lower(), context.args[0].upper())
    await update.message.reply_text("Đang lấy tin tức...")
    await update.message.reply_text(get_news(symbol))

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Dùng: /ask RSI 30 trên BTC 4h có phải oversold không?")
        return
    question = " ".join(context.args)
    await update.message.reply_text("Đang hỏi Gemini...")
    await update.message.reply_text(ask_gemini(question))

async def teach_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /teach Bullish Engulfing | Nến đảo chiều tăng, thân nến xanh lớn bao trùm nến đỏ trước đó,
    xuất hiện ở vùng support thì xác suất cao
    """
    if not context.args:
        await update.message.reply_text(
            "Cú pháp: /teach [Tên pattern] | [Mô tả chi tiết]\n\n"
            "Ví dụ:\n/teach Bullish Engulfing | Nến xanh bao trùm nến đỏ tại support, tín hiệu mua"
        )
        return

    full_text = " ".join(context.args)
    if "|" not in full_text:
        await update.message.reply_text("Cần có dấu | để phân tách tên và mô tả.\nVí dụ: /teach RSI Oversold | RSI dưới 30 tại support mạnh")
        return

    parts = full_text.split("|", 1)
    name = parts[0].strip()
    description = parts[1].strip()

    save_pattern(name, description)
    await update.message.reply_text(
        f"✅ Đã lưu pattern: *{name}*\n\n"
        f"Mô tả: {description}\n\n"
        f"Bot sẽ áp dụng kiến thức này khi phân tích TA.",
        parse_mode="Markdown"
    )

async def patterns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    patterns = list_patterns()
    if not patterns:
        await update.message.reply_text(
            "Chưa có pattern nào. Dùng /teach để dạy bot!\n\n"
            "Ví dụ: /teach Bullish Engulfing | Nến xanh bao trùm nến đỏ tại support"
        )
        return
    await update.message.reply_text(patterns)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn có ảnh."""
    photo = update.message.photo[-1]  # lấy ảnh chất lượng cao nhất
    file = await context.bot.get_file(photo.file_id)
    file_url = file.file_path  # URL tạm thời của ảnh trên Telegram

    caption = update.message.caption or "Phân tích ảnh này"
    await update.message.reply_text("🖼️ Đang phân tích ảnh với Gemini Vision...")

    answer = ask_gemini_with_vision(caption, file_url)
    await update.message.reply_text(answer)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    # Nhận diện hỏi giá
    for key, symbol in COIN_MAP.items():
        if key in text and any(w in text for w in ["giá", "price", "bao nhiêu", "mấy đô", "mấy"]):
            await update.message.reply_text(get_price(symbol))
            return

    # Nhận diện hỏi TA
    if any(w in text for w in ["ta", "phân tích", "rsi", "macd", "chart", "signal", "tín hiệu"]):
        for key, symbol in COIN_MAP.items():
            if key in text:
                await update.message.reply_text(f"⏳ Đang phân tích {symbol} 1h...")
                endpoint = "histohour"
                df = get_ohlcv(symbol, endpoint, limit=200, cc_key=CC_API_KEY)
                if df:
                    ta_summary = analyze_ta(df)
                    await update.message.reply_text(ta_summary["text"])
                    answer = ask_gemini(update.message.text, ta_summary["data_for_grok"])
                    await update.message.reply_text(f"🤖 Gemini:\n\n{answer}")
                    return

    # Nhận diện news
    if any(w in text for w in ["news", "tin tức", "tin mới", "hot"]):
        await update.message.reply_text(get_news())
        return

    # Mặc định: hỏi Gemini
    await update.message.reply_text("Đang xử lý...")
    answer = ask_gemini(update.message.text)
    await update.message.reply_text(answer)

# ── Main ─────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ta", ta_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("teach", teach_cmd))
    app.add_handler(CommandHandler("patterns", patterns_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))   # thêm handler ảnh
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Crypto AI Bot v2 (Gemini) đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
