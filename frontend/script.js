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
    conversation_id: activeConversationId   // Hangi sohbete ait olduğu (null ise yeni açılır)
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
