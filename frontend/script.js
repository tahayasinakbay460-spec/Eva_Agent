/**
 * script.js — Eva AI Frontend Mantığı (Faz 4)
 * ===============================================
 * Faz 3: Sol panel (sidebar) sohbet geçmişi
 * Faz 4: STT (Sesli yazıma) + TTS (Eva sesli konuşur)
 */


/* ================================================================
   1. AYARLAR & GLOBAL DEĞİŞKENLER
   ================================================================ */

const API_BASE = 'http://localhost:8000/api';

// Oturum yönetimi
function getToken()    { return localStorage.getItem('eva_token'); }
function getUsername() { return localStorage.getItem('eva_username'); }
function clearSession() {
  localStorage.removeItem('eva_token');
  localStorage.removeItem('eva_user_id');
  localStorage.removeItem('eva_username');
}

// Oturum içi durum
let conversationHistory = [];   // Aktif sohbetin mesaj dizisi (LLM context için)
let activeConversationId = null; // Şu an açık olan sohbetin MySQL ID'si
let isLoading = false;

// HTML elementleri
const chatWindow     = document.getElementById('chat-window');
const userInput      = document.getElementById('user-input');
const btnSend        = document.getElementById('btn-send');
const btnClear       = document.getElementById('btn-clear');
const btnNewChat     = document.getElementById('btn-new-chat');
const btnLogout      = document.getElementById('btn-logout');
const btnHamburger   = document.getElementById('btn-hamburger');
const btnMic         = document.getElementById('btn-mic');         // Faz 4
const btnTtsToggle   = document.getElementById('btn-tts-toggle');  // Faz 4
const statusText     = document.getElementById('status-text');
const avatarThinking = document.getElementById('avatar-thinking');
const iconSend       = document.getElementById('icon-send');
const iconLoading    = document.getElementById('icon-loading');
const sidebarEl      = document.getElementById('sidebar');
const overlayEl      = document.getElementById('sidebar-overlay');
const convListEl     = document.getElementById('conversation-list');
const convLoadingEl  = document.getElementById('conv-loading');
const sidebarUsernameEl = document.getElementById('sidebar-username');


/* ================================================================
   2. API İLETİŞİMİ
   ================================================================ */

/** Eva'ya mesaj gönderir ve cevabı döndürür. */
async function sendMessageToEva(message) {
  const token = getToken();
  if (!token) { logout(); return ''; }

  const requestBody = {
    message: message,
    history: conversationHistory,
    conversation_id: activeConversationId,   // Hangi sohbete ait olduğu (null ise yeni açılır)
    detected_emotion: cameraActive ? currentEmotion : null  // Faz 5: Kameradan gelen duygu
  };

  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(requestBody)
  });

  if (response.status === 401 || response.status === 403) {
    clearSession();
    window.location.href = '/';
    return '';
  }

  const data = await response.json();

  if (!response.ok) {
    console.error('Backend Hatası:', data.detail || data);
    throw new Error(data.detail || 'Sunucu hatası');
  }

  // Backend yeni bir sohbet açtıysa ID'yi kaydet ve paneli güncelle
  if (data.conversation_id && data.conversation_id !== activeConversationId) {
    activeConversationId = data.conversation_id;
    await fetchConversations();   // Yeni sohbet başlığını sol panele ekle
  }

  return data.response;
}

/** Kullanıcının tüm eski sohbetlerini çeker ve sol paneli doldurur. */
async function fetchConversations() {
  const token = getToken();
  if (!token) return;

  try {
    const response = await fetch(`${API_BASE}/history/conversations`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (!response.ok) return;

    const conversations = await response.json();
    renderConversationList(conversations);

  } catch (err) {
    console.error('Sohbet geçmişi yüklenemedi:', err);
  }
}

/** Tıklanan eski sohbetin mesajlarını yükler ve ekrana basar. */
async function loadConversation(convId) {
  const token = getToken();
  if (!token) return;

  try {
    const response = await fetch(`${API_BASE}/history/conversations/${convId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (!response.ok) return;

    const conv = await response.json();

    // Ekranı temizle ve eski mesajları bas
    chatWindow.innerHTML = '';
    conversationHistory = [];
    activeConversationId = convId;

    if (conv.messages.length === 0) {
      addMessage('Bu sohbet boş.', 'eva');
      return;
    }

    for (const msg of conv.messages) {
      addMessage(msg.content, msg.role === 'assistant' ? 'eva' : 'user');
      conversationHistory.push({ role: msg.role, content: msg.content });
    }

    // Geçmiş 20 mesajla sınırla (LLM context optimizasyonu)
    if (conversationHistory.length > 20) {
      conversationHistory = conversationHistory.slice(-20);
    }

    // Aktif sohbeti panelde işaretle
    updateActiveConvInList(convId);

    // Mobilde paneli kapat
    closeSidebar();

  } catch (err) {
    console.error('Sohbet yüklenemedi:', err);
  }
}

/** Bir sohbeti siler. */
async function deleteConversation(convId, event) {
  event.stopPropagation();  // Satıra tıklamayı engelle

  if (!confirm('Bu sohbeti silmek istediğine emin misin?')) return;

  const token = getToken();
  if (!token) return;

  try {
    await fetch(`${API_BASE}/history/conversations/${convId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });

    // Silinen sohbet aktifse ekranı sıfırla
    if (activeConversationId === convId) {
      startNewChat();
    }

    await fetchConversations();

  } catch (err) {
    console.error('Sohbet silinemedi:', err);
  }
}

/** Backend sağlık kontrolü */
async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    return response.ok;
  } catch {
    return false;
  }
}


/* ================================================================
   3. SIDEBAR UI İŞLEMLERİ
   ================================================================ */

/** Sohbet listesini sol panele render eder. */
function renderConversationList(conversations) {
  convListEl.innerHTML = '';

  if (conversations.length === 0) {
    convListEl.innerHTML = `
      <div class="conv-empty">
        Henüz hiç sohbet yok.<br/>
        Yukarıdaki butona tıklayarak<br/>yeni bir sohbet başlat!
      </div>`;
    return;
  }

  for (const conv of conversations) {
    const item = document.createElement('div');
    item.className = `conv-item${conv.id === activeConversationId ? ' active' : ''}`;
    item.dataset.id = conv.id;
    item.innerHTML = `
      <span class="conv-icon">💬</span>
      <span class="conv-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</span>
      <button class="conv-delete" title="Sil">✕</button>
    `;

    item.addEventListener('click', () => loadConversation(conv.id));
    item.querySelector('.conv-delete').addEventListener('click', (e) => deleteConversation(conv.id, e));

    convListEl.appendChild(item);
  }
}

/** Paneldeki aktif sohbet stilini günceller. */
function updateActiveConvInList(convId) {
  document.querySelectorAll('.conv-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.id) === convId);
  });
}

/** Yeni sohbet başlatır — ekranı temizler, ID sıfırlar. */
function startNewChat() {
  chatWindow.innerHTML = '';
  conversationHistory = [];
  activeConversationId = null;

  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));

  const username = getUsername();
  addMessage(
    `Merhaba ${username}! Ben Eva. Yeni bir sohbet başlatalım, ne konuşmak istersin?`,
    'eva'
  );

  closeSidebar();
  userInput.focus();
}

/** Mobil sidebar açma/kapama */
function openSidebar() {
  sidebarEl.classList.add('open');
  overlayEl.classList.add('active');
}

function closeSidebar() {
  sidebarEl.classList.remove('open');
  overlayEl.classList.remove('active');
}

/** HTML escape (XSS koruması) */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}


/* ================================================================
   4. MESAJ EKLEME (DOM İşlemleri)
   ================================================================ */

function getCurrentTime() {
  return new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Sohbet penceresine yeni bir mesaj ekler.
 * role: 'user' | 'eva'
 */
function addMessage(content, role, isError = false) {
  const isUser = role === 'user';

  const row = document.createElement('div');
  row.className = `message-row ${isUser ? 'user' : 'eva'}`;

  const avatar = document.createElement('div');
  avatar.className = `msg-avatar ${isUser ? 'user-avatar' : ''}`;
  avatar.textContent = isUser ? '👤' : '🤖';

  const contentWrapper = document.createElement('div');
  contentWrapper.className = 'message-content';

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.innerHTML = `
    <span class="message-sender">${isUser ? 'Sen' : 'Eva'}</span>
    <span class="message-time">${getCurrentTime()}</span>
  `;

  const bubble = document.createElement('div');
  bubble.className = `message-bubble ${isUser ? 'user' : 'eva'} ${isError ? 'error' : ''}`;

  if (isUser) {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = marked.parse(content);
    bubble.querySelectorAll('a').forEach(a => {
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    });
  }

  contentWrapper.appendChild(meta);
  contentWrapper.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(contentWrapper);
  chatWindow.appendChild(row);
  scrollToBottom();

  return bubble;
}

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

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function scrollToBottom() {
  setTimeout(() => { chatWindow.scrollTop = chatWindow.scrollHeight; }, 50);
}


/* ================================================================
   5. UI DURUM GÜNCELLEMELERİ
   ================================================================ */

function setLoading(loading) {
  isLoading = loading;

  if (loading) {
    btnSend.disabled = true;
    btnSend.classList.add('loading');
    iconSend.style.display = 'none';
    iconLoading.style.display = 'block';
    userInput.disabled = true;
    statusText.textContent = '● Düşünüyor...';
    statusText.classList.add('thinking');
    avatarThinking.classList.add('active');
  } else {
    btnSend.disabled = userInput.value.trim().length === 0;
    btnSend.classList.remove('loading');
    iconSend.style.display = 'block';
    iconLoading.style.display = 'none';
    userInput.disabled = false;
    userInput.focus();
    statusText.textContent = '● Çevrimiçi';
    statusText.classList.remove('thinking');
    avatarThinking.classList.remove('active');
  }
}

function autoResizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
  btnSend.disabled = userInput.value.trim().length === 0 || isLoading;
}


/* ================================================================
   6. ANA İŞLEV: Mesaj Gönder
   ================================================================ */

async function handleSend() {
  const text = userInput.value.trim();
  if (!text || isLoading) return;

  userInput.value = '';
  autoResizeTextarea();
  addMessage(text, 'user');
  setLoading(true);
  addTypingIndicator();

  try {
    const evaResponse = await sendMessageToEva(text);
    removeTypingIndicator();
    addMessage(evaResponse, 'eva');

    // Geçmişe ekle
    conversationHistory.push({ role: 'user', content: text });
    conversationHistory.push({ role: 'assistant', content: evaResponse });

    // 20 mesaj sınırı
    if (conversationHistory.length > 20) {
      conversationHistory = conversationHistory.slice(-20);
    }

    // Sol paneldeki sohbet başlığını yenile
    await fetchConversations();
    if (activeConversationId) updateActiveConvInList(activeConversationId);

    // Faz 4: Eva cevabını sesli oku
    speakText(evaResponse);

  } catch (error) {
    console.error('Hata:', error);
    removeTypingIndicator();
    addMessage('⚠️ Bağlantı veya sunucu hatası oluştu. (F12 Konsoluna bakınız)', 'eva', true);
  } finally {
    setLoading(false);
  }
}


/* ================================================================
   7. OLAY DİNLEYİCİLERİ
   ================================================================ */

// Gönder butonu
btnSend.addEventListener('click', handleSend);

// Enter = gönder, Shift+Enter = yeni satır
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

// Yazarken boyut ayarla
userInput.addEventListener('input', autoResizeTextarea);

// Yeni sohbet
btnNewChat.addEventListener('click', startNewChat);

// Sohbeti temizle (sadece ekran, DB'ye dokunmaz)
btnClear.addEventListener('click', () => {
  chatWindow.innerHTML = '';
  conversationHistory = [];
  addMessage('Ekran temizlendi. Sohbet geçmişin sol panelde duruyor.', 'eva');
});

// Çıkış
function logout() {
  clearSession();
  window.location.href = '/';
}

if (btnLogout) {
  btnLogout.addEventListener('click', () => {
    if (confirm('Oturumu kapatmak istediğine emin misin?')) logout();
  });
}

// Hamburger (mobil)
btnHamburger.addEventListener('click', openSidebar);
overlayEl.addEventListener('click', closeSidebar);


/* ================================================================
   FAZ 4: SES (STT + TTS)
   ================================================================ */

// ── TTS (Text-to-Speech) — Eva sesle konuşur ──────────────────
let ttsEnabled = true;   // Başlangıçta ses açık

/**
 * Eva'nın cevabını sesle okur.
 * Markdown işaretlerini temizler, düz metin olarak okur.
 */
function speakText(text) {
  if (!ttsEnabled) return;
  if (!window.speechSynthesis) return;  // Tarayıcı desteklemiyor

  // Önce varsa devam eden sesi durdur
  window.speechSynthesis.cancel();

  // Markdown işaretlerini temizle (* ** # ` vb.)
  const cleanText = text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/`{1,3}[^`]*`{1,3}/g, '')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/\n+/g, ' ')
    .trim();

  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang  = 'tr-TR';   // Türkçe
  utterance.rate  = 0.95;      // Biraz yavaş, daha doğal
  utterance.pitch = 1.05;      // Hafif yüksek, daha canlı

  // Türkçe ses varsa onu seç
  const voices = window.speechSynthesis.getVoices();
  const trVoice = voices.find(v => v.lang.startsWith('tr'));
  if (trVoice) utterance.voice = trVoice;

  window.speechSynthesis.speak(utterance);
}

// TTS Toggle butonu
if (btnTtsToggle) {
  btnTtsToggle.addEventListener('click', () => {
    ttsEnabled = !ttsEnabled;
    window.speechSynthesis.cancel();  // Çalan sesi durdur

    if (ttsEnabled) {
      btnTtsToggle.textContent = '🔊 Ses';
      btnTtsToggle.classList.remove('muted');
      btnTtsToggle.title = "Eva'nın sesini kapat";
    } else {
      btnTtsToggle.textContent = '🔇 Ses';
      btnTtsToggle.classList.add('muted');
      btnTtsToggle.title = "Eva'nın sesini aç";
    }
  });
}

// ── STT (Speech-to-Text) — Kullanıcı sesle yazar ───────────────
let isRecording = false;
let recognition = null;

// Web Speech API tarayıcı desteği kontrolü
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition && btnMic) {
  recognition = new SpeechRecognition();
  recognition.lang = 'tr-TR';         // Türkçe
  recognition.continuous = false;     // Tek cümle dinle
  recognition.interimResults = false; // Ara sonuç gösterme

  // Ses tanıma başardığında metin input'a gelir ve direkt gönderilir
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    userInput.value = transcript;
    autoResizeTextarea();
    // Kısa bir bekleme sonrası otomatik gönder
    setTimeout(() => handleSend(), 300);
  };

  recognition.onerror = (event) => {
    console.error('Ses tanıma hatası:', event.error);
    stopRecording();
    if (event.error === 'not-allowed') {
      addMessage('⚠️ Mikrofon izni verilmedi. Tarayıcı ayarlarından mikrofon iznini aç.', 'eva', true);
    }
  };

  recognition.onend = () => stopRecording();

  // Mikrofon butonu tıklaması
  btnMic.addEventListener('click', () => {
    if (isRecording) {
      recognition.stop();
    } else {
      startRecording();
    }
  });

} else if (btnMic) {
  // Tarayıcı desteklemiyor
  btnMic.disabled = true;
  btnMic.title = 'Tarayıcınız STT desteklemiyor (Chrome/Edge kullanın)';
  btnMic.style.opacity = '0.3';
}

function startRecording() {
  if (!recognition || isLoading) return;
  isRecording = true;
  btnMic.classList.add('recording');
  userInput.placeholder = 'Dinliyorum... (konuşmayı bitirince otomatik gider)';
  recognition.start();
}

function stopRecording() {
  isRecording = false;
  if (btnMic) btnMic.classList.remove('recording');
  userInput.placeholder = "Eva'ya bir şey yaz... (Enter gönder, Shift+Enter yeni satır)";
}


/* ================================================================
   FAZ 5: KAMERA & DUYGU ALGILAMA SİSTEMİ
   ================================================================
   📚 Öğretici Not — Genel Akış:
       1. Kullanıcı "📷 Kamera" butonuna tıklar
       2. Tarayıcıdan kamera izni istenir (getUserMedia)
       3. İzin verilirse: WebSocket bağlantısı kurulur (JWT doğrulamalı)
       4. Her 3 saniyede bir video frame'i canvas'a çizilir → base64 JPEG
       5. Frame WebSocket üzerinden backend'e gönderilir
       6. Backend duygu analizi yapıp etiketi geri gönderir
       7. currentEmotion değişkeni güncellenir (Faz 5.4'te LLM'e gidecek)
   ================================================================ */

// HTML elementleri (Faz 5)
const btnCameraToggle = document.getElementById('btn-camera-toggle');
const cameraVideo     = document.getElementById('camera-video');
const cameraCanvas    = document.getElementById('camera-canvas');

// Durum değişkenleri
let cameraActive   = false;     // Kamera modu açık/kapalı
let cameraStream   = null;      // MediaStream referansı (kamera akışı)
let emotionSocket  = null;      // WebSocket bağlantısı
let frameInterval  = null;      // setInterval referansı (3 sn'de bir frame)
let currentEmotion = 'neutral'; // Backend'den gelen son duygu etiketi
let wsReconnectAttempts = 0;    // Yeniden bağlanma deneme sayısı
const WS_MAX_RECONNECTS = 3;   // Maksimum yeniden bağlanma denemesi
const FRAME_INTERVAL_MS = 3000; // Frame gönderim aralığı (3 saniye)
const FRAME_QUALITY     = 0.5;  // JPEG sıkıştırma kalitesi (0-1)
const FRAME_WIDTH        = 320; // Yakalanan frame genişliği
const FRAME_HEIGHT       = 240; // Yakalanan frame yüksekliği


/**
 * Kamera modunu açar/kapatır.
 * Buton her tıklandığında çağrılır.
 */
function toggleCamera() {
  if (cameraActive) {
    stopCamera();
  } else {
    startCamera();
  }
}


/**
 * Kamera modunu başlatır.
 *
 * 📚 navigator.mediaDevices.getUserMedia():
 *     Tarayıcıdan kamera/mikrofon izni ister.
 *     İzin verilirse MediaStream döner (video akışı).
 *     İzin reddedilirse DOMException fırlatır.
 *
 *     facingMode: 'user' → Ön kamerayı seç (selfie modu)
 *     width/height → Düşük çözünürlük (CV analizi için yeterli, bandwidth dostu)
 */
async function startCamera() {
  // Tarayıcı desteği kontrolü
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMessage('⚠️ Tarayıcın kamera erişimini desteklemiyor. Chrome veya Edge kullan.', 'eva', true);
    flashCameraError();
    return;
  }

  try {
    // Kamera izni iste
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width:  { ideal: FRAME_WIDTH },
        height: { ideal: FRAME_HEIGHT },
        facingMode: 'user'   // Ön kamera
      },
      audio: false  // Ses gerekmez
    });

    // İzin verildi — stream'i sakla ve video'ya bağla
    cameraStream = stream;
    cameraVideo.srcObject = stream;

    // Canvas boyutlarını ayarla
    cameraCanvas.width  = FRAME_WIDTH;
    cameraCanvas.height = FRAME_HEIGHT;

    // UI güncelle
    cameraActive = true;
    btnCameraToggle.classList.add('active');
    btnCameraToggle.classList.remove('error');
    btnCameraToggle.textContent = '🟢 Kamera';
    btnCameraToggle.title = 'Kamera modunu kapat';

    console.log('📷 Kamera açıldı — WebSocket bağlantısı kuruluyor...');

    // WebSocket bağlantısını kur
    wsReconnectAttempts = 0;
    connectEmotionSocket();

  } catch (error) {
    // İzin reddedildi veya başka bir hata
    console.error('Kamera hatası:', error);
    flashCameraError();

    if (error.name === 'NotAllowedError') {
      addMessage(
        '⚠️ Kamera izni reddedildi. Duygu algılama olmadan standart sohbet modunda devam ediliyor.',
        'eva', true
      );
    } else if (error.name === 'NotFoundError') {
      addMessage('⚠️ Kamera bulunamadı. Bilgisayarına bir kamera bağlı olduğundan emin ol.', 'eva', true);
    } else {
      addMessage(`⚠️ Kamera açılamadı: ${error.message}`, 'eva', true);
    }
  }
}


/**
 * Kamera modunu kapatır.
 * Stream'i durdurur, WebSocket'i kapatır, interval'i temizler.
 *
 * 📚 MediaStream.getTracks():
 *     Stream'deki tüm medya kanallarını (video, audio) döndürür.
 *     Her birini stop() ile durdurmak → kamera LED'ini söndürür.
 */
function stopCamera() {
  // 1. Frame gönderimini durdur
  if (frameInterval) {
    clearInterval(frameInterval);
    frameInterval = null;
  }

  // 2. WebSocket'i kapat
  if (emotionSocket) {
    emotionSocket.close(1000, 'Kullanıcı kamerayı kapattı');
    emotionSocket = null;
  }

  // 3. Kamera stream'ini durdur (LED söner)
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
  }

  // 4. Video elementini temizle
  cameraVideo.srcObject = null;

  // 5. UI güncelle
  cameraActive = false;
  currentEmotion = 'neutral';
  btnCameraToggle.classList.remove('active');
  btnCameraToggle.textContent = '📷 Kamera';
  btnCameraToggle.title = 'Kamera modunu aç';

  // 6. Avatarı orijinal haline döndür (Faz 5.5)
  resetAvatarEmotion();

  console.log('📷 Kamera kapatıldı');
}


/**
 * Duygu algılama WebSocket bağlantısı kurar.
 *
 * 📚 WebSocket URL'inde JWT:
 *     Normal HTTP: Authorization header ile gönderilir
 *     WebSocket:   Header gönderilmez, token query param olarak eklenir
 *     Güvenlik:    wss:// (TLS) production'da şart, localhost'ta ws:// yeterli
 *
 * Otomatik Yeniden Bağlanma:
 *     Bağlantı düşerse 3 kez dener (2, 4, 6 saniye aralarla)
 *     3 başarısız denemeden sonra kamerayı tamamen kapatır
 */
function connectEmotionSocket() {
  const token = getToken();
  if (!token) {
    console.error('Token bulunamadı — WS bağlantısı kurulamıyor');
    stopCamera();
    return;
  }

  // WebSocket URL'ini oluştur (localhost'ta ws://, production'da wss://)
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.hostname}:8000/ws/emotion?token=${token}`;

  console.log('🔌 Emotion WebSocket bağlanıyor...');

  emotionSocket = new WebSocket(wsUrl);

  // ── Bağlantı Kuruldu ──────────────────────────────────────
  emotionSocket.onopen = () => {
    console.log('✅ Emotion WebSocket bağlantısı kuruldu');
    wsReconnectAttempts = 0;  // Başarılı bağlantı — sayacı sıfırla

    // Frame gönderimini başlat
    startFrameCapture();
  };

  // ── Mesaj Alındı ──────────────────────────────────────────
  emotionSocket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === 'emotion') {
        // Duygu etiketini güncelle
        currentEmotion = data.emotion || 'neutral';
        console.log(`🎭 Duygu: ${currentEmotion} (güven: ${(data.confidence * 100).toFixed(0)}%)`);

        // Faz 5.5: Eva avatarını güncelle
        updateAvatarEmotion(currentEmotion, data.emotion_tr || 'nötr');

      } else if (data.type === 'error') {
        console.warn('Emotion WS hatası:', data.message);

      } else if (data.type === 'pong') {
        // Canlılık kontrolü yanıtı — loglama gerekli değil
      }

    } catch (err) {
      console.error('WS mesaj parse hatası:', err);
    }
  };

  // ── Bağlantı Kapandı ──────────────────────────────────────
  emotionSocket.onclose = (event) => {
    console.log(`🔌 Emotion WS kapandı (code: ${event.code}, reason: ${event.reason})`);

    // 4001 = Yetkisiz — yeniden bağlanma deneme
    if (event.code === 4001) {
      console.error('JWT doğrulaması başarısız — kamera kapatılıyor');
      addMessage('⚠️ Oturum doğrulaması başarısız. Kamera modu kapatıldı.', 'eva', true);
      stopCamera();
      return;
    }

    // Normal kapanış (kullanıcı kapattı) — yeniden bağlanma
    if (event.code === 1000) return;

    // Beklenmeyen kapanış — yeniden bağlan
    if (cameraActive && wsReconnectAttempts < WS_MAX_RECONNECTS) {
      wsReconnectAttempts++;
      const delay = wsReconnectAttempts * 2000;  // 2s, 4s, 6s
      console.log(`🔄 Yeniden bağlanma denemesi ${wsReconnectAttempts}/${WS_MAX_RECONNECTS} (${delay}ms sonra)`);
      setTimeout(() => {
        if (cameraActive) connectEmotionSocket();
      }, delay);
    } else if (wsReconnectAttempts >= WS_MAX_RECONNECTS) {
      console.error('Maksimum yeniden bağlanma denemesi aşıldı — kamera kapatılıyor');
      addMessage('⚠️ Sunucu bağlantısı kurulamadı. Kamera modu kapatıldı.', 'eva', true);
      stopCamera();
    }
  };

  // ── Bağlantı Hatası ───────────────────────────────────────
  emotionSocket.onerror = (error) => {
    console.error('Emotion WS hatası:', error);
    // onclose zaten tetiklenecek, burada ekstra işlem yok
  };
}


/**
 * Periyodik frame yakalama ve gönderimini başlatır.
 * Her FRAME_INTERVAL_MS (3 saniye) bir çalışır.
 *
 * 📚 Neden setInterval?
 *     requestAnimationFrame saniyede 60 kez çalışır — çok fazla
 *     Biz 3 saniyede 1 frame istiyoruz — setInterval daha uygun
 */
function startFrameCapture() {
  // Mevcut interval varsa temizle (çifte başlatma engeli)
  if (frameInterval) clearInterval(frameInterval);

  frameInterval = setInterval(() => {
    if (!cameraActive || !emotionSocket || emotionSocket.readyState !== WebSocket.OPEN) {
      return;  // Kamera kapalı veya WS bağlı değilse atla
    }

    const frameData = captureFrame();
    if (frameData) {
      emotionSocket.send(JSON.stringify({
        type: 'frame',
        data: frameData
      }));
    }
  }, FRAME_INTERVAL_MS);
}


/**
 * Tek bir video frame'i yakalar ve base64 JPEG olarak döndürür.
 *
 * 📚 Canvas Frame Yakalama:
 *     1. Canvas 2D context al
 *     2. Video'nun mevcut frame'ini canvas'a çiz (drawImage)
 *     3. Canvas'ı JPEG formatında base64 string'e çevir (toDataURL)
 *
 *     Neden JPEG?
 *     - PNG'den çok daha küçük dosya boyutu
 *     - quality: 0.5 → ~15-25KB/frame (bandwidth dostu)
 *     - Yüz ifadesi analizi için yeterli kalite
 */
function captureFrame() {
  if (!cameraVideo || !cameraVideo.srcObject) return null;

  // Video henüz yüklenmedi kontrolü
  if (cameraVideo.readyState < 2) return null;  // HAVE_CURRENT_DATA

  const ctx = cameraCanvas.getContext('2d');
  ctx.drawImage(cameraVideo, 0, 0, FRAME_WIDTH, FRAME_HEIGHT);

  // Canvas'ı base64 JPEG'e çevir
  return cameraCanvas.toDataURL('image/jpeg', FRAME_QUALITY);
}


/**
 * Kamera butonunda kırmızı hata animasyonu gösterir.
 * İzin reddedildiğinde veya hata oluştuğunda çağrılır.
 */
function flashCameraError() {
  btnCameraToggle.classList.add('error');
  setTimeout(() => {
    btnCameraToggle.classList.remove('error');
  }, 1500);
}


// ── Kamera Butonu Event Listener ─────────────────────────────
if (btnCameraToggle) {
  btnCameraToggle.addEventListener('click', toggleCamera);
}


/* ================================================================
   FAZ 5.5: AVATAR DUYGU ANİMASYONLARI
   ================================================================
   📚 Kameradan gelen duygu etiketine göre Eva'nın avatarı değişir.
       - Emoji: duyguya göre farklı emoji (😊, 😢, 😠, vb.)
       - Renk: avatar halkasının gradient rengi değişir
       - Tooltip: kullanıcı hover'da duygu durumunu görebilir
   ================================================================ */

// Duygu → Emoji eşlemesi
const EMOTION_EMOJIS = {
  happy:    '😊',
  sad:      '😢',
  angry:    '😠',
  surprise: '😲',
  fear:     '😰',
  disgust:  '😖',
  neutral:  '🤖'
};

// Duygu → Avatar halka rengi eşlemesi
const EMOTION_COLORS = {
  happy:    { from: '#22c55e', to: '#4ade80' },   // Yeşil
  sad:      { from: '#3b82f6', to: '#60a5fa' },   // Mavi
  angry:    { from: '#ef4444', to: '#f87171' },   // Kırmızı
  surprise: { from: '#f59e0b', to: '#fbbf24' },   // Sarı
  fear:     { from: '#8b5cf6', to: '#a78bfa' },   // Mor
  disgust:  { from: '#6b7280', to: '#9ca3af' },   // Gri
  neutral:  { from: '#7c3aed', to: '#a855f7' }    // Varsayılan mor (orijinal)
};

/**
 * Eva avatarını tespit edilen duyguya göre günceller.
 *
 * 📚 Güncellenen elementler:
 *     1. Avatar emoji → duyguya uygun emoji
 *     2. Avatar ring → duyguya uygun gradient renk
 *     3. Avatar title (tooltip) → "Eva — Kullanıcı şu an: mutlu"
 *
 * @param {string} emotion - İngilizce duygu etiketi (happy, sad, ...)
 * @param {string} emotionTr - Türkçe duygu etiketi (mutlu, üzgün, ...)
 */
function updateAvatarEmotion(emotion, emotionTr) {
  const avatarEmoji = document.querySelector('.avatar-emoji');
  const avatarRing  = document.querySelector('.avatar-ring');
  const avatarEl    = document.getElementById('eva-avatar');

  if (!avatarEmoji || !avatarRing) return;

  // 1. Emoji güncelle
  const newEmoji = EMOTION_EMOJIS[emotion] || EMOTION_EMOJIS.neutral;
  if (avatarEmoji.textContent !== newEmoji) {
    // Küçük bir scale animasyonu ile geçiş
    avatarEmoji.style.transition = 'transform 0.3s ease';
    avatarEmoji.style.transform = 'scale(0.5)';
    setTimeout(() => {
      avatarEmoji.textContent = newEmoji;
      avatarEmoji.style.transform = 'scale(1.2)';
      setTimeout(() => {
        avatarEmoji.style.transform = 'scale(1)';
      }, 150);
    }, 150);
  }

  // 2. Avatar halka rengi güncelle
  const colors = EMOTION_COLORS[emotion] || EMOTION_COLORS.neutral;
  avatarRing.style.background = `linear-gradient(135deg, ${colors.from}, ${colors.to})`;

  // 3. Tooltip güncelle
  if (avatarEl) {
    avatarEl.title = emotion !== 'neutral'
      ? `Eva — Kullanıcı şu an: ${emotionTr}`
      : 'Eva';
  }
}

/**
 * Kamera kapatıldığında avatarı orijinal haline döndürür.
 */
function resetAvatarEmotion() {
  const avatarEmoji = document.querySelector('.avatar-emoji');
  const avatarRing  = document.querySelector('.avatar-ring');
  const avatarEl    = document.getElementById('eva-avatar');

  if (avatarEmoji) avatarEmoji.textContent = '🤖';
  if (avatarRing) avatarRing.style.background = '';
  if (avatarEl) avatarEl.title = 'Eva';
}


/* ================================================================
   8. BAŞLANGIÇ
   ================================================================ */

async function init() {
  const token    = getToken();
  const username = getUsername();

  if (!token) {
    window.location.href = '/';
    return;
  }

  // Kullanıcı adlarını doldur
  if (sidebarUsernameEl) sidebarUsernameEl.textContent = username || 'Kullanıcı';

  // Hoşgeldin mesajı
  addMessage(
    `Merhaba ${username}! Ben Eva. Sana karşı dürüst, bazen sert ama her zaman gerçekçi bir dostun olmaya çalışacağım. Ne konuşmak istersin?`,
    'eva'
  );

  // Sol paneli doldur
  await fetchConversations();

  // Backend sağlık kontrolü
  const isHealthy = await checkBackendHealth();
  if (!isHealthy) {
    addMessage("⚠️ Backend'e bağlanamıyorum. Backend'in çalıştığından emin ol.", 'eva', true);
  }

  userInput.focus();
}

init();
