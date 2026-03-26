import chromadb
from chromadb.utils import embedding_functions
from langchain.text_splitter import RecursiveCharacterTextSplitter
import datetime

# Khởi tạo ChromaDB
CHROMA_PATH = "./chroma_data"
EMBED_MODEL = "all-MiniLM-L6-v2"

class RagMemory:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        # Tạo collection lưu kiến thức trading
        self.collection = self.client.get_or_create_collection(
            name="trading_knowledge",
            embedding_function=self.embedding_func
        )
    
    def add_knowledge(self, content: str, metadata: dict):
        """Thêm kiến thức vào bộ nhớ dài hạn"""
        # Tạo chunks cho nội dung dài
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        chunks = text_splitter.split_text(content)
        
        # Thêm từng chunk vào vector DB
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
