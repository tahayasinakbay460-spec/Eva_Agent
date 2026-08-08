"""
memory.py - Uzun Süreli Hafıza Sistemi (ChromaDB + RAG)
=========================================================

📚 Öğretici Not — RAG Nedir?
    RAG = Retrieval-Augmented Generation (Erişimle Güçlendirilmiş Üretim)

    Normal LLM: Kullanıcı sorar → Model cevaplar (geçmişi bilmez)

    RAG sistemi:
    1. KAYDET: Her konuşmayı metinden vektöre (sayı dizisi) çevir ve sakla
    2. SORGULA: Yeni mesaj gelince "buna benzer geçmiş var mı?" diye bak
    3. ZENGİNLEŞTİR: Bulunan geçmiş + yeni mesaj → LLM'e gönder
    4. YANIT: LLM artık geçmişi "bilerek" cevap verir

    Vektör = Bir cümlenin matematiksel temsili.
    "Bugün çok yoruldum" ve "Bugün çok sıkıntılı bir gün geçirdim"
    vektörde birbirine yakın olur → ChromaDB ikisini "benzer" bulur.
"""

import uuid
import chromadb
from chromadb.utils import embedding_functions
from app.config import Config


class EvaMemory:
    """
    Eva'nın uzun süreli hafızasını yöneten sınıf.
    ChromaDB'yi kullanarak konuşmaları vektör olarak saklar
    ve alakalı geçmişi sorgular.
    """

    def __init__(self):
        """
        ChromaDB'yi başlat.

        📚 persist_directory: ChromaDB verilerini diske kaydeder.
            Uygulama kapanıp açılsa bile hafıza kaybolmaz.
        """
        self.client = chromadb.PersistentClient(
            path=Config.CHROMA_DB_PATH
        )

        # 📚 DefaultEmbeddingFunction: yerel, ücretsiz küçük bir model.
        # API anahtarı gerekmez, ilk çalıştırmada otomatik indirilir.
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name="eva_conversations",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )

        print(f"ChromaDB baslatildi. Mevcut hafiza: {self.collection.count()} kayit")

    def save_conversation(self, user_id: str, user_message: str, eva_response: str) -> None:
        """
        Bir konuşma turunu (kullanıcı sorusu + Eva cevabı) hafızaya kaydet.
        """
        combined_text = f"Kullanıcı: {user_message}\nEva: {eva_response}"
        doc_id = str(uuid.uuid4())

        self.collection.add(
            documents=[combined_text],
            metadatas=[{
                "user_id": user_id,
                "user_message": user_message,
                "eva_response": eva_response[:500],
            }],
            ids=[doc_id]
        )

    def retrieve_relevant_memories(self, user_id: str, query: str, n_results: int = 4 ) -> str:
        """
        Yeni bir mesajla alakalı geçmiş konuşmaları bul.
        """
        total_count = self.collection.count()
        if total_count == 0:
            return ""

        actual_n = min(n_results, total_count)

        results = self.collection.query(
            query_texts=[query],
            n_results=actual_n,
            where={"user_id": user_id}
        )

        if not results["documents"] or not results["documents"][0]:
            return ""

        memories = []
        for i, doc in enumerate(results["documents"][0]): #i yani ilk eleman her zaman sıra numarası digeri eleman da her zaman ilgili elemandır 
            memories.append(f"[Geçmiş Konuşma {i+1}]:\n{doc}")

        return "\n\n".join(memories)

    def get_memory_count(self, user_id: str) -> int:
        results = self.collection.get(where={"user_id": user_id})
        return len(results["ids"])


# Singleton pattern
_memory_instance = None

def get_memory() -> EvaMemory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = EvaMemory()
    return _memory_instance
