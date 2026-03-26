# Crypto AI Bot v2 — Telegram

Bot Telegram crypto cá nhân với TA engine + hệ thống dạy pattern.

## Stack
- **AI**: Grok 4.1 Fast (xAI)
- **Giá & OHLCV**: CryptoCompare API (free)
- **News**: CryptoCompare News API (free)
- **TA**: Tính nội bộ bằng pandas (RSI, MACD, BB, EMA) — không cần thư viện ngoài
- **Knowledge base**: JSON local (lưu pattern bạn dạy)
- **Deploy**: Railway

## Các lệnh bot

| Lệnh | Mô tả |
|---|---|
| `/start` | Xem hướng dẫn |
| `/price btc` | Giá + volume 24h |
| `/ta btc 1h` | Phân tích TA đầy đủ (RSI, MACD, BB, EMA) |
| `/ta eth 4h` | TA timeframe 4h |
| `/ta sol 1d` | TA timeframe ngày |
| `/news` | 5 tin crypto mới nhất |
| `/news btc` | Tin về Bitcoin |
| `/ask [câu hỏi]` | Hỏi Grok tự do |
| `/teach [Tên] \| [Mô tả]` | Dạy bot pattern mới |
| `/patterns` | Xem danh sách pattern đã dạy |

## Cách dạy bot TA

```
/teach Bullish Engulfing | Nến xanh thân to bao trùm hoàn toàn nến đỏ trước đó, 
xuất hiện ở vùng support mạnh + volume tăng = tín hiệu mua mạnh

/teach RSI Divergence | Giá tạo đáy mới nhưng RSI tạo đáy cao hơn = 
bullish divergence, khả năng đảo chiều tăng cao

/teach EMA Cross | EMA20 cắt lên EMA50 từ dưới = golden cross, 
tín hiệu xu hướng tăng trung hạn bắt đầu
```

Bot sẽ áp dụng tất cả pattern bạn dạy khi phân tích `/ta`.

## Deploy Railway

### Bước 1 — Push lên GitHub
Upload toàn bộ folder lên repo GitHub mới.

### Bước 2 — Tạo project Railway
1. Vào [railway.app](https://railway.app)
2. **New Project** → **Deploy from GitHub repo**
3. Chọn repo vừa tạo

### Bước 3 — Environment Variables
Vào tab **Variables**, thêm 3 biến:

| Variable | Giá trị |
|---|---|
| `TELEGRAM_TOKEN` | Token từ @BotFather |
| `GROK_API_KEY` | Key từ console.x.ai |
| `CRYPTOCOMPARE_KEY` | Key từ min-api.cryptocompare.com |

### Bước 4 — Deploy
Railway tự build. Xem log ở tab **Deployments**.

## Cấu trúc files

```
crypto-bot-v2/
├── bot.py          ← Logic chính + handlers Telegram
├── ta_engine.py    ← Tính RSI, MACD, BB, EMA từ OHLCV
├── knowledge.py    ← Lưu/đọc pattern TA bạn dạy
├── requirements.txt
├── railway.toml
├── nixpacks.toml
└── README.md
```

## Roadmap tiếp theo
- [ ] Alert tự động khi RSI oversold/overbought
- [ ] Gửi chart ảnh qua Telegram
- [ ] Lưu patterns lên Supabase (để không mất khi redeploy)
- [ ] Backtesting đơn giản cho pattern
