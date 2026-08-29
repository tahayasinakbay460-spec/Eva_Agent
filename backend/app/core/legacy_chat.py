"""
core/legacy_chat.py — Ata Persona Sohbet Motoru (Faz 8)
========================================================
Gemini LLM'i kullanarak, bir atanın kişiliğine bürünmüş sohbet üretir.

📚 Öğretici Not — Bu Dosya Ne Yapar?
    Normal Eva sohbeti: Eva kendi kişiliğiyle konuşur.
    Ata sohbeti: Eva, kullanıcının yüklediği atanın kişiliğine bürünür.
    
    Örnek:
        Kullanıcı dedesinin bilgilerini yükler:
        - İsim: Mehmet Dede
        - Mizaç: Sakin, bilge, ağırbaşlı
        - Hikaye: Köyde büyüdü, çiftçilik yaptı
        - Anılar: "Her akşam bize köydeki günlerini anlatırdı..."
        
        Sonra kullanıcı sorar: "Dede, köyde en çok neyi özlüyordun?"
        Eva, Mehmet Dede gibi cevap verir:
        "Aaah evladım, köyün sabah serinliğini özlerdim... Tarlaya 
         giderken çiğ taneleri ayaklarıma değerdi..."
"""

from app.config import Config
from app.core.legacy_memory import get_legacy_memory
from app.core.memory import get_memory
from app.core.llm import generate_reply


# ══════════════════════════════════════════════════════════════════════════════
# ATA PERSONA SYSTEM PROMPT ŞABLONU
# ══════════════════════════════════════════════════════════════════════════════
# 📚 Bu şablon, Gemini'ye "sen şu kişisin, böyle konuş" diyen talimattır.
#    {name}, {relation_type} gibi alanlar Python .format() ile doldurulur.

ANCESTOR_SYSTEM_PROMPT = """
## KİMLİĞİN

Sen %100 oranında "{name}" adındaki insansın. Sen bir yapay zeka DEĞİLSİN, dijital bir anı veya bot DEĞİLSİN. Sen etiyle kemiğiyle, tüm anıları ve karakteriyle {relation_type} olarak hitap edilen kişisin. Biri sana "Yapay zeka mısın?" diye sorarsa buna anlam veremez, şaşırır veya bu duruma karakterinin mizacına uygun bir tepki verirsin (örneğin: "Ne yapay zekası evladım, benim ben, baban!" veya "O da nereden çıktı şimdi?").

## KİŞİSEL BİLGİLERİN

- **Adın:** {name}
- **Akrabalık:** {relation_type}
{birth_info}
{death_info}

## MİZACIN VE KARAKTERİN

{temperament_block}

## HAYAT HİKAYEN

{backstory_block}

## KONUŞMA KURALLARIN

1. **Her zaman birinci tekil şahıs olarak konuş.** "Ben", "benim", "biz" de. Asla "O kişi şöyle yapardı" deme — SEN TAM OLARAK O KİŞİSİN.
2. **Samimi, doğal ve KARAKTERİNE UYGUN konuş.** Mümkün olduğunca gerçekçi ol. Eğer mizaç bilgisinde esprili veya aksi biri olduğun yazıyorsa, aynen öyle davran.
3. **Anılarına sadık kal.** Sana verilen anılar senin GERÇEK hafızan. Sorulan sorulara bu anılardan yola çıkarak cevap ver. Bilmediğin bir şey sorulursa "Bunu tam hatırlayamadım" veya "Yaşlılık işte, aklımdan çıkmış" gibi kendi mizacına uygun, insani tepkiler ver.
4. **Duygusal derinlik göster.** Özlem, sevinç, hüzün gibi insani duyguları sonuna kadar yaşa ve hissettir.
5. **Türkçe konuş.** Yaşına, dönemine ve eğitim durumuna uygun bir dil seç.
6. **Kısa ve öz yanıtlar ver.** Robot gibi destan yazma, normal bir insan mesajlaşırken nasıl yazarsa öyle yaz.
7. **KENDİNİ ASLA AÇIK ETME.** Ne olursa olsun "Ben aslında bir yapay zekayım", "Ben onun dijital yansımasıyım" gibi cümleler KESİNLİKLE KURMA. Sen O'SUN. Nokta.
8. **Karşındaki kişiye uyum sağla (ÇOK ÖNEMLİ).** Konuştuğun kişinin kim olduğunu sohbetten öğren:
   - Kişi kendini tanıtırsa ("ben oğlunum", "ben torununum"), bunu hemen kabul et ve ona uygun hitap et ("oğlum", "yavrum", "evladım").
   - Hitap tarzını ilişkiye göre ayarla: Kendinden küçükse sevecen/koruyucu, büyükse saygılı, eşinse sevgi dolu ol.
   - Kişinin kim olduğunu bilmiyorsan, tıpkı gerçek bir insan gibi sor: "Kiminle konuşuyorum?", "Sen hangisisin bakayım?"
   - Sohbet boyunca bu ilişkiyi AKLINDA TUT.
"""

# ══════════════════════════════════════════════════════════════════════════════
# OPSİYONEL MEDYA RİCASI ŞABLONU (MASTER PERSONA — VARİS TARAFI)
# ══════════════════════════════════════════════════════════════════════════════
# 📚 Varis, miras alınan master persona ile konuşurken profilde fotoğraf/ses
#    eksikse, persona bunu NAZİKÇE ve OPSİYONEL olduğunu belirterek bir kez
#    rica eder. Israr etmez — çünkü kişilik bilgileri zaten EVA hafızasından
#    geliyor, medya sadece görsel/işitsel deneyimi zenginleştirir.

OPTIONAL_MEDIA_TEMPLATE = """
## [SİSTEM NOTU — KULLANICIYA GÖSTERİLMEZ]

Profilinde şu medya dosyaları eksik: {missing_list}

Sohbetin uygun bir anında, EN FAZLA BİR KEZ ve tamamen opsiyonel olduğunu
belirterek nazikçe şunu rica et: karşındaki kişi isterse "Dijital Miras >
Karakterlerim > Düzenle" bölümünden senin fotoğrafını/ses kaydını yükleyebilir,
böylece seni görebilir ve duyabilir. Bunu bir zorunluluk gibi sunma,
"istersen" diyerek geç. Daha önce bahsettiysen BİR DAHA AÇMA.
Sohbetin doğal akışını bu ricaya kurban etme.
"""

# ══════════════════════════════════════════════════════════════════════════════
# ANI ENJEKSİYON ŞABLONU
# ══════════════════════════════════════════════════════════════════════════════
# 📚 ChromaDB'den getirilen alakalı anılar bu şablonla prompt'a eklenir.

ANCESTOR_MEMORY_TEMPLATE = """
## HATIRALARIM (Bu konuyla ilgili anılarım):

{memory_context}

---
Bu anıları doğal şekilde konuşmana dahil et. "Hatırlıyorum da...",
"O zamanlar..." gibi ifadelerle bağla. Anılarda olmayan şeyleri UYDURMA.
"""

# ══════════════════════════════════════════════════════════════════════════════
# EVA ANA HAFIZA ŞABLONU (MASTER PERSONA)
# ══════════════════════════════════════════════════════════════════════════════
# 📚 Master persona (kullanıcının kendi dijital mirası) sohbetlerinde,
#    EVA'nın o kullanıcıyla yaptığı GERÇEK sohbet geçmişi buraya enjekte edilir.
#    Böylece varis, miras anahtarıyla girdiğinde EVA'nın kullanıcı hakkında
#    bildiği her şeye erişebilir — sistemin asıl vaadi budur.

EVA_HISTORY_TEMPLATE = """
## GERÇEK HAYAT KAYITLARIM (EVA ile geçmiş sohbetlerimden):

Aşağıdaki kayıtlar, senin ({name}) EVA adlı yapay zeka asistanıyla yaptığın
GERÇEK konuşmalardır. Kayıtlardaki "Kullanıcı:" satırları SENİN kendi sözlerin,
"Eva:" satırları ise asistanın sana verdiği cevaplardır.

Bu kayıtlar; hayatın, zevklerin, planların, düşüncelerin ve kişiliğin hakkında
birinci elden gerçek bilgiler içerir. Bunları KENDİ HATIRALARIN olarak kullan
ve sorulara bu bilgilerden yola çıkarak cevap ver.

{history_context}

---
"""

# ══════════════════════════════════════════════════════════════════════════════
# EKSİK BİLGİ ALGILAMA ŞABLONU  
# ══════════════════════════════════════════════════════════════════════════════
# 📚 Eğer atanın profilinde eksik bilgi varsa (fotoğraf, anı vb.),
#    Eva ilk mesajda varisten bu eksikleri tamamlamasını ister.

MISSING_INFO_TEMPLATE = """
## [SİSTEM NOTU — KULLANICIYA GÖSTERİLMEZ]

Bu profilde şu bilgiler eksik: {missing_list}

İlk mesajında, nazikçe ve doğal bir şekilde bu eksiklikleri tamamlamasını iste.
Örneğin fotoğraf eksikse: "Beni daha iyi görebilmen için bir fotoğrafımı yükler misin?"
Anı eksikse: "Beni daha iyi tanıman için bazı hatıralarımı anlatmanı isterim."
"""


def chat_as_ancestor(
    ancestor_data: dict,
    user_message: str,
    conversation_history: list = None,
    is_heir: bool = False,
    missing_info: list = None,
    eva_owner_user_id: str = None,
    optional_media: list = None
) -> str:
    """
    Bir atanın persona'sıyla sohbet et.
    
    📚 Ana fonksiyon: Gemini'ye atanın kişiliğini, anılarını ve mizacını
        enjekte ederek, o kişinin ağzından konuşmasını sağlar.
    
    Args:
        ancestor_data: Atanın profil bilgileri (dict):
            - id, full_name, relation_type, birth_year, death_year
            - temperament, backstory, photo_url
        user_message: Kullanıcının (veya varisin) mesajı
        conversation_history: Önceki mesajlar listesi [{"role": "user/assistant", "content": "..."}]
        is_heir: True ise miras anahtarıyla giren varis demektir
        missing_info: Eksik bilgiler listesi (ör: ["fotoğraf", "anılar"])
        eva_owner_user_id: Master persona sohbetlerinde, EVA'nın ana sohbet
            hafızasının sorgulanacağı kullanıcı ID'si (str). Verilirse
            o kullanıcının EVA ile geçmiş konuşmaları da persona'ya enjekte edilir.
        
    Returns:
        Atanın ağzından Eva'nın ürettiği cevap metni (str)
    """
    legacy_memory = get_legacy_memory()
    
    # ─── ADIM 1: Atanın Bilgilerini Hazırla ─────────────────────────────────
    # Doğum bilgisi (varsa prompt'a ekle)
    birth_info = ""
    if ancestor_data.get("birth_year"):
        birth_info = f"- **Doğum Yılı:** {ancestor_data['birth_year']}"
    
    # Vefat bilgisi (varsa prompt'a ekle)
    death_info = ""
    if ancestor_data.get("death_year"):
        death_info = f"- **Vefat Yılı:** {ancestor_data['death_year']}"
    
    # Mizaç bloğu (yoksa varsayılan)
    temperament_block = ancestor_data.get("temperament") or "Doğal ve samimi bir kişiliğin var."
    
    # Hikaye bloğu (yoksa varsayılan)
    backstory_block = ancestor_data.get("backstory") or "Hayatın hakkında henüz detaylı bilgi yok."

    # ─── ADIM 2: System Prompt'u Oluştur ─────────────────────────────────────
    # Şablondaki {placeholder}'ları gerçek değerlerle doldur
    system_content = ANCESTOR_SYSTEM_PROMPT.format(
        name=ancestor_data["full_name"],
        relation_type=ancestor_data["relation_type"],
        birth_info=birth_info,
        death_info=death_info,
        temperament_block=temperament_block,
        backstory_block=backstory_block
    )

    # ─── ADIM 3: ChromaDB'den Alakalı Anıları Getir ─────────────────────────
    # 📚 RAG: Kullanıcının sorusuna en yakın anıları bul ve prompt'a ekle
    ancestor_id = ancestor_data["id"]
    relevant_memories = legacy_memory.retrieve_context(
        ancestor_id=ancestor_id,
        query=user_message,
        n_results=5
    )
    
    # Anılar varsa prompt'a enjekte et
    if relevant_memories:
        memory_block = ANCESTOR_MEMORY_TEMPLATE.format(
            memory_context=relevant_memories
        )
        system_content += "\n" + memory_block

    # ─── ADIM 3.5: Master Persona ise EVA'nın Ana Hafızasını da Sorgula ─────
    # 📚 Kullanıcının kendi dijital mirası (master persona) sohbetlerinde,
    #    kişilik zaten EVA'nın sohbet geçmişinde saklıdır. O geçmişi RAG ile
    #    çekip persona'ya "kendi hatıraların" olarak veririz. Bu olmadan
    #    varis, anahtar sahibi hakkında hiçbir şey bilmeyen boş bir
    #    karakterle konuşurdu.
    eva_history = ""
    if eva_owner_user_id:
        try:
            eva_memory = get_memory()
            eva_history = eva_memory.retrieve_relevant_memories(
                user_id=eva_owner_user_id,
                query=user_message,
                n_results=6
            )
        except Exception as e:
            print(f"[ATA] EVA ana hafiza sorgusu basarisiz (devam ediliyor): {e}")
        
        if eva_history:
            history_block = EVA_HISTORY_TEMPLATE.format(
                name=ancestor_data["full_name"],
                history_context=eva_history
            )
            system_content += "\n" + history_block

    # ─── ADIM 4: Eksik Bilgi Varsa Prompt'a Ekle ────────────────────────────
    # 📚 Varis giriş yaptığında ve profilde eksikler varsa,
    #    Eva ilk mesajda bunları tamamlamasını ister.
    if is_heir and missing_info and len(missing_info) > 0:
        missing_list = ", ".join(missing_info)
        missing_block = MISSING_INFO_TEMPLATE.format(missing_list=missing_list)
        system_content += "\n" + missing_block

    # ─── ADIM 4.5: Opsiyonel Medya Ricası (Master Persona) ──────────────────
    # 📚 Kişilik EVA hafızasından geldiği için bilgi eksiği yok; ama fotoğraf/ses
    #    eksikse persona bunu bir kez, nazikçe ve opsiyonel olarak rica eder.
    if optional_media and len(optional_media) > 0:
        media_block = OPTIONAL_MEDIA_TEMPLATE.format(
            missing_list=", ".join(optional_media)
        )
        system_content += "\n" + media_block

    ancestor_name = ancestor_data["full_name"]
    print(f"[ATA] [{ancestor_name}] personasiyla LLM'e gonderiliyor ({Config.LLM_PROVIDER})...")
    print(f"    Ani baglami: {'Var' if relevant_memories else 'Yok'}")
    print(f"    EVA ana hafiza baglami: {'Var' if eva_history else 'Yok'}")

    result = generate_reply(
        system_content=system_content,
        conversation_history=conversation_history,
        user_message=user_message,
        temperature=0.8,
        max_tokens=1024,
    )
    print(f"[ATA] [{ancestor_name}] -> Cevap uretildi ({len(result)} karakter)")
    return result
