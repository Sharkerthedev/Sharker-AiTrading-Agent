import os
import requests
import datetime
import base64
import sqlite3
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
from ta_engine import analyze_ta, get_ohlcv
from knowledge import save_pattern, get_patterns, list_patterns
from rag_memory import RagMemory

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY")
CC_API_KEY = os.environ.get("CRYPTOCOMPARE_KEY")

ALLOWED_USERS_STR = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = set()
if ALLOWED_USERS_STR:
    for uid in ALLOWED_USERS_STR.split(','):
        try:
            ALLOWED_USERS.add(int(uid.strip()))
        except ValueError:
            pass

OWNER_ID = int(os.environ.get("OWNER_ID", 0))
if OWNER_ID:
    ALLOWED_USERS.add(OWNER_ID)

ollama_client = OpenAI(
    api_key=OLLAMA_API_KEY,
    base_url="https://ollama.com/v1"
)

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

rag = RagMemory()

DATA_DIR = os.environ.get("DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "chat_memory.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  role TEXT,
                  content TEXT,
                  timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_message(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, role, content, timestamp))
    conn.commit()
    conn.close()

def get_recent_messages(user_id, limit=7):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))

init_db()

async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Bạn không được phép sử dụng bot này.")
        return False
    return True

def get_current_price(symbol: str) -> float:
    try:
        url = "https://min-api.cryptocompare.com/data/price"
        r = requests.get(url, params={"fsym": symbol, "tsyms": "USD", "api_key": CC_API_KEY}, timeout=5)
        return r.json()["USD"]
    except:
        return None

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

def ask_ollama_with_rag(user_message: str, context_data: str = "", history=None) -> str:
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        patterns = get_patterns()
        pattern_text = ""
        if patterns:
            pattern_text = "\n\nKiến thức TA từ chủ nhân bot:\n" + "\n".join(
                f"- [{p['name']}]: {p['description']}" for p in patterns
            )

        rag_context = ""
        try:
            relevant_knowledge = rag.search_knowledge(user_message, n_results=3)
            if relevant_knowledge:
                rag_context = "\n\n**📚 Kiến thức đã học trước đây:**\n" + "\n".join(relevant_knowledge)
        except Exception as e:
            print(f"Lỗi RAG search: {e}")

        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và phân tích kỹ thuật (TA). "
            f"Hôm nay là {current_time}. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Chỉ phân tích khi người dùng yêu cầu cụ thể. Không tự động thêm bảng chỉ số. "
            "Hãy trả lời tối đa 5-7 câu, tập trung vào ý chính."
            + pattern_text
            + rag_context
        )

        messages = [{"role": "system", "content": system_prompt}]

        if context_data:
            messages.append({"role": "user", "content": f"Dữ liệu thị trường:\n{context_data}"})
            messages.append({"role": "assistant", "content": "Đã nhận dữ liệu thị trường."})

        if history:
            for role, content in history:
                if len(content) > 500:
                    content = content[:500] + "..."
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        response = ollama_client.chat.completions.create(
            model="gemini-3-flash-preview",
            messages=messages,
            max_tokens=1500,
            temperature=0.7,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Lỗi Ollama API: {e}"

def ask_ollama_with_vision(question: str, image_base64: str, mime_type: str = "image/jpeg") -> str:
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_prompt = (
            "Bạn là AI assistant chuyên về crypto trading và phân tích kỹ thuật (TA). "
            f"Hôm nay là {current_time}. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Phân tích hình ảnh được cung cấp và trả lời câu hỏi. "
            "Không tự động thêm bảng chỉ số, chỉ trả lời ngắn gọn."
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

        response = ollama_client.chat.completions.create(
            model="gemini-3-flash-preview",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Lỗi Ollama Vision: {e}"

def detect_coin_in_text(text: str) -> str:
    for key, symbol in COIN_MAP.items():
        if key in text:
            return symbol
    return None

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    await update.message.reply_text(
        "👋 Xin chào! Tui là Crypto AI Bot v2 (Ollama + RAG).\n\n"
        "📊 Giá & Data:\n"
        "/price btc — Xem giá\n"
        "/ta btc 1h — Phân tích TA (1h/4h/1d)\n"
        "/news — Tin tức mới nhất\n"
        "/news btc — Tin về coin cụ thể\n\n"
        "🤖 AI & Học:\n"
        "/ask [câu hỏi] — Hỏi AI crypto/TA\n"
        "/teach [tên] | [mô tả] — Dạy bot pattern mới\n"
        "/patterns — Xem pattern đã dạy\n"
        "/memory — Xem kiến thức bot đã học (RAG)\n\n"
        "🖼️ Gửi ảnh (có hoặc không caption) để phân tích!\n\n"
        "Chat tự nhiên tiếng Việt cũng được!\n"
        "Ví dụ: 'btc hôm nay nên long hay short?'"
    )

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /price btc")
        return
    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    await update.message.reply_text(get_price(symbol))

async def ta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Dùng: /ta btc 1h  (timeframe: 1h, 4h, 1d)")
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

    user_id = update.effective_user.id
    history = get_recent_messages(user_id, limit=7)

    prompt = (
        f"Dữ liệu kỹ thuật {symbol} timeframe {tf}:\n{ta_summary['data_for_grok']}\n\n"
        "Hãy phân tích ngắn gọn: xu hướng hiện tại? Vùng hỗ trợ/kháng cự quan trọng? Điểm cần chú ý?"
    )

    answer = ask_ollama_with_rag(
        user_message=prompt,
        context_data="",
        history=history
    )

    save_message(user_id, "user", f"/ta {symbol} {tf}")
    save_message(user_id, "assistant", answer)

    try:
        rag.save_analysis(symbol, answer, ta_summary)
    except Exception as e:
        print(f"Lỗi lưu RAG: {e}")

    await update.message.reply_text(f"🤖 Phân tích {symbol} {tf}:\n\n{answer}")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    symbol = None
    if context.args:
        symbol = COIN_MAP.get(context.args[0].lower(), context.args[0].upper())
    await update.message.reply_text("Đang lấy tin tức...")
    await update.message.reply_text(get_news(symbol))

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    if not context.args:
        await update.message.reply_text("Dùng: /ask RSI 30 trên BTC 4h có phải oversold không?")
        return
    question = " ".join(context.args)
    user_id = update.effective_user.id
    history = get_recent_messages(user_id, limit=7)
    answer = ask_ollama_with_rag(question, history=history)
    save_message(user_id, "user", f"/ask {question}")
    save_message(user_id, "assistant", answer)
    await update.message.reply_text(answer)

async def teach_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
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

    try:
        rag.add_knowledge(
            content=f"Pattern: {name} - {description}",
            metadata={"type": "pattern", "name": name}
        )
    except Exception as e:
        print(f"Lỗi lưu pattern vào RAG: {e}")

    await update.message.reply_text(
        f"✅ Đã lưu pattern: *{name}*\n\n"
        f"Mô tả: {description}\n\n"
        f"Bot sẽ áp dụng kiến thức này khi phân tích TA.",
        parse_mode="Markdown"
    )

async def patterns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    patterns = list_patterns()
    if not patterns:
        await update.message.reply_text(
            "Chưa có pattern nào. Dùng /teach để dạy bot!\n\n"
            "Ví dụ: /teach Bullish Engulfing | Nến xanh bao trùm nến đỏ tại support"
        )
        return
    await update.message.reply_text(patterns)

async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    try:
        results = rag.collection.get(limit=10)
        if results['documents'] and results['documents'][0]:
            msg = "📚 **Kiến thức bot đã học (RAG):**\n\n"
            for i, doc in enumerate(results['documents'][:10], 1):
                if doc and len(doc) > 0:
                    msg += f"{i}. {doc[:200]}...\n\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("Chưa có kiến thức nào được lưu trong RAG.")
    except Exception as e:
        await update.message.reply_text(f"Lỗi truy xuất RAG: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    mime_type = "image/jpeg"

    caption = update.message.caption or "Phân tích ảnh này"
    await update.message.reply_text("🖼️ Đang phân tích ảnh với Ollama Vision...")

    answer = ask_ollama_with_vision(caption, base64_image, mime_type)
    user_id = update.effective_user.id
    save_message(user_id, "user", "[ảnh] " + caption)
    save_message(user_id, "assistant", answer)
    await update.message.reply_text(answer)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    user_id = update.effective_user.id
    user_text = update.message.text

    save_message(user_id, "user", user_text)

    text_lower = user_text.lower()

    # Hỏi giá
    for key, symbol in COIN_MAP.items():
        if key in text_lower and any(w in text_lower for w in ["giá", "price", "bao nhiêu", "mấy đô", "mấy"]):
            reply = get_price(symbol)
            await update.message.reply_text(reply)
            save_message(user_id, "assistant", reply)
            return

    # Hỏi TA / quyết định
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
            prompt = (
                f"Dữ liệu kỹ thuật {coin_symbol} khung 1h:\n{ta_summary['data_for_grok']}\n\n"
                f"Câu hỏi: {user_text}\nHãy trả lời ngắn gọn, tập trung vào phân tích."
            )
            history = get_recent_messages(user_id, limit=7)
            answer = ask_ollama_with_rag(prompt, context_data="", history=history)
            try:
                rag.save_analysis(coin_symbol, answer, ta_summary)
            except Exception as e:
                print(f"Lỗi lưu RAG: {e}")
        else:
            answer = ask_ollama_with_rag(user_text, history=get_recent_messages(user_id, limit=7))
        
        await update.message.reply_text(f"🤖 Ollama:\n\n{answer}")
        save_message(user_id, "assistant", answer)
        return

    # Hỏi news
    if any(w in text_lower for w in ["news", "tin tức", "tin mới", "hot"]):
        reply = get_news()
        await update.message.reply_text(reply)
        save_message(user_id, "assistant", reply)
        return

    # Mặc định: hỏi AI
    await update.message.reply_text("Đang xử lý...")
    history = get_recent_messages(user_id, limit=6)
    answer = ask_ollama_with_rag(user_text, history=history)
    await update.message.reply_text(answer)
    save_message(user_id, "assistant", answer)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ta", ta_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("ask", ask_cmd))
    app.add_handler(CommandHandler("teach", teach_cmd))
    app.add_handler(CommandHandler("patterns", patterns_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Crypto AI Bot v2 (Ollama + RAG) đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
