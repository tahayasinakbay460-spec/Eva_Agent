"""
eva_agent.py - Eva'nın Gemini İstemcisi
====================================================
Bu dosya değişmedi — LangChain kodu Flask/FastAPI'den bağımsız!
Sadece Groq referansları kaldırıldı, yalnızca Gemini kaldı.
Şimdi Google'ın en yeni kütüphanesi 'google-genai' kullanacak şekilde güncellendi.
"""

from google import genai
from google.genai import types # google ' a istek gonderirken onun kutuphanesini kurallarıyla donatıp gondermemiz gerekiyor 
from app.config import Config
from app.core.prompts import EVA_SYSTEM_PROMPT, MEMORY_INJECTION_TEMPLATE, EMOTION_INJECTION_TEMPLATE
from app.core.memory import get_memory
from app.core.emotion_analyzer import (
    get_filtered_emotion, analyze_emotion,
    EMOTION_LABELS_TR
)


def _create_client():
    """
    Yeni google-genai SDK'sı ile Gemini Client oluşturur.
    """
    if not Config.GOOGLE_API_KEY:
        raise ValueError(
            "❌ GOOGLE_API_KEY eksik!\n"
            ".env dosyasına API key'ini ekle:\n"
            "GOOGLE_API_KEY=AIza...\n"
            "Key almak için: https://aistudio.google.com/apikey"
        )
    print(f"LLM: Google Gemini ({Config.GEMINI_MODEL}) (Yeni SDK)")
    return genai.Client(api_key=Config.GOOGLE_API_KEY)


_client = None

def get_client():
    global _client
    if _client is None:
        _client = _create_client()
    return _client


def chat_with_eva(
    user_message: str,
    user_id: str = "default_user",
    conversation_history: list = None,
    detected_emotion: str = None
) -> str:
    """
    Eva ile bir konuşma turu gerçekleştirir (Yeni google-genai SDK).
    
    Faz 5: detected_emotion parametresi eklenmiştir.
    Kameradan tespit edilen duygu etiketi buraya gelir ve
    3 katmanlı güvenlik filtresinden geçirildikten sonra
    LLM'e gizli bir sistem notu olarak enjekte edilir.
    """
    memory = get_memory()  #hafıza nesnesi olusturuyor 
    client = get_client() # LLM ile olan baglantı motorunu calıştırıyor.

    # ─── ADIM 1: Uzun Süreli Hafızayı Sorgula ───────────────────────────────
    relevant_memories = memory.retrieve_relevant_memories(
        user_id=user_id,
        query=user_message,
        n_results=4
    )

    # ─── ADIM 2: Sistem Promptunu Oluştur ───────────────────────────────────
    system_content = EVA_SYSTEM_PROMPT
    if relevant_memories:
        memory_block = MEMORY_INJECTION_TEMPLATE.format( # format {} blokları varsa onları dolduruyor.
            memory_context=relevant_memories
        )
        system_content = system_content + "\n\n" + memory_block

    # ─── ADIM 2.5 (Faz 5): Duygu Etiketini Prompt'a Enjekte Et ───────────
    # 📚 Kameradan gelen duygu etiketi, 3 katmanlı filtreden geçirildikten sonra
    #     LLM'e gizli bir not olarak eklenir. Kullanıcı bu notu görmez.
    if detected_emotion and detected_emotion != "neutral":
        # Sahte bir emotion_result oluştur (WS'den gelen etiketi kullanarak)
        camera_result = {
            "emotion": detected_emotion,
            "emotion_tr": EMOTION_LABELS_TR.get(detected_emotion, "nötr"),
            "confidence": 0.80,  # Frontend'den sadece etiket geliyor, default confidence
            "all_emotions": {}
        }
        
        # Katman 2 + 3 filtrelerini uygula (metin hiyerarşisi + hafıza filtresi)
        filtered = get_filtered_emotion(
            camera_emotion_result=camera_result,
            user_message=user_message,
            relevant_memories=relevant_memories
        )
        
        final_emotion = filtered["emotion"]
        final_emotion_tr = filtered["emotion_tr"]
        
        # Sadece nötr olmayan duygular için enjekte et
        if final_emotion != "neutral":
            emotion_block = EMOTION_INJECTION_TEMPLATE.format(
                emotion_tr=final_emotion_tr,
                confidence=int(filtered["confidence"] * 100)
            )
            system_content = system_content + "\n\n" + emotion_block
            print(f"🎭 Duygu enjekte edildi: {final_emotion_tr} (filtre: {filtered['filtered']})")

    config = types.GenerateContentConfig(
        system_instruction=system_content,
        temperature=0.7,   # Yaratıcılık katsayısı 0 ila 1 arası degişir . 0 da robot 1 de ise hallusinasyon gorur. 
        max_output_tokens=1024, # En fazla 1024 token ver diyoruz,Token = 4 harf, Maaliyet hesabı burda yapılır.
    )

    # ─── ADIM 3: Mesaj Listesini Oluştur ────────────────────────────────────
    contents = []

    # Oturum içi geçmişi ekle (son 10 mesajla sınırla)
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = 'user' if msg["role"] == "user" else 'model'
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]) 
            )# Googleın istedigi sekilde mesaj yapısını kuruyoruz. Bu yüzden parantezler çok önemlidir.

    # Yeni kullanıcı mesajını ekle
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )

    # ─── ADIM 4: LLM'e Gönder ───────────────────────────────────────────────
    print(f"Gemini'ye gonderiliyor... (Hafiza: {'Var' if relevant_memories else 'Yok'})")
    response = client.models.generate_content( #Bu fonksiyon asıl zekayı burada çağırıyor. Asıl aksiyon burda kral! 
        model=Config.GEMINI_MODEL,
        contents=contents,
        config=config
    )
    eva_response = response.text # LLM'den gelen ham cevabı alıyoruz.

    # ─── ADIM 5: Bu Konuşmayı Hafızaya Kaydet ───────────────────────────────
    memory.save_conversation(
        user_id=user_id,
        user_message=user_message,
        eva_response=eva_response
    )
    print("Konusma hafizaya kaydedildi.")

    return eva_response
