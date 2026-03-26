import chromadb
from chromadb.utils import embedding_functions
import datetime

CHROMA_PATH = "./chroma_data"
EMBED_MODEL = "all-MiniLM-L6-v2"

class RagMemory:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        self.collection = self.client.get_or_create_collection(
            name="trading_knowledge",
            embedding_function=self.embedding_func
        )

    def _split_text(self, text: str, chunk_size: int = 500, overlap: int = 50):
        """Đơn giản hóa split text mà không cần langchain."""
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                # cố gắng cắt ở khoảng trắng
                last_space = text.rfind(' ', start, end)
                if last_space != -1:
                    end = last_space
            chunks.append(text[start:end].strip())
            start = end - overlap
            if start < 0:
                start = 0
        return chunks

    def add_knowledge(self, content: str, metadata: dict):
        """Thêm kiến thức vào bộ nhớ dài hạn"""
        chunks = self._split_text(content, chunk_size=500, overlap=50)
        for i, chunk in enumerate(chunks):
            doc_id = f"{metadata.get('type', 'knowledge')}_{datetime.datetime.now().timestamp()}_{i}"
            self.collection.add(
                documents=[chunk],
                metadatas=[metadata],
                ids=[doc_id]
            )

    def search_knowledge(self, query: str, n_results: int = 5) -> list:
        """Tìm kiếm kiến thức liên quan đến câu hỏi"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        if results['documents']:
            return results['documents'][0]
        return []

    def save_analysis(self, symbol: str, analysis: str, indicators: dict):
        """Lưu phân tích TA vào bộ nhớ"""
        content = f"Phân tích {symbol}: {analysis}\nCác chỉ báo: {indicators}"
        metadata = {
            "type": "ta_analysis",
            "symbol": symbol,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.add_knowledge(content, metadata)
