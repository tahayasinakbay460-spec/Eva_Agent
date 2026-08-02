# EVA Proje Yapısı ve Dosya Rehberi

Bu belge, EVA projenin tüm klasör ve dosya yapısını, her bir dosyanın ne işe yaradığını detaylıca açıklamaktadır. Mimariyi anlamak, projeyi gelecekte çok daha rahat geliştirmeni ve ölçeklendirmeni sağlayacaktır.

---

## 1. Frontend (Önyüz) Klasörü
Kullanıcının etkileşime girdiği görsel arayüzü temsil eder.

- **`index.html`**: Web sayfasının iskeletidir. Chat ekranındaki mesajlaşma kutusu, gönder butonu, sayfa başlığı gibi tüm görsel yapı taşları (butonlar, alanlar) burada tanımlanır.
- **`style.css`**: Sayfanın makyajıdır. Renkler, yazı tipleri, butonların yuvarlaklığı, arka planın görünümü ve gece/gündüz modu gibi tüm görsel estetik kuralları bu dosyada belirlenir.
- **`script.js`**: Sayfanın beyni ve hareket merkezidir (ön yüz için). Kullanıcı bir mesaj yazıp "Gönder"e bastığında, bu mesajı alıp backend'e (arkayüze) gönderen ve oradan gelen EVA'nın cevabını alıp ekrana yazdıran işlemleri yapar.

---

## 2. Backend (Arkayüz) Ana Dizini
Tüm zekanın, veritabanı işlemlerinin ve API'nin çalıştığı ana makine dairesidir.

- **`run.py`**: Projenin marş motorudur. Backend sunucusunu (Uvicorn/FastAPI) ayağa kaldırmak için çalıştırdığımız ana dosyadır. Projeyi başlatmak istediğimizde sadece bu dosyaya dokunuruz.
- **`.env`**: Çok gizli bilgilerin tutulduğu kasadır. API anahtarları (örneğin OpenAI veya Gemini key'leri), veritabanı şifreleri gibi bilgileri burada saklarız ki kodun içine yazılıp başkalarının eline geçmesin.
- **`requirements.txt`**: Projenin alışveriş listesidir. Projenin çalışması için internetten indirilmesi gereken dış paketlerin (FastAPI, Langchain, SQLAlchemy vb.) isimlerini ve versiyonlarını tutar.
- **`eva_users.db` / `instance/eva_users.db`**: SQLite veritabanı dosyalarıdır (Excel dosyası gibi düşünebilirsin). Kullanıcıların bilgilerini, geçmiş mesajlarını (eğer kaydediliyorsa) kalıcı olarak tuttuğumuz fiziksel tablolardır.
- **`chroma_db/`**: Vektör veritabanı klasörüdür. EVA'nın uzun süreli hafızası (RAG sistemi) için dokümanları ve kelimeleri "anlamsal" (vektörel) olarak sakladığı yerdir.
- **`venv/`**: Sanal çalışma ortamıdır (Virtual Environment). Projenin dışa bağımlı olduğu paketlerin bilgisayarın genelinden izole bir şekilde sadece bu proje için kurulduğu korumalı klasördür.

---

## 3. Backend İçerisindeki `app/` Klasörü (Uygulamanın Kalbi)
Bütün sistemin organize edildiği ana klasördür.

- **`main.py`**: Ana santraldir. Gelen isteklerin nereye gideceğini belirler, veritabanı bağlantılarını başlatır, genel ayarları yükler ve uygulamayı (FastAPI) oluşturur.
- **`config.py`**: Ayarlar dosyasıdır. `.env` dosyasındaki gizli bilgileri güvenli bir şekilde alıp tüm projenin okuyabileceği bir formata çevirir.
- **`database.py`**: Veritabanı ile (SQLite) program arasındaki köprüdür. Veritabanına nasıl bağlanılacağı, verilerin nasıl kaydedileceği ve okunacağı ile ilgili kuralları barındırır.
- **`__init__.py`**: Bu dosya, bulunduğu klasörün sıradan bir klasör değil, bir "Python modülü" olduğunu sisteme söyler (Genelde içi boştur).

### 3.1 `app/core/` (Çekirdek İş Mantığı)
EVA'nın yapay zeka beyni ve hafızası ile ilgili ana kodlar buradadır.
- **`eva_agent.py`**: EVA'nın zekasıdır. Langchain (veya benzeri yapay zeka kütüphaneleri) kullanılarak dil modelinin çağrıldığı, dış araçların (Google arama vs.) modele bağlandığı yerdir.
- **`memory.py`**: Kısa süreli hafıza yöneticisidir. Sen "Merhaba" dedikten sonra "Nasılsın?" dediğinde, önceki "Merhaba" mesajını hatırlamasını sağlayan sohbet geçmişi (Conversation Buffer) burada tutulur.
- **`prompts.py`**: EVA'nın kişiliğini belirleyen kurallar bütünüdür. "Sen bir asistansın, adın EVA, Türkçe konuşacaksın" gibi sisteme verilen gizli komutların (System Prompt) bulunduğu metinleri içerir.

### 3.2 `app/routes/` (API Yönlendirmeleri - Yollar)
Dışarıdan gelen isteklerin (Frontend'den gelen mesajların) karşılandığı gişelerdir.
- **`chat.py`**: Chat işlemleri için ayrılmış özel gişedir. Frontend'den gelen mesajı alır, `eva_agent.py`'a gönderir, oradan gelen yapay zeka cevabını tekrar paketleyip frontend'e geri yollar.

### 3.3 `app/models/` (Veritabanı Tabloları)
Veritabanındaki tabloların kod tarafındaki karşılıklarıdır (Mimari çizimler).
- **`user.py`**: Veritabanındaki bir kullanıcının veya bir mesajın neye benzeyeceğini (Örn: isim, e-posta, mesaj içeriği, gönderilme tarihi vb.) tarif eden kalıplardır.

### 3.4 `app/schemas/` (Veri Doğrulama Şemaları)
Gelen ve giden kargoların (verilerin) güvenlik kontrolünden geçtiği yerdir (Pydantic).
- **`chat.py`**: Frontend'den gelen mesajın gerçekten bir metin (string) olup olmadığını kontrol eder. Boş mesaj geldiyse hata fırlatarak sistemin çökmesini engeller.

---

## 4. Kök Dizin (Root)
- **`.gitignore`**: Git (Versiyon kontrol) sisteminin "görmezden gelmesi" gereken dosyaların listesidir. Örneğin şifreleri içeren `.env`, veritabanı `eva_users.db` veya boyutça çok büyük olan `venv` klasörü gibi dosyaların internete (GitHub'a) yanlışlıkla yüklenmesini engeller.
- **`README.md`**: Projenin kullanım kılavuzudur. Projeyi bilgisayarına ilk defa kuracak birine projenin ne olduğunu, nasıl kurulacağını ve çalıştırılacağını anlatır.

---

## 5. Tüm Dosyaları Tek Bir Dosyada Birleştirseydik Ne Olurdu? (Monolitik Yapı)

Eğer şu an sahip olduğumuz tüm bu klasörleri ve dosyaları (HTML, CSS, JS hariç, sadece Python backend dosyalarını) **tek bir büyük `app.py` dosyasında** birleştirseydik:

### Ne Olurdu?
1. **Çok Uzun Bir Dosya:** `app.py` dosyan muhtemelen binlerce satır uzunluğunda olurdu. 
2. **Karmakarışık Bir Yapı:** En üstte veritabanı ayarları, hemen altında API yolları, onun altında yapay zeka (Agent) ayarları, en altta veritabanı modelleri olurdu.

### Neden Böyle Yapmıyoruz? (Modüler Yapının Avantajları)
- **Hata Bulma (Debugging):** Tek dosyada bir hata olduğunda "Nerede bu hata?" diyerek binlerce satır kodu taraman gerekir. Modüler yapıda ise "Veritabanına bağlanamıyorum" hatası alırsan direkt `database.py`'a; "EVA yanlış cevap veriyor" hatası alırsan direkt `eva_agent.py`'a veya `prompts.py`'a gidersin.
- **Ekip Çalışması:** Eğer bir gün projeye bir arkadaşını dahil edersen, tek dosyada aynı anda çalışmanız imkansızdır (Sürekli birbirinizin kodunu ezersiniz). Ama şu anki yapıda sen `eva_agent.py` üzerinde çalışırken o `user.py` üzerinde aynı anda sorunsuz çalışabilir.
- **Genişletilebilirlik (Ölçeklendirme):** Yarın projeye "Giriş Yap / Üye Ol" ekranı (Auth), "Ödeme Yap" ekranı (Payment) gibi yeni özellikler eklemek istediğinde tek dosya patlama noktasına gelir. Modüler yapıda sadece `routes/auth.py` veya `routes/payment.py` diye yeni dosyalar açıp hiç sistemi bozmadan yoluna devam edebilirsin.
- **Tekrar Kullanılabilirlik:** `config.py` içindeki ayarları, projenin 5 farklı yerinden hiçbir kodu kopyala-yapıştır yapmadan tek bir satırla çağırıp kullanabilirsin.

Kısacası, bu "parçalara ayırma" yöntemi yazılım mühendisliğinin en temel prensiplerinden biridir (Seperation of Concerns - Sorumlulukların Ayrılığı). Projen şu anda profesyonel, modern ve büyümeye oldukça müsait bir iskelete sahip!
