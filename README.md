Crypto AI Bot v2 (Gemini + RAG)
📖 Giới thiệu
Crypto AI Bot v2 là một trợ lý giao dịch tiền điện tử thông minh tích hợp trong Telegram, sử dụng AI Gemini của Google kết hợp với bộ nhớ dài hạn RAG (Retrieval-Augmented Generation). Bot có khả năng phân tích kỹ thuật (TA) chuyên sâu, học hỏi từ người dùng và nhớ kiến thức lâu dài.

🚀 Tính năng chính
📊 Phân tích kỹ thuật (TA)
Chỉ báo đầy đủ: EMA (5,13,50,200,800), RSI(14), MACD, Bollinger Bands, Volume SMA20

Hỗ trợ/kháng cự: Tự động xác định vùng hỗ trợ và kháng cự gần nhất

Nhiều khung thời gian: Hỗ trợ 1h, 4h, 1d, 1w

Dữ liệu realtime: Lấy từ CryptoCompare (tổng hợp 300+ sàn)

🧠 AI Gemini tích hợp
Phân tích thông minh: Gemini 2.5 Flash đọc và giải thích các chỉ báo TA

Nhận diện ảnh: Phân tích chart qua ảnh chụp màn hình (Gemini Vision)

Trả lời tự nhiên: Hiểu tiếng Việt, trả lời như trader kinh nghiệm

📚 Bộ nhớ dài hạn (RAG)
Học từ kinh nghiệm: Tự động lưu các phân tích TA vào vector database

Nhớ qua nhiều ngày: Bot nhớ những nhận định từ tuần trước

Tìm kiếm thông minh: Khi hỏi, bot tìm kiếm kiến thức liên quan nhất

Càng dùng càng thông minh: Tích lũy kiến thức theo thời gian

🎓 Học từ người dùng
Lệnh /teach: Dạy bot các mẫu hình, quy tắc, chiến lược mới

Lưu vào RAG: Kiến thức được lưu trữ dài hạn và tự động áp dụng

Xem kiến thức: Lệnh /memory để xem bot đã học được gì

💾 Bộ nhớ ngắn hạn
Nhớ cuộc hội thoại: Lưu 10 tin nhắn gần nhất để theo kịp ngữ cảnh

SQLite: Lưu trữ nhẹ, không cần cài database riêng

📋 Các lệnh hỗ trợ
Lệnh	Mô tả	Ví dụ
/start	Khởi động và hướng dẫn sử dụng	/start
/price	Xem giá hiện tại của coin	/price btc
/ta	Phân tích kỹ thuật chi tiết	/ta btc 1h
/news	Tin tức mới nhất về crypto	/news hoặc /news btc
/ask	Hỏi trực tiếp Gemini	/ask RSI 30 có phải oversold?
/teach	Dạy bot pattern/kiến thức mới	/teach Bullish Engulfing | Nến xanh bao trùm nến đỏ
/patterns	Xem các pattern đã dạy	/patterns
/memory	Xem kiến thức bot đã học (RAG)	/memory
🗣️ Chat tự nhiên
Bot hiểu ngôn ngữ tự nhiên tiếng Việt:

Hỏi giá: "btc giá bao nhiêu", "eth mấy đô"

Hỏi phân tích: "phân tích sol", "chart btc hôm nay thế nào"

Hỏi quyết định: "btc hôm nay nên long hay short?", "có nên mua eth không?"

Hỏi tin tức: "có tin gì về crypto không", "news btc"

🖼️ Phân tích ảnh
Gửi ảnh chart (JPEG/PNG) kèm caption hoặc không, bot sẽ:

Tải ảnh về và chuyển sang base64

Gửi cho Gemini Vision phân tích

Trả về nhận định về chỉ báo, xu hướng

🔧 Cài đặt
Yêu cầu
Python 3.9+

Telegram Bot Token (từ @BotFather)

Gemini API Key (từ Google AI Studio)

CryptoCompare API Key (đăng ký miễn phí)

Cài đặt thư viện
bash
pip install python-telegram-bot pandas requests ta chromadb sentence-transformers langchain-text-splitters
Biến môi trường
bash
export TELEGRAM_TOKEN="your_bot_token"
export GEMINI_API_KEY="your_gemini_key"
export CRYPTOCOMPARE_KEY="your_cryptocompare_key"
export OWNER_ID="your_telegram_user_id"
Chạy bot
bash
python bot.py
🧠 Kiến trúc
text
┌─────────────────────────────────────────────────────────┐
│                     Telegram Bot                        │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Gemini AI  │  │  TA Engine   │  │  Knowledge   │  │
│  │  (text+vision│  │ (EMA,RSI,...)│  │  (patterns)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐                    │
│  │   Short-term │  │   Long-term  │                    │
│  │   Memory     │  │   Memory     │                    │
│  │   (SQLite)   │  │   (RAG)      │                    │
│  │  10 messages │  │  ChromaDB    │                    │
│  └──────────────┘  └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
📁 Cấu trúc file
text
bot/
├── bot.py              # File chính
├── ta_engine.py        # Tính toán chỉ báo TA
├── knowledge.py        # Quản lý pattern (JSON)
├── rag_memory.py       # Bộ nhớ dài hạn (ChromaDB)
├── chat_memory.db      # SQLite - short-term memory
├── chroma_data/        # Vector database - long-term memory
└── patterns.json       # Lưu pattern đã dạy
🔐 Bảo mật
Bot chỉ phản hồi chủ nhân (kiểm tra Telegram User ID)

API keys được lưu qua biến môi trường

Private key không được lưu trong code

Dữ liệu local, không gửi ra ngoài

🚧 Giới hạn và lưu ý
RAG cần thời gian: Bot càng dùng lâu càng thông minh

Chi phí Gemini: Với Tier 1, chi phí ~$1-3/tháng tùy tần suất

Dữ liệu CryptoCompare: Free tier 100k requests/tháng

Không phải lời khuyên tài chính: Bot chỉ phân tích kỹ thuật, quyết định giao dịch là của bạn

🛠️ Phát triển tiếp theo
Thêm Fibonacci retracement tự động

Tích hợp X (Twitter) scraping

Paper trading (giao dịch giả lập)

Cảnh báo tự động khi có tín hiệu

Hỗ trợ nhiều người dùng

📝 Giấy phép
MIT License

🙏 Cảm ơn
Google Gemini API

python-telegram-bot

CryptoCompare

ChromaDB

Bot của bạn – Trợ lý giao dịch thông minh, học hỏi và nhớ lâu! 🚀
