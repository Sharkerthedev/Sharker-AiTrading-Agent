import os
import requests
import datetime
import base64
import sqlite3
import ta
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
            "Bạn là Sophia, trader nữ chuyên phân tích crypto. "
            f"Hôm nay là {current_time}. "
            "Bạn sẽ nhận được dữ liệu kỹ thuật đầy đủ (giá, RSI, MACD, EMA, Volume, PVSRA, v.v.). "
            "HÃY DỰA VÀO DỮ LIỆU NÀY LÀM CƠ SỞ CHÍNH để xác định xu hướng, vùng hỗ trợ/kháng cự và tín hiệu. "
            "Sau đó, bổ sung các quy tắc, mẫu hình đã học (Fibonacci, mô hình nến, v.v.) để tăng độ chính xác. "
            "Trả lời bằng tiếng Việt, ngắn gọn, tập trung vào ý chính."
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
            "Bạn là Sophia, trader nữ chuyên phân tích crypto. "
            f"Hôm nay là {current_time}. "
            "Trả lời bằng tiếng Việt, ngắn gọn, thực tế, như một trader kinh nghiệm. "
            "Phân tích hình ảnh được cung cấp và trả lời câu hỏi. "
            "Chỉ dựa vào ảnh để đưa ra nhận định."
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

def detect_timeframe_in_text(text: str) -> str:
    """Phát hiện timeframe trong câu hỏi: 5m,15m,1h,4h,1d,1w. Mặc định 1h nếu không có."""
    text = text.lower()
    import re
    if re.search(r'\b5m\b', text):
        return "5m"
    if re.search(r'\b15m\b', text):
        return "15m"
    if re.search(r'\b4h\b', text):
        return "4h"
    if re.search(r'\b1d\b', text):
        return "1d"
    if re.search(r'\b1w\b', text):
        return "1w"
    if re.search(r'\b1h\b', text):
        return "1h"
    return "1h"

# ──── Signal Engine ──────────────────────────────────────────────

def _parse_indicators(df):
    """
    Tính indicators thẳng từ DataFrame — không parse text.
    Trả về dict các giá trị cần cho cả 2 hệ thống.
    """
    import ta as ta_lib
    close  = df["close"]
    volume = df["volume"]

    rsi       = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    macd_obj  = ta_lib.trend.MACD(close)
    macd_hist = macd_obj.macd_diff()
    macd_line = macd_obj.macd()
    macd_sig  = macd_obj.macd_signal()

    ema = {}
    for p in [5, 13, 50, 200, 800]:
        if len(close) >= p:
            ema[p] = ta_lib.trend.EMAIndicator(close, window=p).ema_indicator()
        else:
            ema[p] = None

    vol_sma20 = volume.rolling(20).mean()

    return {
        "price":      close.iloc[-1],
        "rsi":        rsi.iloc[-1],
        "rsi_prev":   rsi.iloc[-2],
        "macd_hist":  macd_hist.iloc[-1],
        "macd_hist_prev": macd_hist.iloc[-2],
        "macd_line":  macd_line.iloc[-1],
        "macd_sig":   macd_sig.iloc[-1],
        "ema5":       ema[5].iloc[-1]   if ema[5]   is not None else None,
        "ema13":      ema[13].iloc[-1]  if ema[13]  is not None else None,
        "ema50":      ema[50].iloc[-1]  if ema[50]  is not None else None,
        "ema200":     ema[200].iloc[-1] if ema[200]  is not None else None,
        "ema800":     ema[800].iloc[-1] if ema[800]  is not None else None,
        "vol_ratio":  volume.iloc[-1] / vol_sma20.iloc[-1] if vol_sma20.iloc[-1] else 1.0,
    }


def system1_check(ind: dict) -> str | None:
    """
    Hệ thống 1 — EMA Stack Trend Filter
    Cần EMA xếp đúng thứ tự + RSI trung tính + MACD hist tăng + Volume
    Ít signal nhưng chất lượng cao.
    """
    p = ind["price"]
    e5, e13, e50, e200 = ind["ema5"], ind["ema13"], ind["ema50"], ind["ema200"]
    if any(v is None for v in [e5, e13, e50, e200]):
        return None

    rsi  = ind["rsi"]
    hist = ind["macd_hist"]
    hist_prev = ind["macd_hist_prev"]
    vol  = ind["vol_ratio"]

    # LONG: EMA stack tăng + giá trên EMA50 + RSI 45-65 + MACD hist tăng + volume
    if (e5 > e13 > e50 > e200
            and p > e50
            and 45 <= rsi <= 65
            and hist > 0 and hist > hist_prev
            and vol >= 1.0):
        return "LONG"

    # SHORT: EMA stack giảm + giá dưới EMA50 + RSI 35-55 + MACD hist giảm + volume
    if (e5 < e13 < e50 < e200
            and p < e50
            and 35 <= rsi <= 55
            and hist < 0 and hist < hist_prev
            and vol >= 1.0):
        return "SHORT"

    return None


def system2_check(ind: dict) -> str | None:
    """
    Hệ thống 2 — RSI Bounce tại EMA động
    Giá bounce từ EMA13/50 + RSI vừa chạm vùng extreme rồi đảo chiều
    + MACD hist đổi dấu (zero cross).
    Bắt được cả sideway / pullback trong uptrend.
    """
    p = ind["price"]
    e13, e50, e200, e800 = ind["ema13"], ind["ema50"], ind["ema200"], ind["ema800"]
    if any(v is None for v in [e13, e50, e200]):
        return None

    rsi      = ind["rsi"]
    rsi_prev = ind["rsi_prev"]
    hist     = ind["macd_hist"]
    hist_prev = ind["macd_hist_prev"]

    # Giá đang gần EMA13 hoặc EMA50 (trong vòng 0.3%)
    near_ema13 = abs(p - e13) / p < 0.003
    near_ema50 = abs(p - e50) / p < 0.003

    # LONG: bounce từ EMA + RSI vừa chạm 30-45 rồi tăng + MACD hist đổi âm→dương
    # + big picture: EMA200 và EMA800 dưới giá
    if ((near_ema13 or near_ema50)
            and 30 <= rsi <= 50 and rsi > rsi_prev
            and hist > 0 and hist_prev <= 0
            and (e200 is None or p > e200)):
        return "LONG"

    # SHORT: reject tại EMA + RSI vừa chạm 55-70 rồi giảm + MACD hist đổi dương→âm
    if ((near_ema13 or near_ema50)
            and 50 <= rsi <= 70 and rsi < rsi_prev
            and hist < 0 and hist_prev >= 0
            and (e200 is None or p < e200)):
        return "SHORT"

    return None


# ──── Scheduler ──────────────────────────────────────────────────
# Cooldown: tránh spam cùng 1 signal trong vòng 1 giờ
_last: dict = {"sys1": {"type": None, "time": 0},
               "sys2": {"type": None, "time": 0}}

COOLDOWN = 3600  # giây


async def check_signals(context: ContextTypes.DEFAULT_TYPE):
    """Chạy mỗi 15 phút — kiểm tra cả 2 hệ thống, fire signal nếu có."""
    print("DEBUG: check_signals is running")
    try:
        df = get_ohlcv("BTC", "15m", limit=900, cc_key=CC_API_KEY)
        if df is None:
            return

        ind        = _parse_indicators(df)
        ta_summary = analyze_ta(df)
        now        = datetime.datetime.now().timestamp()

        checks = [
            ("sys1", "📊 Hệ thống 1 — EMA Stack", system1_check(ind)),
            ("sys2", "📊 Hệ thống 2 — RSI Bounce EMA", system2_check(ind)),
        ]

        for sys_key, sys_name, signal_type in checks:
            if signal_type is None:
                print(f"[{sys_key}] No signal | RSI={ind['rsi']:.1f} MACD_hist={ind['macd_hist']:.4f}")
                continue

            last = _last[sys_key]
            if last["type"] == signal_type and now - last["time"] < COOLDOWN:
                print(f"[{sys_key}] {signal_type} cooldown, skip")
                continue

            # Có signal mới → hỏi Sophia giải thích
            emoji  = "🟢" if signal_type == "LONG" else "🔴"
            prompt = (
                f"Dữ liệu BTC 15m:\n{ta_summary['data_for_grok']}\n\n"
                f"{sys_name} phát hiện tín hiệu {signal_type}. "
                f"Giải thích ngắn gọn lý do và điểm cần lưu ý."
            )
            answer = ask_ollama_with_rag(prompt, history=None)

            msg = (
                f"{emoji} *{signal_type} — BTC 15m*\n"
                f"_{sys_name}_\n\n"
                f"💰 Giá: ${ind['price']:,.2f}\n"
                f"📈 RSI: {ind['rsi']:.1f}\n"
                f"📉 MACD hist: {ind['macd_hist']:.4f}\n"
                f"📊 EMA5/13/50: {ind['ema5']:.0f} / {ind['ema13']:.0f} / {ind['ema50']:.0f}\n\n"
                f"🤖 Sophia: {answer}"
            )

            for user_id in ALLOWED_USERS:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    parse_mode="Markdown"
                )

            _last[sys_key] = {"type": signal_type, "time": now}
            print(f"[{sys_key}] Fired {signal_type} signal")

    except Exception as e:
        print(f"Lỗi check_signals: {e}")

# ──── Handlers ─────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context):
        return
    await update.message.reply_text(
        "👋 Xin chào! Tui là Sophia – Crypto AI Bot v2 (Ollama + RAG).\n\n"
        "📊 Giá & Data:\n"
        "/price btc — Xem giá\n"
        "/ta btc 1h — Phân tích TA (5m/15m/1h/4h/1d/1w)\n"
        "/news — Tin tức mới nhất\n"
        "/news btc — Tin về coin cụ thể\n\n"
        "🤖 AI & Học:\n"
        "/ask [câu hỏi] — Hỏi AI crypto/TA\n"
        "/teach [tên] | [mô tả] — Dạy bot pattern mới\n"
        "/patterns — Xem pattern đã dạy\n"
        "/memory — Xem kiến thức bot đã học (RAG)\n\n"
        "🖼️ Gửi ảnh (có hoặc không caption) để phân tích!\n\n"
        "Chat tự nhiên tiếng Việt cũng được!\n"
        "Ví dụ: 'btc 5m nên long hay short?'"
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
        await update.message.reply_text("Dùng: /ta btc 5m  (timeframe: 5m,15m,1h,4h,1d,1w)")
        return

    symbol = COIN_MAP.get(args[0].lower(), args[0].upper())
    tf = args[1].lower() if len(args) > 1 else "1h"
    if tf not in ["5m", "15m", "1h", "4h", "1d", "1w"]:
        await update.message.reply_text("Timeframe không hợp lệ. Chọn: 5m, 15m, 1h, 4h, 1d, 1w")
        return

    await update.message.reply_text(f"⏳ Đang phân tích {symbol} {tf}...")

    limit = 300 if tf in ["5m", "15m"] else 1000
    df = get_ohlcv(symbol, tf, limit=limit, cc_key=CC_API_KEY)
    if df is None:
        await update.message.reply_text("Không lấy được dữ liệu OHLCV.")
        return

    ta_summary = analyze_ta(df)
    user_id = update.effective_user.id
    history = get_recent_messages(user_id, limit=7)

    prompt = (
        f"Dữ liệu kỹ thuật {symbol} timeframe {tf}:\n{ta_summary['data_for_grok']}\n\n"
        "Hãy phân tích ngắn gọn: xu hướng hiện tại? Vùng hỗ trợ/kháng cự quan trọng? Điểm cần chú ý? "
        "Nếu có tín hiệu PVSRA hoặc mẫu hình đặc biệt, hãy đề cập."
    )

    answer = ask_ollama_with_rag(prompt, context_data="", history=history)

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
        
        tf = detect_timeframe_in_text(text_lower)
        # In log để debug (có thể xóa sau)
        print(f"DEBUG: detected timeframe: {tf} from text: {user_text}")
        await update.message.reply_text(f"⏳ Đang phân tích {coin_symbol} {tf}...")
        
        limit = 300 if tf in ["5m", "15m"] else 1000
        df = get_ohlcv(coin_symbol, tf, limit=limit, cc_key=CC_API_KEY)
        if df is not None:
            ta_summary = analyze_ta(df)
            prompt = (
                f"Dữ liệu kỹ thuật {coin_symbol} khung {tf}:\n{ta_summary['data_for_grok']}\n\n"
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
        
        await update.message.reply_text(f"🤖 Sophia:\n\n{answer}")
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

# ──── Main ─────────────────────────────────────────────────────
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

    # Scheduler dùng JobQueue, chạy mỗi 15 phút
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_signals, interval=900, first=10)
        print("✅ Scheduler chạy mỗi 15 phút (BTC 15m)")
    else:
        print("⚠️ JobQueue không khả dụng, scheduler không chạy")

    print("🚀 Sophia – Crypto AI Bot v2 (Ollama + RAG) đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
