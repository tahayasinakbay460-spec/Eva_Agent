/**
 * script.js — Eva AI Frontend Mantığı
 * ======================================
 * Tüm JavaScript kodu burada.
 * Bölümler:
 *   1. Ayarlar & Global Değişkenler
 *   2. API İletişimi (fetch ile backend'e istek)
 *   3. Mesaj Ekleme (DOM'a yeni mesaj ekle)
 *   4. UI Durum Güncellemeleri (loading, status)
 *   5. Olay Dinleyicileri (buton click, enter tuşu vb.)
 *   6. Başlangıç
 */


/* ================================================================
   1. AYARLAR & GLOBAL DEĞİŞKENLER
   ================================================================ */

// Backend API adresi
const API_BASE = 'http://localhost:8000/api';

// Oturum yönetimi
function getToken() { return localStorage.getItem('eva_token'); }
function getUsername() { return localStorage.getItem('eva_username'); }
function clearSession() {
  localStorage.removeItem('eva_token');
  localStorage.removeItem('eva_user_id');
  localStorage.removeItem('eva_username');
}

// Oturum içi konuşma geçmişi
let conversationHistory = [];

// Eva şu an cevap üretiyor mu?
let isLoading = false;

// HTML elementleri — sayfa yüklenince bunlara erişeceğiz
const chatWindow = document.getElementById('chat-window');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnClear = document.getElementById('btn-clear');
const btnLogout = document.getElementById('btn-logout');
const statusText = document.getElementById('status-text');
const avatarThinking = document.getElementById('avatar-thinking');
const iconSend = document.getElementById('icon-send');
const iconLoading = document.getElementById('icon-loading');
const headerUsername = document.getElementById('header-username');


/* ================================================================
   2. API İLETİŞİMİ
   ================================================================ */

/**
 * Eva'ya mesaj gönderir ve cevabı döndürür.
 *
 * @param {string} message - Kullanıcının yazdığı mesaj
 * @returns {Promise<string>} - Eva'nın cevabı
 *
 * 📚 fetch() nedir?
 *   Tarayıcının yerleşik HTTP istek fonksiyonu.
 *   axios'un yaptığını yapar ama ekstra kütüphane gerekmez.
 *   async/await ile kullanmak çok okunabilir.
 */
async function sendMessageToEva(message) {
  const token = getToken();
  if (!token) { logout(); return ''; }

  const requestBody = { // burda token kullanamamızın sebebi eger fetch ile user id gonderseydik 
    // hackerlar ele gecirebilir. Ama JWT token ile bu token'ın içindeki user id'yi alıyoruz
    // token hash'li olduğu için değiştirilmesi zor.
    message: message,
    history: conversationHistory
    // user_id gönderilmiyor — backend token'dan alıyor
  };

  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`   // ← JWT TOKEN
    },
    body: JSON.stringify(requestBody)
  });

  if (response.status === 401 || response.status === 403) {
    // Token süresi dolmuş
    clearSession();
    window.location.href = '/';
    return '';
  }

  const data = await response.json();

  if (!response.ok) {
    // Hata detayını F12 konsoluna yazdır
    console.error("Backend Hatası:", data.detail || data);
    throw new Error(data.detail || 'Sunucu hatası');
  }

  return data.response;
}

/**
 * Backend sağlık kontrolü
 */
async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    return response.ok;
  } catch {
    return false;
  }
}


/* ================================================================
   3. MESAJ EKLEME (DOM İşlemleri)
   ================================================================ */

/**
 * Saati "HH:MM" formatında döndürür.
 */
function getCurrentTime() {
  return new Date().toLocaleTimeString('tr-TR', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

/**
 * Sohbet penceresine yeni bir mesaj ekler.
 *
 * @param {string} content  - Mesajın metni
 * @param {'user'|'eva'} role - Kim yazdı?
 * @param {boolean} isError - Hata mesajı mı?
 * @returns {HTMLElement} - Oluşturulan mesaj elementi (güncelleme için)
 *
 * 📚 DOM nedir?
 *   Document Object Model — HTML belgesi bir ağaç yapısı.
 *   document.createElement() ile yeni element oluşturulur.
 *   element.appendChild() ile ağaca eklenir.
 */
function addMessage(content, role, isError = false) {
  const isUser = role === 'user';

  // ── Mesaj satırı (tüm satır) ──────────────────────────────
  const row = document.createElement('div');
  row.className = `message-row ${isUser ? 'user' : 'eva'}`;

  // ── Avatar ────────────────────────────────────────────────
  const avatar = document.createElement('div');
  avatar.className = `msg-avatar ${isUser ? 'user-avatar' : ''}`;
  avatar.textContent = isUser ? '👤' : '🤖';

  // ── Mesaj içeriği kapsayıcısı ─────────────────────────────
  const content_wrapper = document.createElement('div');
  content_wrapper.className = 'message-content';

  // Meta (isim + saat)
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.innerHTML = `
    <span class="message-sender">${isUser ? 'Sen' : 'Eva'}</span>
    <span class="message-time">${getCurrentTime()}</span>
  `;

  // Balon
  const bubble = document.createElement('div');
  bubble.className = `message-bubble ${isUser ? 'user' : 'eva'} ${isError ? 'error' : ''}`;

  if (isUser) {
    // Kullanıcı mesajı: düz metin (güvenlik için HTML encode edilmez ama escape edilmeli)
    bubble.textContent = content;
  } else {
    // Eva'nın mesajı: Markdown → HTML dönüşümü
    // marked.parse() markdown'ı HTML'e çevirir
    bubble.innerHTML = marked.parse(content);
    // Link'leri yeni sekmede aç
    bubble.querySelectorAll('a').forEach(a => {
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    });
  }

  // Hepsini birleştir
  content_wrapper.appendChild(meta);
  content_wrapper.appendChild(bubble);

  row.appendChild(avatar);
  row.appendChild(content_wrapper);

  // Sohbet penceresine ekle
  chatWindow.appendChild(row);

  // En alta kaydır
  scrollToBottom();

  return bubble;  // Güncellemek için dönder
}

/**
 * "Eva yazıyor..." göstergesini ekler.
 * @returns {HTMLElement} - Gösterge elementi (kaldırmak için)
 */
function addTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'message-row eva';
  row.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '🤖';

  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = '<span></span><span></span><span></span>';

  row.appendChild(avatar);
  row.appendChild(indicator);
  chatWindow.appendChild(row);
  scrollToBottom();

  return row;
}

/**
 * Yazma göstergesini kaldırır.
 */
function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();
}

/**
 * Sohbet penceresini en alta kaydırır.
 */
function scrollToBottom() {
  // setTimeout ile DOM güncellemesinin bitmesini bekle
  setTimeout(() => {
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }, 50);
}


/* ================================================================
   4. UI DURUM GÜNCELLEMELERİ
   ================================================================ */

/**
 * Yükleme durumunu açar/kapatır.
 * @param {boolean} loading - true = yükleniyor, false = hazır
 */
function setLoading(loading) {
  isLoading = loading;

  if (loading) {
    // Gönder butonunu yükleme moduna al
    btnSend.disabled = true;
    btnSend.classList.add('loading');
    iconSend.style.display = 'none';
    iconLoading.style.display = 'block';

    // Textarea devre dışı bırak
    userInput.disabled = true;

    // Status "Düşünüyor..." yap
    statusText.textContent = '● Düşünüyor...';
    statusText.classList.add('thinking');

    // Avatar düşünme animasyonu
    avatarThinking.classList.add('active');

  } else {
    // Gönder butonunu normal hale getir
    btnSend.disabled = userInput.value.trim().length === 0;
    btnSend.classList.remove('loading');
    iconSend.style.display = 'block';
    iconLoading.style.display = 'none';

    // Textarea'yı aktif et
    userInput.disabled = false;
    userInput.focus();

    // Status "Çevrimiçi" yap
    statusText.textContent = '● Çevrimiçi';
    statusText.classList.remove('thinking');

    // Avatar animasyonu kapat
    avatarThinking.classList.remove('active');
  }
}

/**
 * Textarea yüksekliğini içeriğe göre otomatik ayarlar.
 */
function autoResizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';

  // Gönder butonunu aktif/pasif yap
  btnSend.disabled = userInput.value.trim().length === 0 || isLoading;
}


/* ================================================================
   5. ANA İŞLEV: Mesaj Gönder
   ================================================================ */

/**
 * Kullanıcının mesajını gönderir ve Eva'nın cevabını alır.
 * Bu fonksiyon tüm süreci yönetir:
 *   1. Input'u al ve temizle
 *   2. Kullanıcı mesajını ekle
 *   3. Yazma göstergesi göster
 *   4. API'ye gönder
 *   5. Eva'nın cevabını göster
 *   6. Geçmişi güncelle
 */
async function handleSend() {
  const text = userInput.value.trim();
  if (!text || isLoading) return;

  // Input'u temizle
  userInput.value = '';
  autoResizeTextarea();

  // 1. Kullanıcı mesajını ekle
  addMessage(text, 'user');

  // 3. Yükleme başlat + yazma göstergesi
  setLoading(true);
  addTypingIndicator();

  try {
    // 4. Eva'ya gönder
    const evaResponse = await sendMessageToEva(text);

    // 5. Yazma göstergesi kaldır, cevabı ekle
    removeTypingIndicator();
    addMessage(evaResponse, 'eva');

    // 6. Geçmişe ekle (Kullanıcı mesajını ve Eva'nın cevabını aynı anda ekle ki API'ye çift gitmesin)
    conversationHistory.push({ role: 'user', content: text });
    conversationHistory.push({ role: 'assistant', content: evaResponse });

    // Geçmişi 20 mesajla sınırla (bellek tasarrufu)
    if (conversationHistory.length > 20) {
      conversationHistory = conversationHistory.slice(-20);
    }

  } catch (error) {
    console.error('Frontend/Backend Hatası:', error);
    removeTypingIndicator();
    // Kullanıcıya karmaşık backend detayları yerine jenerik bir mesaj ver, hata detayını gizle
    addMessage(`⚠️ Bağlantı veya sunucu hatası oluştu. (Detaylar için F12 Konsoluna bakınız)`, 'eva', true);
  } finally {
    setLoading(false);
  }
}


/* ================================================================
   6. OLAY DİNLEYİCİLERİ (Event Listeners)
   ================================================================ */

// Gönder butonu
btnSend.addEventListener('click', handleSend);

// Enter = gönder, Shift+Enter = yeni satır
userInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();  // Varsayılan yeni satır davranışını engelle
    handleSend();
  }
});

// Yazarken otomatik yükseklik + buton durumu
userInput.addEventListener('input', autoResizeTextarea);

// Sohbeti temizle
btnClear.addEventListener('click', () => {
  // Sohbet penceresini temizle
  chatWindow.innerHTML = '';

  // Geçmişi sıfırla
  conversationHistory = [];

  // Hoşgeldin mesajı tekrar göster
  addMessage('Yeni bir konuşmaya başlayalım! Sana nasıl yardımcı olabilirim?', 'eva');
});


/* ================================================================
   7. BAŞL ANGIÇ
   ================================================================ */

/**
 * Giriş yoksa login sayfasına at.
 * Varsa kullanıcı adını göster ve Eva'yı başlat.
 */
async function init() {
  const token = getToken();
  const username = getUsername();

  // Token yoksa login'e yönlendir
  if (!token) {
    window.location.href = '/';
    return;
  }

  // Kullanıcı adını header'a yaz
  if (headerUsername) headerUsername.textContent = username || 'Kullanıcı';

  // Hoşgeldin mesajı
  addMessage(
    `Merhaba ${username}! Ben Eva. Sana karşı dürüst, bazen sert ama her zaman gerçekçi bir dostun olmaya çalışacağım. Ne konuşmak istersin?`,
    'eva'
  );

  // Backend sağlık kontrolü
  const isHealthy = await checkBackendHealth();
  if (!isHealthy) {
    addMessage(
      '⚠️ Backend\'e bağlamamıyorum. Backend\'in çalıştığından emin ol.',
      'eva',
      true
    );
  }

  userInput.focus();
}

// Çıkış fonksiyonu
function logout() {
  clearSession();
  window.location.href = '/';
}

// Çıkış butonu
if (btnLogout) {
  btnLogout.addEventListener('click', () => {
    if (confirm('Oturumu kapatıp çıkmak istiyor musun?')) logout();
  });
}

// Sayfa yüklenince başlat
init();
