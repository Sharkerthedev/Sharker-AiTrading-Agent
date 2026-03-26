# 🤖 Crypto AI Bot v2 (Ollama + RAG)

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://core.telegram.org/bots)
[![Gemini](https://img.shields.io/badge/Gemini-AI-orange.svg)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Crypto AI Bot v2** là một trợ lý giao dịch tiền điện tử thông minh trên Telegram, sử dụng AI Gemini của Google kết hợp với bộ nhớ dài hạn RAG (Retrieval-Augmented Generation). Bot có khả năng phân tích kỹ thuật (TA) chuyên sâu, học hỏi từ người dùng và nhớ kiến thức lâu dài.

---

## ✨ Tính năng nổi bật

### 📊 Phân tích kỹ thuật (TA)
- **Chỉ báo đầy đủ:** EMA5, EMA13, EMA50, EMA200, EMA800, RSI(14), MACD, Bollinger Bands, Volume SMA20
- **Hỗ trợ/kháng cự:** Tự động xác định vùng hỗ trợ và kháng cự gần nhất
- **Nhiều khung thời gian:** Hỗ trợ 1h, 4h, 1d, 1w
- **Dữ liệu realtime:** Lấy từ CryptoCompare (tổng hợp 300+ sàn giao dịch)

### 🧠 AI Ollama tích hợp
- **Phân tích thông minh:** Gemini 2.5 Flash đọc và giải thích các chỉ báo TA
- **Nhận diện ảnh:** Phân tích chart qua ảnh chụp màn hình (Gemini Vision)
- **Trả lời tự nhiên:** Hiểu tiếng Việt, trả lời như trader kinh nghiệm

### 📚 Bộ nhớ dài hạn (RAG)
- **Học từ kinh nghiệm:** Tự động lưu các phân tích TA vào vector database
- **Nhớ qua nhiều ngày:** Bot nhớ những nhận định từ tuần trước
- **Tìm kiếm thông minh:** Khi hỏi, bot tìm kiếm kiến thức liên quan nhất
- **Càng dùng càng thông minh:** Tích lũy kiến thức theo thời gian

### 🎓 Học từ người dùng
- **Lệnh `/teach`:** Dạy bot các mẫu hình, quy tắc, chiến lược mới
- **Lưu vào RAG:** Kiến thức được lưu trữ dài hạn và tự động áp dụng
- **Xem kiến thức:** Lệnh `/memory` để xem bot đã học được gì

### 💾 Bộ nhớ ngắn hạn
- **Nhớ cuộc hội thoại:** Lưu 10 tin nhắn gần nhất để theo kịp ngữ cảnh
- **SQLite:** Lưu trữ nhẹ, không cần cài database riêng

---

## 📋 Các lệnh hỗ trợ

| Lệnh | Mô tả | Ví dụ |
|------|-------|-------|
| `/start` | Khởi động và hướng dẫn sử dụng | `/start` |
| `/price` | Xem giá hiện tại của coin | `/price btc` |
| `/ta` | Phân tích kỹ thuật chi tiết | `/ta btc 1h` |
| `/news` | Tin tức mới nhất về crypto | `/news` hoặc `/news btc` |
| `/ask` | Hỏi trực tiếp Gemini | `/ask RSI 30 có phải oversold?` |
| `/teach` | Dạy bot pattern/kiến thức mới | `/teach Bullish Engulfing \| Nến xanh bao trùm nến đỏ` |
| `/patterns` | Xem các pattern đã dạy | `/patterns` |
| `/memory` | Xem kiến thức bot đã học (RAG) | `/memory` |

---

## 🗣️ Chat tự nhiên

Bot hiểu ngôn ngữ tự nhiên tiếng Việt:

| Bạn hỏi | Bot hiểu |
|---------|----------|
| *"btc giá bao nhiêu"* | Trả về giá BTC hiện tại |
| *"phân tích sol"* | Phân tích TA cho SOL |
| *"btc hôm nay nên long hay short?"* | Phân tích xu hướng và đưa ra nhận định |
| *"có tin gì về crypto không"* | Lấy tin tức mới nhất |
| *"eth mấy đô"* | Trả về giá ETH |

---

## 🖼️ Phân tích ảnh

Gửi ảnh chart (JPEG/PNG) kèm caption hoặc không, bot sẽ:
1. Tải ảnh về và chuyển sang base64
2. Gửi cho Gemini Vision phân tích
3. Trả về nhận định về chỉ báo, xu hướng

---

## 🔧 Cài đặt

### Yêu cầu hệ thống
- Python 3.9 trở lên
- Telegram Bot Token (từ [@BotFather](https://t.me/BotFather))
- Gemini API Key (từ [Google AI Studio](https://aistudio.google.com/))
- CryptoCompare API Key (đăng ký miễn phí tại [CryptoCompare](https://www.cryptocompare.com/))

### 1. Clone repository
```bash
git clone https://github.com/yourusername/crypto-ai-bot.git
cd crypto-ai-bot
