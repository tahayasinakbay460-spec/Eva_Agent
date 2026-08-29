"""
eva_agent.py - Eva sohbet motoru
================================
Hafıza + duygu filtresi burada. Asıl LLM çağrısı core/llm.py'de
(Gemini veya NVIDIA NIM).
"""

from app.config import Config
from app.core.prompts import EVA_SYSTEM_PROMPT, MEMORY_INJECTION_TEMPLATE, EMOTION_INJECTION_TEMPLATE
from app.core.memory import get_memory
from app.core.llm import generate_reply
from app.core.emotion_analyzer import (
    get_filtered_emotion, normalize_emotion_label,
    EMOTION_LABELS_TR
)


def chat_with_eva(
    user_message: str,
    user_id: str = "default_user",
    conversation_history: list = None,
    detected_emotion: str = None
) -> str:
    memory = get_memory()

    relevant_memories = memory.retrieve_relevant_memories(
        user_id=user_id,
        query=user_message,
        n_results=4
    )

    system_content = EVA_SYSTEM_PROMPT
    if relevant_memories:
        memory_block = MEMORY_INJECTION_TEMPLATE.format(
            memory_context=relevant_memories
        )
        system_content = system_content + "\n\n" + memory_block

    if detected_emotion and detected_emotion != "neutral":
        detected_emotion = normalize_emotion_label(detected_emotion)

        camera_result = {
            "emotion": detected_emotion,
            "emotion_tr": EMOTION_LABELS_TR.get(detected_emotion, "nötr"),
            "confidence": 0.80,
            "all_emotions": {}
        }

        filtered = get_filtered_emotion(
            camera_emotion_result=camera_result,
            user_message=user_message,
            relevant_memories=relevant_memories
        )

        final_emotion = filtered["emotion"]
        final_emotion_tr = filtered["emotion_tr"]

        if final_emotion != "neutral":
            emotion_block = EMOTION_INJECTION_TEMPLATE.format(
                emotion_tr=final_emotion_tr,
                confidence=int(filtered["confidence"] * 100)
            )
            system_content = system_content + "\n\n" + emotion_block
            print(f"[DUYGU] Duygu enjekte edildi: {final_emotion_tr} (filtre: {filtered['filtered']})")

    print(f"LLM'e gonderiliyor ({Config.LLM_PROVIDER})... (Hafiza: {'Var' if relevant_memories else 'Yok'})")
    eva_response = generate_reply(
        system_content=system_content,
        conversation_history=conversation_history,
        user_message=user_message,
        temperature=0.7,
        max_tokens=1024,
    )

    memory.save_conversation(
        user_id=user_id,
        user_message=user_message,
        eva_response=eva_response
    )
    print("Konusma hafizaya kaydedildi.")

    return eva_response
