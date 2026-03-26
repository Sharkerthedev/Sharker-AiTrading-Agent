import pandas as pd
import requests
import ta

def get_ohlcv(symbol: str, endpoint: str, limit: int = 200, cc_key: str = None) -> pd.DataFrame:
    """Lấy dữ liệu OHLCV từ CryptoCompare"""
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {
        "fsym": symbol,
        "tsym": "USD",
        "limit": limit,
        "api_key": cc_key
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "Data" not in data or "Data" not in data["Data"]:
            return None
        ohlcv = data["Data"]["Data"]
        df = pd.DataFrame(ohlcv)
        df["time"] = pd.to_datetime(df["time"], unit='s')
        df = df.rename(columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volumefrom": "volume"
        })
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df.set_index("time", inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching OHLCV: {e}")
        return None

def analyze_ta(df: pd.DataFrame) -> dict:
    """Tính toán các chỉ báo kỹ thuật: Volume, EMA combo, RSI, MACD, Bollinger Bands"""
    if df is None or df.empty:
        return {"text": "Không có dữ liệu", "data_for_grok": ""}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # RSI (14)
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]

    # MACD
    macd = ta.trend.MACD(close)
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    macd_hist = macd.macd_diff().iloc[-1]

    # Bollinger Bands (20,2)
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]

    # EMA 5,13,50,200,800
    ema_periods = [5, 13, 50, 200, 800]
    ema_values = {}
    for p in ema_periods:
        if len(close) >= p:
            ema = ta.trend.EMAIndicator(close, window=p).ema_indicator().iloc[-1]
            ema_values[p] = ema
        else:
            ema_values[p] = None

    # Volume SMA 20
    vol_sma20 = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else None
    current_volume = volume.iloc[-1]
    vol_ratio = current_volume / vol_sma20 if vol_sma20 else None

    # Hỗ trợ/kháng cự gần (20 nến)
    recent_high = high[-20:].max()
    recent_low = low[-20:].min()

    current_price = close.iloc[-1]

    # Tạo text hiển thị
    text_lines = [
        f"📊 Phân tích kỹ thuật:",
        f"💰 Giá hiện tại: ${current_price:.2f}",
        f"📈 RSI(14): {rsi:.1f}",
        f"📉 MACD: {macd_line:.2f} / Signal: {macd_signal:.2f} / Hist: {macd_hist:.2f}",
        f"📊 Bollinger Bands: Upper ${bb_upper:.2f} / Mid ${bb_mid:.2f} / Lower ${bb_lower:.2f}",
    ]

    # Thêm các EMA
    for p in ema_periods:
        if ema_values[p]:
            text_lines.append(f"📈 EMA{p}: ${ema_values[p]:.2f}")
        else:
            text_lines.append(f"📈 EMA{p}: (không đủ dữ liệu)")

    # Thêm Volume
    text_lines.append(f"💧 Volume hiện tại: {current_volume:,.0f}")
    if vol_ratio:
        text_lines.append(f"💧 Volume SMA20: {vol_sma20:,.0f} (ratio {vol_ratio:.2f}x)")

    text_lines.append(f"🛡️ Hỗ trợ gần: ${recent_low:.2f} | Kháng cự gần: ${recent_high:.2f}")
    text = "\n".join(text_lines)

    # Dữ liệu gửi cho Gemini
    data_for_grok = f"""Current price: {current_price:.2f}
RSI(14): {rsi:.1f}
MACD line: {macd_line:.2f}, Signal: {macd_signal:.2f}, Histogram: {macd_hist:.2f}
Bollinger Bands: Upper {bb_upper:.2f}, Middle {bb_mid:.2f}, Lower {bb_lower:.2f}
EMA5: {ema_values[5] if ema_values[5] else 'N/A'}, EMA13: {ema_values[13] if ema_values[13] else 'N/A'}, EMA50: {ema_values[50] if ema_values[50] else 'N/A'}, EMA200: {ema_values[200] if ema_values[200] else 'N/A'}, EMA800: {ema_values[800] if ema_values[800] else 'N/A'}
Volume: {current_volume:,.0f}, Volume SMA20: {vol_sma20:,.0f} (ratio {vol_ratio:.2f}x)
Recent support: {recent_low:.2f}, resistance: {recent_high:.2f}"""

    return {"text": text, "data_for_grok": data_for_grok}
