import json
import os
from datetime import datetime

DATA_DIR = os.environ.get("DATA_DIR", ".")
KNOWLEDGE_FILE = os.path.join(DATA_DIR, "patterns.json")


def _load() -> list:
    if not os.path.exists(KNOWLEDGE_FILE):
        return []
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(data: list):
    with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_pattern(name: str, description: str):
    """Lưu pattern mới hoặc cập nhật nếu trùng tên"""
    patterns = _load()
    # Cập nhật nếu tên đã tồn tại
    for p in patterns:
        if p["name"].lower() == name.lower():
            p["description"] = description
            p["updated_at"] = datetime.now().isoformat()
            _save(patterns)
            return
    # Thêm mới
    patterns.append({
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
    })
    _save(patterns)


def get_patterns() -> list:
    """Trả về list patterns để đưa vào system prompt Grok"""
    return _load()


def list_patterns() -> str:
    """Trả về string để hiển thị trong Telegram"""
    patterns = _load()
    if not patterns:
        return ""
    lines = [f"📚 Patterns bạn đã dạy bot ({len(patterns)}):\n"]
    for i, p in enumerate(patterns, 1):
        lines.append(f"{i}. *{p['name']}*\n   {p['description']}\n")
    return "\n".join(lines)


def delete_pattern(name: str) -> bool:
    """Xóa pattern theo tên"""
    patterns = _load()
    new_patterns = [p for p in patterns if p["name"].lower() != name.lower()]
    if len(new_patterns) == len(patterns):
        return False
    _save(new_patterns)
    return True
