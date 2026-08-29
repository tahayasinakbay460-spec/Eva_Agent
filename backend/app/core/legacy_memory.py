"""
core/legacy_memory.py — Ata Anı Hafıza Yöneticisi (Faz 8)
===========================================================
ChromaDB kullanarak ataların anılarını vektör olarak saklar ve sorgular.

📚 Öğretici Not — Bu Dosya Ne Yapar?
    Mevcut EvaMemory sistemi Eva'nın kendi sohbet geçmişi içindir.
    Bu dosya ise her ata için AYRI bir vektör koleksiyonu oluşturur.
    
    Böylece "Dedem hakkında ne biliyorsun?" diye sorulduğunda,
    sadece o dedeye ait anılar aranır — Eva'nın genel hafızası karışmaz.

    Her ata için koleksiyon adı: "legacy_ancestor_{id}"
    Örn: legacy_ancestor_5 → Ancestor ID=5 olan kişinin anıları
"""

import uuid
import chromadb
from chromadb.utils import embedding_functions
from app.config import Config


class LegacyMemoryManager:
    """
    Ata anılarını ChromaDB'de yöneten sınıf.
    
    📚 Mevcut EvaMemory pattern'ini taklit eder ama
        her ata için izole bir koleksiyon kullanır.
    """

    def __init__(self):
        """
        ChromaDB istemcisini başlat.
        
        📚 Aynı persist_directory'yi kullanıyoruz (./chroma_db).
            Ama koleksiyon isimleri farklı olduğu için
            Eva'nın kendi hafızasıyla karışmaz.
        """
        # Mevcut ChromaDB dizinini kullan (aynı veritabanı, farklı koleksiyonlar)
        self.client = chromadb.PersistentClient(
            path=Config.CHROMA_DB_PATH
        )

        # Yerel embedding fonksiyonu — API anahtarı gerektirmez, ücretsiz
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        print("[ATA] Ata Teknolojisi Hafiza Yoneticisi baslatildi.")

    def _get_collection(self, ancestor_id: int):
        """
        Belirli bir ata için ChromaDB koleksiyonunu al veya oluştur.
        
        📚 Her ata kendi koleksiyonuna sahip:
            legacy_ancestor_1, legacy_ancestor_2, ...
            Bu sayede anılar birbirine karışmaz.
        
        Args:
            ancestor_id: Atanın veritabanı ID'si
            
        Returns:
            ChromaDB Collection nesnesi
        """
        collection_name = f"legacy_ancestor_{ancestor_id}"
        return self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            # cosine = metin benzerliği için en iyi metrik
            metadata={"hnsw:space": "cosine"}
        )

    def save_memory(self, ancestor_id: int, content: str, title: str = None) -> str:
        """
        Bir anıyı ChromaDB'ye vektör olarak kaydet.
        
        📚 Nasıl çalışır:
            1. Metin alınır (anı içeriği)
            2. Embedding fonksiyonu metni vektöre çevirir (sayı dizisi)
            3. ChromaDB bu vektörü saklar
            4. Sonra sorgulama yapılınca benzer metinler bulunabilir
        
        Args:
            ancestor_id: Hangi atanın anısı
            content: Anının tam metni
            title: Anının başlığı (opsiyonel, metadata olarak saklanır)
            
        Returns:
            ChromaDB'deki belge ID'si (UUID formatında)
        """
        collection = self._get_collection(ancestor_id)
        
        # Her anı için benzersiz bir ID oluştur
        doc_id = str(uuid.uuid4())
        
        # Başlık varsa metne ekle (arama kalitesini artırır)
        full_text = content
        if title:
            full_text = f"[{title}]\n{content}"
        
        # ChromaDB'ye kaydet
        collection.add(
            documents=[full_text],
            metadatas=[{
                "ancestor_id": str(ancestor_id),
                "title": title or "Başlıksız Anı",
            }],
            ids=[doc_id]
        )
        
        print(f"[ATA] Ani kaydedildi -> Ancestor #{ancestor_id} | ID: {doc_id[:8]}...")
        return doc_id

    def save_chat_turn(
        self,
        ancestor_id: int,
        user_message: str,
        ancestor_response: str,
        ancestor_name: str = None,
    ) -> str:
        """
        Karakter sohbetinin bir turunu Chroma'ya kaydet.

        Yüklenen anılardan ayrı durur ama aynı koleksiyonda aranır —
        persona sonraki konuşmalarda bu sohbeti de hatırlar.
        """
        collection = self._get_collection(ancestor_id)
        name = ancestor_name or "Karakter"
        combined_text = f"Kullanıcı: {user_message}\n{name}: {ancestor_response}"
        doc_id = str(uuid.uuid4())

        collection.add(
            documents=[combined_text],
            metadatas=[{
                "ancestor_id": str(ancestor_id),
                "title": "Sohbet",
                "type": "chat",
            }],
            ids=[doc_id]
        )
        print(f"[ATA] Sohbet turu kaydedildi -> Ancestor #{ancestor_id} | ID: {doc_id[:8]}...")
        return doc_id

    def retrieve_context(self, ancestor_id: int, query: str, n_results: int = 5) -> str:
        """
        Bir soruya en alakalı anıları getir (RAG sorgulama).
        
        📚 Nasıl çalışır:
            1. Kullanıcının sorusu vektöre çevrilir
            2. ChromaDB'de bu vektöre en yakın anılar bulunur
            3. Bulunan anılar metin olarak birleştirilip döndürülür
            4. Bu metin, Gemini'ye gönderilecek prompt'a eklenir
        
        Args:
            ancestor_id: Hangi atanın anılarında aranacak
            query: Kullanıcının sorusu/mesajı
            n_results: En fazla kaç sonuç getirilecek
            
        Returns:
            Bulunan anıların birleştirilmiş metni (boşsa "" döner)
        """
        collection = self._get_collection(ancestor_id)
        
        # Koleksiyonda hiç anı yoksa boş dön
        total_count = collection.count()
        if total_count == 0:
            return ""
        
        # Koleksiyondaki anı sayısından fazla sonuç istenmemeli
        actual_n = min(n_results, total_count)
        
        # Benzerlik araması yap
        results = collection.query(
            query_texts=[query],
            n_results=actual_n
        )
        
        # Sonuç yoksa boş dön
        if not results["documents"] or not results["documents"][0]:
            return ""
        
        # Bulunan anıları düzenli formatta birleştir
        memories = []
        for i, doc in enumerate(results["documents"][0]):
            memories.append(f"[Anı {i+1}]:\n{doc}")
        
        return "\n\n".join(memories)

    def delete_ancestor_memories(self, ancestor_id: int):
        """
        Bir ataya ait TÜM anıları ChromaDB'den sil.
        
        📚 Ata profili silindiğinde çağrılır.
            Koleksiyonun kendisini siler.
        
        Args:
            ancestor_id: Silinecek atanın ID'si
        """
        collection_name = f"legacy_ancestor_{ancestor_id}"
        try:
            self.client.delete_collection(name=collection_name)
            print(f"[ATA] Ancestor #{ancestor_id} anilari ChromaDB'den silindi.")
        except Exception as e:
            # Koleksiyon zaten yoksa sessizce geç
            print(f"[ATA] Silme hatasi (muhtemelen zaten yok): {e}")

    def get_memory_count(self, ancestor_id: int) -> int:
        """
        Bir atanın ChromaDB'deki anı sayısını döndür.
        
        Args:
            ancestor_id: Atanın ID'si
            
        Returns:
            Anı sayısı (int)
        """
        collection = self._get_collection(ancestor_id)
        return collection.count()


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON PATTERN — Tek bir örnek kullan
# ══════════════════════════════════════════════════════════════════════════════
# 📚 Uygulama boyunca tek bir LegacyMemoryManager kullanılır.
#    Bu sayede ChromaDB bağlantısı gereksiz yere tekrar açılmaz.

_legacy_memory_instance = None


def get_legacy_memory() -> LegacyMemoryManager:
    """
    LegacyMemoryManager singleton'ını döndür.
    İlk çağrıda oluşturulur, sonrakilerde mevcut örnek döner.
    """
    global _legacy_memory_instance
    if _legacy_memory_instance is None:
        _legacy_memory_instance = LegacyMemoryManager()
    return _legacy_memory_instance
