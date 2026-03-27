import pandas as pd
import requests
import ta

# ──── Hàm gộp nến từ 1 phút thành nến lớn hơn ─────────────────────
def aggregate_ohlcv(df_1min: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """
    Gộp dữ liệu OHLCV từ nến 1 phút thành nến với số phút tùy chọn (5, 15, ...)
    """
    if df_1min is None or df_1min.empty:
        return None
    df_1min = df_1min.copy()
    # Tính nhóm thời gian (floor theo số phút)
    df_1min['group'] = df_1min.index.floor(f'{minutes}T')
    grouped = df_1min.groupby('group')
    df_agg = pd.DataFrame()
    df_agg['open'] = grouped['open'].first()
    df_agg['high'] = grouped['high'].max()
    df_agg['low'] = grouped['low'].min()
    df_agg['close'] = grouped['close'].last()
    df_agg['volume'] = grouped['volume'].sum()
    return df_agg

# ──── Hàm lấy OHLCV (đã sửa để hỗ trợ các khung mới) ─────────────
def get_ohlcv(symbol: str, timeframe: str, limit: int = 200, cc_key: str = None) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV cho symbol với timeframe cụ thể.
    Hỗ trợ: '1h', '4h', '1d', '1w', '5m', '15m'
    """
    # Xác định endpoint và số nến raw cần lấy
    if timeframe == '1h' or timeframe == '4h':
        endpoint = 'histohour'
        raw_limit = limit
    elif timeframe == '1d':
        endpoint = 'histoday'
        raw_limit = limit
    elif timeframe == '1w':
        endpoint = 'histoday'
        raw_limit = limit * 7  # lấy nhiều ngày để gộp thành tuần
    elif timeframe in ['5m', '15m']:
        endpoint = 'histominute'
        minutes = int(timeframe[:-1])
        raw_limit = limit * minutes
    else:
        # Mặc định histohour nếu không nhận diện được
        endpoint = 'histohour'
        raw_limit = limit

    # Gọi API CryptoCompare
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {
        "fsym": symbol,
        "tsym": "USD",
        "limit": raw_limit,
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

        # Nếu timeframe là 5m hoặc 15m, cần gộp nến
        if timeframe in ['5m', '15m']:
            minutes = int(timeframe[:-1])
            df = aggregate_ohlcv(df, minutes)
            # Giới hạn số nến về limit
            if len(df) > limit:
                df = df.iloc[-limit:]

        return df
    except Exception as e:
        print(f"Error fetching OHLCV: {e}")
        return None

# ──── PVSRA (giữ nguyên) ─────────────────────────────────────────
def pvsra_classify(df: pd.DataFrame) -> str:
    """Xác định loại nến PVSRA cho nến cuối cùng."""
    if df is None or len(df) < 11:
        return "unknown"
    last_11 = df.iloc[-11:]
    current = last_11.iloc[-1]
    prev_10 = last_11.iloc[:-1]

    avg_volume = prev_10['volume'].mean()

    def volume_spread(row):
        return (row['high'] - row['low']) * row['volume']

    spreads = prev_10.apply(volume_spread, axis=1)
    highest_spread = spreads.max() if not spreads.empty else 0
    current_spread = volume_spread(current)

    cond_strong = (current['volume'] >= 2 * avg_volume) or (current_spread >= highest_spread)
    cond_medium = (current['volume'] >= 1.5 * avg_volume)

    is_bull = current['close'] > current['open']

    if cond_strong:
        return 'green' if is_bull else 'red'
    elif cond_medium:
        return 'blue' if is_bull else 'violet'
    else:
        return 'regular_up' if is_bull else 'regular_down'

def recent_pvsra(df: pd.DataFrame, n: int = 5) -> list:
    """Trả về danh sách PVSRA của n nến gần nhất (không tính nến cuối)"""
    if df is None or len(df) < n+1:
        return []
    colors = []
    for i in range(-n, 0):
        slice_df = df.iloc[:i] if i != 0 else df
        colors.append(pvsra_classify(slice_df))
    return colors

# ──── Phân tích kỹ thuật chính (không thay đổi) ───────────────────
def analyze_ta(df: pd.DataFrame) -> dict:
    """Tính tất cả chỉ báo + PVSRA, trả về text và data_for_grok"""
    if df is None or df.empty:
        return {"text": "Không có dữ liệu", "data_for_grok": ""}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # Các chỉ báo cũ
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
    macd = ta.trend.MACD(close)
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    macd_hist = macd.macd_diff().iloc[-1]

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]

    ema_periods = [5, 13, 50, 200, 800]
    ema_values = {}
    for p in ema_periods:
        if len(close) >= p:
            ema = ta.trend.EMAIndicator(close, window=p).ema_indicator().iloc[-1]
            ema_values[p] = ema
        else:
            ema_values[p] = None

    vol_sma20 = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else None
    current_volume = volume.iloc[-1]
    vol_ratio = current_volume / vol_sma20 if vol_sma20 else None

    recent_high = high[-20:].max()
    recent_low = low[-20:].min()
    current_price = close.iloc[-1]

    # PVSRA
    pvsra_color = pvsra_classify(df)
    pvsra_recent = recent_pvsra(df, n=5)

    # Xây dựng text hiển thị
    text_lines = [
        f"📊 Phân tích kỹ thuật:",
        f"💰 Giá hiện tại: ${current_price:.2f}",
        f"📈 RSI(14): {rsi:.1f}",
        f"📉 MACD: {macd_line:.2f} / Signal: {macd_signal:.2f} / Hist: {macd_hist:.2f}",
        f"📊 Bollinger Bands: Upper ${bb_upper:.2f} / Mid ${bb_mid:.2f} / Lower ${bb_lower:.2f}",
    ]
    for p in ema_periods:
        if ema_values[p]:
            text_lines.append(f"📈 EMA{p}: ${ema_values[p]:.2f}")
        else:
            text_lines.append(f"📈 EMA{p}: (không đủ dữ liệu)")

    text_lines.append(f"💧 Volume hiện tại: {current_volume:,.0f}")
    if vol_ratio:
        text_lines.append(f"💧 Volume SMA20: {vol_sma20:,.0f} (ratio {vol_ratio:.2f}x)")
    text_lines.append(f"🛡️ Hỗ trợ gần: ${recent_low:.2f} | Kháng cự gần: ${recent_high:.2f}")
    text_lines.append(f"🎨 PVSRA: {pvsra_color.upper()}")
    if pvsra_recent:
        text_lines.append(f"📜 PVSRA gần đây: {', '.join(pvsra_recent)}")
    text = "\n".join(text_lines)

    # Dữ liệu gửi cho AI
    data_for_grok = f"""Current price: {current_price:.2f}
RSI(14): {rsi:.1f}
MACD line: {macd_line:.2f}, Signal: {macd_signal:.2f}, Histogram: {macd_hist:.2f}
Bollinger Bands: Upper {bb_upper:.2f}, Middle {bb_mid:.2f}, Lower {bb_lower:.2f}
EMA5: {ema_values[5] if ema_values[5] else 'N/A'}, EMA13: {ema_values[13] if ema_values[13] else 'N/A'}, EMA50: {ema_values[50] if ema_values[50] else 'N/A'}, EMA200: {ema_values[200] if ema_values[200] else 'N/A'}, EMA800: {ema_values[800] if ema_values[800] else 'N/A'}
Volume: {current_volume:,.0f}, Volume SMA20: {vol_sma20:,.0f} (ratio {vol_ratio:.2f}x)
Recent support: {recent_low:.2f}, resistance: {recent_high:.2f}
PVSRA: {pvsra_color}
Recent PVSRA sequence: {', '.join(pvsra_recent) if pvsra_recent else 'N/A'}"""

    return {"text": text, "data_for_grok": data_for_grok}
