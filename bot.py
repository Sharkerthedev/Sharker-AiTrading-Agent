import os
import requests
import datetime
import base64
import re
import sys
import json
import subprocess
import sqlite3
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)

# Các module nội bộ
from ta_engine import analyze_ta, get_ohlcv
from knowledge import save_pattern, get_patterns, list_patterns
from paper_trade import paper_balance, paper_buy, paper_sell, paper_history, init_paper_db
from memory import init_memory_db, save_message, get_recent_messages, clear_memory

# Lấy biến môi trường
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CC_API_KEY = os.environ.get("CRYPTOCOMPARE_KEY")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

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

# ----------------------------------------------------------------------
# Hàm kiểm tra chủ nhân
async def check_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Bot này chỉ dành cho chủ nhân.")
        return False
    return True

# ----------------------------------------------------------------------
# Các helper (giá, news, Gemini, ...)
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

def get_current_price(symbol: str) -> float:
    try:
        url = "https://min-api.cryptocompare.com/data/price"
        r = requests.get(url, params={"fsym": symbol, "tsyms": "USD", "api_key": CC_API_KEY}, timeout=5)
        return r.json()["USD"]
    except:
        return None

def ask_gemini(user_message: str, context_data: str = "", history=None) -> str:
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        patterns = get_patterns()
        pattern_text = ""
        if patterns:
            pattern_text = "\n\nKiến thức TA từ chủ nhân bot:\n" + "\n".join(
                f"- [{p['name']}]: {p['description']}" for p in patterns
            )

        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và phân tích kỹ thuật (TA). "
            f"Hôm nay là {current_time}. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Phân tích dựa trên RSI, MACD, Bollinger Bands, EMA, support/resistance, volume. "
            "Bạn có thể đưa ra nhận định về xu hướng (tăng/giảm/đi ngang) và các kịch bản, nhưng không đưa ra lời khuyên tài chính trực tiếp (không nói 'nên mua' hay 'nên bán')."
            + pattern_text
        )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if context_data:
            messages.append({"role": "user", "content": f"Dữ liệu thị trường:\n{context_data}"})
            messages.append({"role": "assistant", "content": "Đã nhận dữ liệu thị trường."})

        if history:
            for role, content in history:
                if len(content) > 500:
                    content = content[:500] + "..."
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        response = requests.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-2.5-flash",
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=30
        )

        if response.status_code != 200:
            return f"Lỗi Gemini API: {response.status_code} - {response.text}"

        data = response.json()
        if "choices" not in data:
            return f"Lỗi cấu trúc phản hồi: {data}"

        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Lỗi Gemini API: {e}"

def ask_gemini_with_vision(question: str, image_base64: str, mime_type: str = "image/jpeg") -> str:
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và phân tích kỹ thuật (TA). "
            f"Hôm nay là {current_time}. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Phân tích hình ảnh được cung cấp và trả lời câu hỏi. "
            "Bạn có thể đưa ra nhận định về xu hướng nhưng không đưa ra lời khuyên tài chính trực tiếp."
        )
        data_url = f"data:{mime_type};base64,{image_base64}"
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ]
        response = requests.post(
            GEMINI_URL,
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-2.5-flash",
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=30
        )

        if response.status_code != 200:
            return f"Lỗi Gemini Vision: {response.status_code} - {response.text}"

        data = response.json()
        if "choices" not in data:
            return f"Lỗi cấu trúc phản hồi: {data}"

        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Lỗi Gemini Vision: {e}"

def detect_coin_in_text(text: str) -> str:
    for key, symbol in COIN_MAP.items():
        if key in text:
            return symbol
    return None

# ----------------------------------------------------------------------
# Các handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
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
        "📈 Paper Trade:\n"
        "/paper_balance — Xem tài khoản ảo\n"
        "/paper_buy btc 0.01 — Mua 0.01 BTC\n"
        "/paper_sell btc 0.01 — Bán 0.01 BTC\n"
        "/paper_history — Xem lịch sử giao dịch ảo\n\n"
        "🧠 Bộ nhớ: bot nhớ 10 tin nhắn gần nhất\n"
        "/clear_memory — Xóa bộ nhớ hội thoại\n\n"
        "🖼️ Gửi ảnh (có caption) để phân tích chart!\n\n"
        "Chat tự nhiên tiếng Việt: 'btc giá', 'phân tích eth', 'btc nên long hay short?'"
    )

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /price btc")
        return
    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    await update.message.reply_text(get_price(symbol))

async def ta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /ta btc 1h (timeframe: 1h, 4h, 1d)")
        return

    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    tf = args[1].lower() if len(args) > 1 else "1h"

    await update.message.reply_text(f"⏳ Đang phân tích {symbol} {tf}...")

    endpoint = TIMEFRAME_MAP.get(tf, "histohour")
    df = get_ohlcv(symbol, endpoint, limit=1000, cc_key=CC_API_KEY)
    if df is None:
        await update.message.reply_text("Không lấy được dữ liệu OHLCV.")
        return

    ta_summary = analyze_ta(df)
    await update.message.reply_text(ta_summary["text"])

    user_id = update.effective_user.id
    history = get_recent_messages(user_id, limit=10)
    gemini_answer = ask_gemini(
        f"Phân tích kỹ thuật {symbol} timeframe {tf}. "
        "Xu hướng hiện tại? Vùng support/resistance quan trọng? Nên chờ gì?",
        context_data=ta_summary["data_for_grok"],
        history=history
    )
    # Lưu tin nhắn và phản hồi
    save_message(user_id, "user", f"/ta {symbol} {tf}")
    save_message(user_id, "assistant", gemini_answer)
    await update.message.reply_text(f"🤖 Gemini phân tích:\n\n{gemini_answer}")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    symbol = None
    if context.args:
        symbol = COIN_MAP.get(context.args[0].lower(), context.args[0].upper())
    await update.message.reply_text("Đang lấy tin tức...")
    await update.message.reply_text(get_news(symbol))

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    if not context.args:
        await update.message.reply_text("Dùng: /ask RSI 30 trên BTC 4h có phải oversold không?")
        return
    question = " ".join(context.args)
    user_id = update.effective_user.id
    history = get_recent_messages(user_id, limit=10)
    answer = ask_gemini(question, history=history)
    save_message(user_id, "user", question)
    save_message(user_id, "assistant", answer)
    await update.message.reply_text(answer)

async def teach_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
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
    if not await check_owner(update, context):
        return
    patterns = list_patterns()
    if not patterns:
        await update.message.reply_text(
            "Chưa có pattern nào. Dùng /teach để dạy bot!\n\n"
            "Ví dụ: /teach Bullish Engulfing | Nến xanh bao trùm nến đỏ tại support"
        )
        return
    await update.message.reply_text(patterns)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    mime_type = "image/jpeg"

    caption = update.message.caption or "Phân tích ảnh này"
    await update.message.reply_text("🖼️ Đang phân tích ảnh với Gemini Vision...")

    answer = ask_gemini_with_vision(caption, base64_image, mime_type)
    user_id = update.effective_user.id
    save_message(user_id, "user", f"[Image] {caption}")
    save_message(user_id, "assistant", answer)
    await update.message.reply_text(answer)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    user_id = update.effective_user.id
    user_text = update.message.text

    # Lấy lịch sử hội thoại
    history = get_recent_messages(user_id, limit=10)

    # Hỏi giá
    text_lower = user_text.lower()
    for key, symbol in COIN_MAP.items():
        if key in text_lower and any(w in text_lower for w in ["giá", "price", "bao nhiêu", "mấy đô", "mấy"]):
            await update.message.reply_text(get_price(symbol))
            save_message(user_id, "user", user_text)
            return

    # Hỏi TA / quyết định giao dịch
    is_trade_question = any(w in text_lower for w in ["long", "short", "đợi", "nên", "mua", "bán", "vào lệnh", "xu hướng"])
    is_ta_question = any(w in text_lower for w in ["ta", "phân tích", "rsi", "macd", "chart", "signal", "tín hiệu"])

    if is_ta_question or is_trade_question:
        coin_symbol = detect_coin_in_text(text_lower)
        if not coin_symbol:
            coin_symbol = "BTC"
            await update.message.reply_text(f"🔍 Không thấy tên coin, tôi sẽ phân tích BTC.")
        await update.message.reply_text(f"⏳ Đang phân tích {coin_symbol} 1h...")
        endpoint = "histohour"
        df = get_ohlcv(coin_symbol, endpoint, limit=1000, cc_key=CC_API_KEY)
        if df is not None:
            ta_summary = analyze_ta(df)
            await update.message.reply_text(ta_summary["text"])
            answer = ask_gemini(user_text, context_data=ta_summary["data_for_grok"], history=history)
        else:
            answer = ask_gemini(user_text, history=history)
        save_message(user_id, "user", user_text)
        save_message(user_id, "assistant", answer)
        await update.message.reply_text(f"🤖 Gemini:\n\n{answer}")
        return

    # Hỏi news
    if any(w in text_lower for w in ["news", "tin tức", "tin mới", "hot"]):
        await update.message.reply_text(get_news())
        save_message(user_id, "user", user_text)
        return

    # Mặc định: hỏi AI với bộ nhớ
    await update.message.reply_text("Đang xử lý...")
    answer = ask_gemini(user_text, history=history)
    save_message(user_id, "user", user_text)
    save_message(user_id, "assistant", answer)
    await update.message.reply_text(answer)

# Paper trade handlers
async def paper_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    balance_text = paper_balance()
    await update.message.reply_text(balance_text)

async def paper_buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Dùng: /paper_buy <symbol> <số lượng>")
        return
    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    try:
        quantity = float(args[1])
    except:
        await update.message.reply_text("Số lượng không hợp lệ")
        return
    price = get_current_price(symbol)
    if price is None:
        await update.message.reply_text("Không lấy được giá")
        return
    result = paper_buy(symbol, quantity, price)
    await update.message.reply_text(result)

async def paper_sell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Dùng: /paper_sell <symbol> <số lượng>")
        return
    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    try:
        quantity = float(args[1])
    except:
        await update.message.reply_text("Số lượng không hợp lệ")
        return
    price = get_current_price(symbol)
    if price is None:
        await update.message.reply_text("Không lấy được giá")
        return
    result = paper_sell(symbol, quantity, price)
    await update.message.reply_text(result)

async def paper_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    history_text = paper_history()
    await update.message.reply_text(history_text)

async def clear_memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_owner(update, context):
        return
    user_id = update.effective_user.id
    clear_memory(user_id)
    await update.message.reply_text("🗑️ Đã xóa bộ nhớ hội thoại.")

# ----------------------------------------------------------------------
# Main
def main():
    # Khởi tạo cơ sở dữ liệu
    init_memory_db()
    init_paper_db()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ta", ta_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("teach", teach_cmd))
    app.add_handler(CommandHandler("patterns", patterns_cmd))
    app.add_handler(CommandHandler("paper_balance", paper_balance_cmd))
    app.add_handler(CommandHandler("paper_buy", paper_buy_cmd))
    app.add_handler(CommandHandler("paper_sell", paper_sell_cmd))
    app.add_handler(CommandHandler("paper_history", paper_history_cmd))
    app.add_handler(CommandHandler("clear_memory", clear_memory_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Crypto AI Bot v2 (Gemini 2.5 Flash) đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
