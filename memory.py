import sqlite3
import datetime

DB_PATH = "chat_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  role TEXT,   -- 'user' hoặc 'assistant'
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

def get_recent_messages(user_id, limit=10):
    """Lấy tin nhắn gần nhất của user (cả user và bot)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    # Trả về theo thứ tự thời gian tăng dần (từ cũ đến mới)
    return list(reversed(rows))
