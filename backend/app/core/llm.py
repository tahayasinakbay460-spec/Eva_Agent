"""
Tek LLM kapısı — Otomatik Fallback Sistemi.

Birden fazla LLM sağlayıcıyı sırayla dener. Biri başarısız olursa
(kota, ağ hatası, API hatası) otomatik olarak sonrakine geçer.
Kullanıcı hiçbir şey fark etmez.

Desteklenen sağlayıcılar (hepsi OpenAI uyumlu + Gemini native):
  1. gemini   — Google Gemini (native SDK)
  2. deepseek — DeepSeek (OpenAI uyumlu)
  3. nvidia   — NVIDIA NIM (OpenAI uyumlu)
  4. groq     — Groq (OpenAI uyumlu)
  5. openrouter — OpenRouter (OpenAI uyumlu)
  6. sambanova  — SambaNova (OpenAI uyumlu)
"""
import traceback
from openai import OpenAI
from google import genai
from google.genai import types

from app.config import Config


# ═══════════════════════════════════════════════════════════════════════
# PROVIDER REGISTRY — Her sağlayıcının bağlantı bilgileri
# ═══════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "gemini": {
        "type": "gemini",  # Native SDK kullanır
        "api_key_attr": "GOOGLE_API_KEY",
        "model_attr": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
    },
    "deepseek": {
        "type": "openai",
        "base_url": "https://api.deepseek.com",
        "api_key_attr": "DEEPSEEK_API_KEY",
        "model_attr": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
    },
    "nvidia": {
        "type": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_attr": "NVIDIA_API_KEY",
        "model_attr": "NVIDIA_MODEL",
        "default_model": "meta/llama-3.1-8b-instruct",
    },
    "groq": {
        "type": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_attr": "GROQ_API_KEY",
        "model_attr": "GROQ_MODEL",
        "default_model": "llama-3.1-8b-instant",
    },
    "openrouter": {
        "type": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_attr": "OPENROUTER_API_KEY",
        "model_attr": "OPENROUTER_MODEL",
        "default_model": "google/gemini-2.0-flash-exp:free",
    },
    "sambanova": {
        "type": "openai",
        "base_url": "https://api.sambanova.ai/v1",
        "api_key_attr": "SAMBANOVA_API_KEY",
        "model_attr": "SAMBANOVA_MODEL",
        "default_model": "Meta-Llama-3.1-8B-Instruct",
    },
}


def _get_fallback_chain() -> list:
    """
    .env'deki LLM_FALLBACK_ORDER'a göre sıralı provider listesi döndürür.
    Sadece API key'i olan provider'lar dahil edilir.
    """
    order_str = getattr(Config, "LLM_FALLBACK_ORDER", "") or ""
    if order_str.strip():
        order = [p.strip().lower() for p in order_str.split(",") if p.strip()]
    else:
        # Varsayılan sıra: mevcut LLM_PROVIDER önce, sonra diğerleri
        primary = getattr(Config, "LLM_PROVIDER", "gemini").strip().lower()
        all_providers = ["gemini", "deepseek", "nvidia", "groq", "openrouter", "sambanova"]
        order = [primary] + [p for p in all_providers if p != primary]

    # Sadece API key'i olan provider'ları filtrele
    active = []
    for name in order:
        if name not in PROVIDERS:
            continue
        prov = PROVIDERS[name]
        api_key = getattr(Config, prov["api_key_attr"], None)
        if api_key and api_key.strip():
            active.append(name)

    return active


def generate_reply(
    system_content: str,
    conversation_history: list,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Ana LLM çağrısı — fallback chain boyunca dener.
    İlk başarılı cevabı döndürür. Hepsi başarısız olursa hata fırlatır.
    """
    chain = _get_fallback_chain()

    if not chain:
        raise ValueError(
            "Hiçbir LLM sağlayıcının API key'i bulunamadı! "
            ".env dosyasına en az bir API key ekleyin: "
            "GOOGLE_API_KEY, DEEPSEEK_API_KEY, NVIDIA_API_KEY, GROQ_API_KEY, "
            "OPENROUTER_API_KEY veya SAMBANOVA_API_KEY"
        )

    errors = []
    for provider_name in chain:
        try:
            prov = PROVIDERS[provider_name]
            if prov["type"] == "gemini":
                result = _call_gemini(prov, system_content, conversation_history, user_message, temperature, max_tokens)
            else:
                result = _call_openai_compat(provider_name, prov, system_content, conversation_history, user_message, temperature, max_tokens)

            if result and result.strip():
                return result
            else:
                errors.append(f"{provider_name}: Boş cevap döndü")

        except Exception as e:
            error_msg = f"{provider_name}: {type(e).__name__}: {str(e)[:200]}"
            errors.append(error_msg)
            print(f"[!] LLM Fallback -- {error_msg}")
            # Sonraki provider'a geç
            continue

    # Hiçbiri çalışmadı
    raise ValueError(
        f"Tüm LLM sağlayıcıları başarısız oldu!\n"
        + "\n".join(f"  - {e}" for e in errors)
    )


# ═══════════════════════════════════════════════════════════════════════
# PROVIDER ÇAĞRI FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════

def _build_openai_messages(system_content: str, conversation_history: list, user_message: str) -> list:
    """OpenAI uyumlu mesaj listesi oluşturur."""
    messages = [{"role": "system", "content": system_content}]
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": msg.get("content") or ""})
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_openai_compat(
    provider_name: str,
    prov: dict,
    system_content: str,
    conversation_history: list,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Tüm OpenAI uyumlu sağlayıcılar için tek çağrı fonksiyonu."""
    api_key = getattr(Config, prov["api_key_attr"])
    model = getattr(Config, prov["model_attr"], None) or prov["default_model"]

    client = OpenAI(
        base_url=prov["base_url"],
        api_key=api_key,
    )

    messages = _build_openai_messages(system_content, conversation_history, user_message)
    print(f"[LLM] {provider_name.upper()} ({model})")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise ValueError(f"{provider_name} boş cevap döndü.")
    print(f"[OK] {provider_name.upper()} basarili!")
    return text


def _call_gemini(
    prov: dict,
    system_content: str,
    conversation_history: list,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Google Gemini native SDK çağrısı."""
    api_key = getattr(Config, prov["api_key_attr"])
    model = getattr(Config, prov["model_attr"], None) or prov["default_model"]

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_content,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )

    contents = []
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg.get("content") or "")])
            )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )

    print(f"[LLM] GEMINI ({model})")
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    text = response.text
    if not text or not text.strip():
        raise ValueError("Gemini boş cevap döndü.")
    print(f"[OK] GEMINI basarili!")
    return text
