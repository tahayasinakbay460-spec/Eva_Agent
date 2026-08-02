"""
eva_agent.py - Eva'nın Gemini İstemcisi
====================================================
Bu dosya değişmedi — LangChain kodu Flask/FastAPI'den bağımsız!
Sadece Groq referansları kaldırıldı, yalnızca Gemini kaldı.
Şimdi Google'ın en yeni kütüphanesi 'google-genai' kullanacak şekilde güncellendi.
"""

from google import genai
from google.genai import types
from app.config import Config
from app.core.prompts import EVA_SYSTEM_PROMPT, MEMORY_INJECTION_TEMPLATE
from app.core.memory import get_memory


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
    conversation_history: list = None
) -> str:
    """
    Eva ile bir konuşma turu gerçekleştirir (Yeni google-genai SDK).
    """
    memory = get_memory()
    client = get_client()

    # ─── ADIM 1: Uzun Süreli Hafızayı Sorgula ───────────────────────────────
    relevant_memories = memory.retrieve_relevant_memories(
        user_id=user_id,
        query=user_message,
        n_results=4
    )

    # ─── ADIM 2: Sistem Promptunu Oluştur ───────────────────────────────────
    system_content = EVA_SYSTEM_PROMPT
    if relevant_memories:
        memory_block = MEMORY_INJECTION_TEMPLATE.format(
            memory_context=relevant_memories
        )
        system_content = system_content + "\n\n" + memory_block

    config = types.GenerateContentConfig(
        system_instruction=system_content,
        temperature=0.7,
        max_output_tokens=1024,
    )

    # ─── ADIM 3: Mesaj Listesini Oluştur ────────────────────────────────────
    contents = []

    # Oturum içi geçmişi ekle (son 10 mesajla sınırla)
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = 'user' if msg["role"] == "user" else 'model'
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
            )

    # Yeni kullanıcı mesajını ekle
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )

    # ─── ADIM 4: LLM'e Gönder ───────────────────────────────────────────────
    print(f"Gemini'ye gonderiliyor... (Hafiza: {'Var' if relevant_memories else 'Yok'})")
    response = client.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=contents,
        config=config
    )
    eva_response = response.text

    # ─── ADIM 5: Bu Konuşmayı Hafızaya Kaydet ───────────────────────────────
    memory.save_conversation(
        user_id=user_id,
        user_message=user_message,
        eva_response=eva_response
    )
    print("Konusma hafizaya kaydedildi.")

    return eva_response
