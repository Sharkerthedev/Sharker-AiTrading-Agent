import pandas as pd
import requests
import ta

# ========== HÀM LẤY DỮ LIỆU (CryptoCompare hoặc có thể mở rộng) ==========
def get_ohlcv(symbol: str, endpoint: str, limit: int = 200, cc_key: str = None) -> pd.DataFrame:
    """Lấy OHLCV từ CryptoCompare (giữ nguyên như cũ)"""
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


# ========== HÀM PVSRA ==========
def pvsra_classify(df: pd.DataFrame) -> str:
    """
    Xác định loại nến PVSRA cho nến cuối cùng.
    Trả về: 'green', 'red', 'blue', 'violet', 'regular_up', 'regular_down'
    """
    if df is None or len(df) < 11:
        return "unknown"   # không đủ dữ liệu để tính

    # Lấy 11 nến gần nhất (nến hiện tại + 10 nến trước)
    last_11 = df.iloc[-11:]
    current = last_11.iloc[-1]
    prev_10 = last_11.iloc[:-1]

    # Tính khối lượng trung bình 10 nến trước
    avg_volume = prev_10['volume'].mean()
    if avg_volume == 0:
        avg_volume = 1  # tránh chia 0

    # Hàm tính volume spread
    def volume_spread(row):
        return (row['high'] - row['low']) * row['volume']

    spreads = prev_10.apply(volume_spread, axis=1)
    highest_spread = spreads.max()
    current_spread = volume_spread(current)

    # Điều kiện vector mạnh (200%)
    cond_strong = (current['volume'] >= 2 * avg_volume) or (current_spread >= highest_spread)
    # Điều kiện vector trung bình (150%)
    cond_medium = (current['volume'] >= 1.5 * avg_volume)

    # Xác định xu hướng nến
    is_bull = current['close'] > current['open']

    if cond_strong:
        return 'green' if is_bull else 'red'
    elif cond_medium:
        return 'blue' if is_bull else 'violet'
    else:
        return 'regular_up' if is_bull else 'regular_down'


def recent_pvsra(df: pd.DataFrame, n: int = 5) -> list:
    """Trả về danh sách PVSRA của n nến cuối cùng (không bao gồm nến hiện tại)"""
    if df is None or len(df) < n+1:
        return []
    colors = []
    for i in range(1, n+1):
        slice_df = df.iloc[: -i] if i < len(df) else df
        colors.append(pvsra_classify(slice_df))
    return colors


# ========== HÀM PHÂN TÍCH TA (giữ nguyên cũ + thêm PVSRA) ==========
def analyze_ta(df: pd.DataFrame) -> dict:
    """Tính toán các chỉ báo kỹ thuật: Volume, EMA combo, RSI, MACD, Bollinger, PVSRA"""
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

    # Volume SMA20
    vol_sma20 = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else None
    current_volume = volume.iloc[-1]
    vol_ratio = current_volume / vol_sma20 if vol_sma20 else None

    # Hỗ trợ/kháng cự gần (20 nến)
    recent_high = high[-20:].max()
    recent_low = low[-20:].min()

    current_price = close.iloc[-1]

    # --- PVSRA ---
    pvsra_color = pvsra_classify(df)
    recent_pvsra_list = recent_pvsra(df, n=5)
    recent_pvsra_str = ", ".join(recent_pvsra_list) if recent_pvsra_list else ""

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

    # Thêm PVSRA
    text_lines.append(f"📊 PVSRA: {pvsra_color.upper()}")
    if recent_pvsra_str:
        text_lines.append(f"📊 PVSRA gần đây: {recent_pvsra_str}")

    text = "\n".join(text_lines)

    # Dữ liệu gửi cho AI (giữ cấu trúc cũ)
    data_for_grok = f"""Current price: {current_price:.2f}
RSI(14): {rsi:.1f}
MACD line: {macd_line:.2f}, Signal: {macd_signal:.2f}, Histogram: {macd_hist:.2f}
Bollinger Bands: Upper {bb_upper:.2f}, Middle {bb_mid:.2f}, Lower {bb_lower:.2f}
EMA5: {ema_values[5] if ema_values[5] else 'N/A'}, EMA13: {ema_values[13] if ema_values[13] else 'N/A'}, EMA50: {ema_values[50] if ema_values[50] else 'N/A'}, EMA200: {ema_values[200] if ema_values[200] else 'N/A'}, EMA800: {ema_values[800] if ema_values[800] else 'N/A'}
Volume: {current_volume:,.0f}, Volume SMA20: {vol_sma20:,.0f} (ratio {vol_ratio:.2f}x)
Recent support: {recent_low:.2f}, resistance: {recent_high:.2f}
PVSRA: {pvsra_color.upper()}
Recent PVSRA: {recent_pvsra_str}"""

    return {"text": text, "data_for_grok": data_for_grok}
