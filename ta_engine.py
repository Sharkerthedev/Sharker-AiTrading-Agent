import requests
import pandas as pd


def get_ohlcv(symbol: str, endpoint: str, limit: int = 200, cc_key: str = "") -> pd.DataFrame | None:
    """Lấy dữ liệu OHLCV từ CryptoCompare"""
    try:
        url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
        r = requests.get(url, params={
            "fsym": symbol,
            "tsym": "USD",
            "limit": limit,
            "api_key": cc_key,
        }, timeout=15)
        data = r.json().get("Data", {}).get("Data", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df = df[["time", "open", "high", "low", "close", "volumeto"]].copy()
        df.rename(columns={"volumeto": "volume"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df[df["close"] > 0].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Lỗi get_ohlcv: {e}")
        return None


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bb(series: pd.Series, period: int = 20, std: float = 2.0):
    ma = series.rolling(period).mean()
    std_dev = series.rolling(period).std()
    upper = ma + std * std_dev
    lower = ma - std * std_dev
    return upper, ma, lower


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def analyze_ta(df: pd.DataFrame) -> dict:
    """Tính toàn bộ indicators và trả về text + data cho Grok"""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # RSI
    rsi = calc_rsi(close, 14)
    rsi_val = rsi.iloc[-1]

    # MACD
    macd_line, signal_line, histogram = calc_macd(close)
    macd_val = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]

    # Bollinger Bands
    bb_upper, bb_mid, bb_lower = calc_bb(close, 20)
    bb_upper_val = bb_upper.iloc[-1]
    bb_lower_val = bb_lower.iloc[-1]
    bb_mid_val = bb_mid.iloc[-1]
    price_now = close.iloc[-1]

    # EMA
    ema20 = calc_ema(close, 20).iloc[-1]
    ema50 = calc_ema(close, 50).iloc[-1]
    ema200 = calc_ema(close, 200).iloc[-1]

    # Volume trung bình
    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_now = volume.iloc[-1]
    vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1

    # Support / Resistance đơn giản (low/high 20 nến gần nhất)
    support = low.tail(20).min()
    resistance = high.tail(20).max()

    # Tín hiệu
    signals = []
    if rsi_val < 30:
        signals.append("RSI Oversold (<30) — có thể đảo chiều tăng")
    elif rsi_val > 70:
        signals.append("RSI Overbought (>70) — cẩn thận đảo chiều giảm")
    else:
        signals.append(f"RSI trung tính ({rsi_val:.1f})")

    if macd_val > signal_val and hist_val > 0:
        signals.append("MACD bullish — đà tăng")
    elif macd_val < signal_val and hist_val < 0:
        signals.append("MACD bearish — đà giảm")
    else:
        signals.append("MACD đang cross — chú ý")

    if price_now > ema20 > ema50:
        signals.append("Giá trên EMA20 > EMA50 — xu hướng tăng ngắn hạn")
    elif price_now < ema20 < ema50:
        signals.append("Giá dưới EMA20 < EMA50 — xu hướng giảm ngắn hạn")

    if vol_ratio > 1.5:
        signals.append(f"Volume tăng đột biến ({vol_ratio:.1f}x trung bình) — chú ý breakout")

    bb_position = (price_now - bb_lower_val) / (bb_upper_val - bb_lower_val) * 100 if (bb_upper_val - bb_lower_val) > 0 else 50

    # Format text gửi Telegram
    text = (
        f"📊 Phân tích kỹ thuật\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Giá hiện tại: ${price_now:,.4f}\n\n"
        f"📈 Indicators:\n"
        f"RSI(14): {rsi_val:.1f}\n"
        f"MACD: {macd_val:.4f} | Signal: {signal_val:.4f}\n"
        f"BB Upper: ${bb_upper_val:,.2f}\n"
        f"BB Mid:   ${bb_mid_val:,.2f}\n"
        f"BB Lower: ${bb_lower_val:,.2f}\n"
        f"BB Position: {bb_position:.0f}%\n\n"
        f"📉 EMA:\n"
        f"EMA20: ${ema20:,.2f}\n"
        f"EMA50: ${ema50:,.2f}\n"
        f"EMA200: ${ema200:,.2f}\n\n"
        f"🏔 S/R (20 nến gần nhất):\n"
        f"Resistance: ${resistance:,.2f}\n"
        f"Support: ${support:,.2f}\n\n"
        f"⚡ Tín hiệu:\n" +
        "\n".join(f"• {s}" for s in signals)
    )

    # Data ngắn gọn cho Grok
    data_for_grok = (
        f"Price: ${price_now:,.4f} | RSI: {rsi_val:.1f} | "
        f"MACD: {macd_val:.4f} vs Signal: {signal_val:.4f} (hist: {hist_val:.4f}) | "
        f"BB: {bb_lower_val:.2f}/{bb_mid_val:.2f}/{bb_upper_val:.2f} (pos: {bb_position:.0f}%) | "
        f"EMA20: {ema20:.2f} EMA50: {ema50:.2f} EMA200: {ema200:.2f} | "
        f"Support: {support:.2f} Resistance: {resistance:.2f} | "
        f"Volume: {vol_ratio:.1f}x avg"
    )

    return {"text": text, "data_for_grok": data_for_grok}
