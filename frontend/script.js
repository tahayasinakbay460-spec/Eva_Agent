/**
 * script.js — Eva AI Frontend Mantığı (Faz 4)
 * ===============================================
 * Faz 3: Sol panel (sidebar) sohbet geçmişi
 * Faz 4: STT (Sesli yazıma) + TTS (Eva sesli konuşur)
 */


/* ================================================================
   1. AYARLAR & GLOBAL DEĞİŞKENLER
   ================================================================ */

// Göreli yol kullanılır — frontend'i backend sunduğu için her ortamda çalışır
// (localhost'a sabitlenirse başka bilgisayardan/sunucudan erişim bozulur)
const API_BASE = '/api';

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
const activeRequests = new Map();

function cancelGeneration(trackingId) {
  if (activeRequests.has(trackingId)) {
    const controller = activeRequests.get(trackingId);
    controller.abort();
    if (controller.uniqueId) {
      fetch(`${API_BASE}/chat/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracking_id: controller.uniqueId })
      }).catch(e => console.error('Cancel isteği hatası:', e));
    }
  }
}

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
async function sendMessageToEva(message, abortSignal = null, uniqueTrackingId = null) {
  const token = getToken();
  if (!token) { logout(); return ''; }

  const requestBody = {
    message: message,
    history: conversationHistory,
    conversation_id: activeConversationId,   // Hangi sohbete ait olduğu (null ise yeni açılır)
    detected_emotion: (typeof cameraActive !== 'undefined' && cameraActive) ? currentEmotion : null,
    tracking_id: uniqueTrackingId
  };

  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(requestBody)
  };
  if (abortSignal) options.signal = abortSignal;

  const response = await fetch(`${API_BASE}/chat`, options);

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

  return data;
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

    if (typeof leaveLegacyChatMode === 'function') leaveLegacyChatMode();

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
    
    if (activeRequests.has(convId)) {
        addTypingIndicator();
    } else {
        removeTypingIndicator();
    }
    updateUIForTrackingId(convId);

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

/** Sohbet başlığını satır içinde yeniden adlandırır. */
function startRenameConversation(convId, event) {
  event.stopPropagation();

  const item = event.currentTarget.closest('.conv-item');
  const titleEl = item?.querySelector('.conv-title');
  if (!item || !titleEl || item.classList.contains('renaming')) return;

  const current = titleEl.textContent;
  item.classList.add('renaming');

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'conv-rename-input';
  input.value = current;
  input.maxLength = 200;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const next = input.value.trim();
    if (save && next && next !== current) {
      await saveConversationTitle(convId, next);
    }
    await fetchConversations();
  };

  input.addEventListener('click', (e) => e.stopPropagation());
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') {
      e.preventDefault();
      finish(true);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      finish(false);
    }
  });
  input.addEventListener('blur', () => finish(true));
}

async function saveConversationTitle(convId, title) {
  const token = getToken();
  if (!token) return;

  try {
    const response = await fetch(`${API_BASE}/history/conversations/${convId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title })
    });
    if (!response.ok) {
      console.error('Sohbet yeniden adlandırılamadı');
    }
  } catch (err) {
    console.error('Sohbet yeniden adlandırılamadı:', err);
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
        Henüz sohbet yok.<br/>
        Yeni bir konuşma başlatın.
      </div>`;
    return;
  }

  for (const conv of conversations) {
    const item = document.createElement('div');
    item.className = `conv-item${conv.id === activeConversationId ? ' active' : ''}`;
    item.dataset.id = conv.id;
    item.innerHTML = `
      <span class="conv-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</span>
      <div class="conv-actions">
        <button class="conv-action conv-rename" title="Yeniden adlandır" aria-label="Yeniden adlandır">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"></path>
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
          </svg>
        </button>
        <button class="conv-action conv-delete" title="Sil" aria-label="Sil">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
            <path d="M10 11v6"></path>
            <path d="M14 11v6"></path>
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>
          </svg>
        </button>
      </div>
    `;

    item.addEventListener('click', () => loadConversation(conv.id));
    item.querySelector('.conv-rename').addEventListener('click', (e) => startRenameConversation(conv.id, e));
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
  if (typeof leaveLegacyChatMode === 'function') leaveLegacyChatMode();

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
  if (activeRequests.has('new')) {
     addTypingIndicator();
  } else {
     removeTypingIndicator();
  }
  updateUIForTrackingId(null);
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
  
  // Faz 8: Miras sohbet modunda Eva mesajları karakterin kimliğiyle görünür
  const isLegacyMsg = !isUser
    && typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode;

  const row = document.createElement('div');
  row.className = `message-row ${isUser ? 'user' : 'eva'}`;

  const avatar = document.createElement('div');
  avatar.className = `msg-avatar ${isUser ? 'user-avatar' : ''}`;
  if (isLegacyMsg && typeof activeLegacyAncestorPhoto !== 'undefined' && activeLegacyAncestorPhoto) {
    avatar.innerHTML = `<img src="${activeLegacyAncestorPhoto}" alt="" />`;
  } else if (isUser) {
    const initial = (getUsername() || 'S').charAt(0).toUpperCase();
    avatar.textContent = initial;
  } else {
    avatar.textContent = isLegacyMsg ? '🏛️' : 'E';
  }

  const senderName = isUser
    ? 'Sen'
    : (isLegacyMsg && activeLegacyAncestorName ? activeLegacyAncestorName : 'Eva');

  const contentWrapper = document.createElement('div');
  contentWrapper.className = 'message-content';

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.innerHTML = `
    <span class="message-sender">${senderName}</span>
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
  if (typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode
      && typeof activeLegacyAncestorPhoto !== 'undefined' && activeLegacyAncestorPhoto) {
    avatar.innerHTML = `<img src="${activeLegacyAncestorPhoto}" alt="" />`;
  } else {
    avatar.textContent = (typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode) ? '🏛️' : 'E';
  }

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

function updateUIForTrackingId(convId) {
  const trackingId = convId || 'new';
  const isGenerating = activeRequests.has(trackingId);

  if (isGenerating) {
    btnSend.disabled = false; // İptal butonu için aktif bırak
    btnSend.classList.add('loading');
    iconSend.style.display = 'none';
    iconLoading.style.display = 'block';
    iconLoading.innerHTML = '<rect x="6" y="6" width="12" height="12" fill="currentColor"></rect>'; // Kare (Stop) ikonu
    userInput.disabled = true;
    statusText.textContent = '● Düşünüyor...';
    statusText.classList.add('thinking');
    avatarThinking.classList.add('active');
  } else {
    btnSend.disabled = userInput.value.trim().length === 0;
    btnSend.classList.remove('loading');
    iconSend.style.display = 'block';
    iconLoading.style.display = 'none';
    iconLoading.innerHTML = '<path d="M21 12a9 9 0 11-6.219-8.56" />'; // Yuvarlak dönen ikon
    userInput.disabled = false;
    if (document.activeElement !== userInput) userInput.focus();
    statusText.textContent = (typeof getLegacyStatusText === 'function')
      ? getLegacyStatusText()
      : '● Çevrimiçi';
    statusText.classList.remove('thinking');
    avatarThinking.classList.remove('active');
  }
}

function autoResizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
  const trackingId = activeConversationId || 'new';
  btnSend.disabled = userInput.value.trim().length === 0 || activeRequests.has(trackingId);
}


/* ================================================================
   6. ANA İŞLEV: Mesaj Gönder
   ================================================================ */

async function handleSend() {
  const text = userInput.value.trim();
  const trackingId = activeConversationId || 'new';
  if (!text || activeRequests.has(trackingId)) return;

  const shouldSpeak = !!window.isCallModeActive;

  userInput.value = '';
  autoResizeTextarea();
  addMessage(text, 'user');
  
  const uniqueTrackingId = crypto.randomUUID();
  const abortController = new AbortController();
  abortController.uniqueId = uniqueTrackingId;
  activeRequests.set(trackingId, abortController);
  updateUIForTrackingId(activeConversationId);
  addTypingIndicator();

  if (typeof update3DAvatarEmotion === 'function') {
    update3DAvatarEmotion((typeof currentEmotion !== 'undefined' ? currentEmotion : 'neutral'));
  }

  try {
    let evaResponse;
    
    if (typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode && typeof sendLegacyChatMessage === 'function') {
      evaResponse = await sendLegacyChatMessage(text, abortController.signal, uniqueTrackingId);
    } else {
      const data = await sendMessageToEva(text, abortController.signal, uniqueTrackingId);
      evaResponse = data.response;
      
      const isStillViewingThisChat = (activeConversationId || 'new') === trackingId;
      
      if (isStillViewingThisChat) {
          conversationHistory.push({ role: 'user', content: text });
          conversationHistory.push({ role: 'assistant', content: evaResponse });
          if (conversationHistory.length > 20) {
            conversationHistory = conversationHistory.slice(-20);
          }
      }
      
      if (data.conversation_id) {
         if (trackingId === 'new') {
            activeRequests.delete('new');
            activeRequests.set(data.conversation_id, abortController);
            if (isStillViewingThisChat) {
               activeConversationId = data.conversation_id;
            }
         }
         await fetchConversations();
         if (activeConversationId) updateActiveConvInList(activeConversationId);
      }
    }
    
    const isNowViewingThisChat = (activeConversationId || 'new') === (activeRequests.has(activeConversationId) ? activeConversationId : trackingId);
    
    if (isNowViewingThisChat) {
        removeTypingIndicator();
        addMessage(evaResponse, 'eva');

        if (shouldSpeak) {
          speakText(evaResponse);
        } else if (window.speechSynthesis) {
          window.speechSynthesis.cancel();
        }
    }

  } catch (error) {
    if (error.name === 'AbortError') {
       console.log('Sohbet iptal edildi: ' + trackingId);
       if ((activeConversationId || 'new') === trackingId) {
           removeTypingIndicator();
       }
    } else {
       console.error('Hata:', error);
       if ((activeConversationId || 'new') === trackingId) {
           removeTypingIndicator();
           addMessage('⚠️ SUNUCU (API) ÇÖKTÜ VEYA BAĞLANTI KOPTU', 'eva', true);
       }
    }
  } finally {
    for (const [key, val] of activeRequests.entries()) {
        if (val === abortController) {
            activeRequests.delete(key);
        }
    }
    updateUIForTrackingId(activeConversationId);
  }
}


/* ================================================================
   7. OLAY DİNLEYİCİLERİ
   ================================================================ */

// Gönder butonu
btnSend.addEventListener('click', () => {
  const trackingId = activeConversationId || 'new';
  if (activeRequests.has(trackingId)) {
     cancelGeneration(trackingId);
  } else {
     handleSend();
  }
});

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
  if (typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode) {
    legacyChatHistory = [];
    addMessage('Ekran temizlendi. Bu karakterle geçmişin sol panelde duruyor.', 'eva');
    return;
  }
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
let ttsEnabled = true;   // Ses butonu: sesli komutta cevabı kapatmak için

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

  // Faz 6: TTS Eventleri (Avatar animasyonu ve Ses Döngüsü için)
  utterance.onstart = () => {
    if (window.isCallModeActive) {
      if (typeof set3DAvatarState === 'function') set3DAvatarState('speaking');
    }
  };

  utterance.onend = () => {
    if (window.isCallModeActive) {
      if (typeof set3DAvatarState === 'function') set3DAvatarState('neutral');
      // Eva susunca tekrar dinlemeye geç (Continuous Voice Loop)
      startRecording();
    }
  };

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

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    userInput.value = transcript;
    autoResizeTextarea();

    // Faz 6: Çağrı modundaysa avatar 'thinking' durumuna geçer ve otomatik gönderilir
    if (window.isCallModeActive) {
      if (typeof set3DAvatarState === 'function') set3DAvatarState('thinking');
      document.getElementById('call-status-text').textContent = 'Eva Düşünüyor...';
      handleSend(); // Hemen gönder
    } else {
      // Chat modundaysa kısa bir bekleme sonrası otomatik gönder
      setTimeout(() => handleSend(), 300);
    }
  };

  recognition.onerror = (event) => {
    console.error('Ses tanıma hatası:', event.error);
    stopRecording();
    if (event.error === 'not-allowed') {
      addMessage('⚠️ Mikrofon izni verilmedi. Tarayıcı ayarlarından mikrofon iznini aç.', 'eva', true);
    }
    // Faz 6: Hata olursa döngüyü kırmamak için veya status güncellemek için
    if (window.isCallModeActive) {
      document.getElementById('call-status-text').textContent = 'Hata oluştu. Tekrar deneniyor...';
      setTimeout(startRecording, 2000);
    }
  };

  recognition.onend = () => {
    stopRecording();
    if (window.isCallModeActive && currentAvatarState !== 'thinking' && currentAvatarState !== 'speaking') {
      // Eğer kendi kendine kapanırsa ve Eva konuşmuyorsa, tekrar aç (Sürekli Dinleme)
      startRecording();
    }
  };

  // Mikrofon butonu tıklaması (Chat)
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
  if (!recognition || isRecording) return;
  isRecording = true;
  recognition.start();
  if (btnMic) btnMic.classList.add('recording');
  userInput.placeholder = 'Dinliyorum... (konuşmayı bitirince otomatik gider)';
  
  // Faz 6 Update
  if (window.isCallModeActive) {
    if (typeof set3DAvatarState === 'function') set3DAvatarState('listening');
    const statusText = document.getElementById('call-status-text');
    if (statusText) statusText.textContent = 'Dinliyor...';
  }
}

function stopRecording() {
  if (!recognition || !isRecording) return;
  isRecording = false;
  recognition.stop();
  if (btnMic) btnMic.classList.remove('recording');
  userInput.placeholder = "Bir şey yazın…";
  
  if (window.isCallModeActive && typeof set3DAvatarState === 'function' && currentAvatarState === 'listening') {
    set3DAvatarState('neutral');
  }
}


/* ================================================================
   FAZ 5 + 6.5: KAMERA & DUYGU ALGILAMA SİSTEMİ
   ================================================================
   📚 Öğretici Not — Genel Akış (Güncel: face-api.js, tarayıcı içi):
       1. Kullanıcı "📷 Kamera" butonuna tıklar
       2. Tarayıcıdan kamera izni istenir (getUserMedia)
       3. face-api.js modelleri yüklenir (bir kez, /static/models'ten)
       4. Algılama döngüsü video karesini doğrudan analiz eder
       5. currentEmotion güncellenir → mesajla birlikte LLM'e gider
       (Eski WebSocket + DeepFace backend akışı tamamen kaldırıldı)
   ================================================================ */

// HTML elementleri (Faz 5)
const btnCameraToggle = document.getElementById('btn-camera-toggle');
const cameraVideo     = document.getElementById('camera-video');

// Durum değişkenleri
let cameraActive   = false;     // Kamera modu açık/kapalı
let cameraStream   = null;      // MediaStream referansı (kamera akışı)
let currentEmotion = 'neutral'; // face-api.js'den gelen son duygu etiketi
const FRAME_WIDTH  = 320;       // Kamera çözünürlüğü (CV analizi için yeterli)
const FRAME_HEIGHT = 240;


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

    // PiP kamera önizlemesine de bağla (Call Mode köşe videosu)
    const pipVideo = document.getElementById('call-pip-video');
    if (pipVideo) pipVideo.srcObject = stream;

    // UI güncelle
    cameraActive = true;
    btnCameraToggle.classList.add('active');
    btnCameraToggle.classList.remove('error');
    btnCameraToggle.textContent = '🟢 Kamera';
    btnCameraToggle.title = 'Kamera modunu kapat';

    console.log('📷 Kamera açıldı — face-api.js duygu algılama başlıyor...');

    // Faz 6.5: face-api.js ile tarayıcı içi duygu algılama
    await startFaceApiDetection();

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
 */
function stopCamera() {
  // 1. face-api.js tespiti durdur
  stopFaceApiDetection();

  // 2. Kamera stream'ini durdur (LED söner)
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
  }

  // 3. Video elementini temizle
  cameraVideo.srcObject = null;

  // 4. UI güncelle
  cameraActive = false;
  currentEmotion = 'neutral';
  btnCameraToggle.classList.remove('active');
  btnCameraToggle.textContent = '📷 Kamera';
  btnCameraToggle.title = 'Kamera modunu aç';

  // 5. Avatarı orijinal haline döndür
  resetAvatarEmotion();

  console.log('📷 Kamera kapatıldı');
}


/* ================================================================
   FAZ 6.5: FACE-API.JS — TARAYICI İÇİ DUYGU ALGILAMA MOTORU
   ================================================================
   Eski yapı: Frontend → WebSocket → Backend (DeepFace) → WebSocket → Frontend
   Yeni yapı: Frontend (face-api.js) → Anında Sonuç
   
   Avantajlar:
   - Sıfır gecikme (0ms latency)
   - Backend yükü yok
   - DeepFace hatası yok
   - Saniyede 10+ kare işleyebilir
   ================================================================ */

let faceApiLoaded    = false; // Modeller bir kez yüklenir
let faceApiRunning   = false; // Döngü durumu
let faceApiOptions   = null;  // TinyFaceDetector ayarları (bir kez oluşturulur)

// 📚 PERFORMANS: Algılama sıklığı. 400ms = saniyede 2.5 analiz.
//    Duygu tespiti için fazlasıyla yeterli — eski 100ms (10 FPS) değeri
//    CPU'yu gereksiz yoruyordu ve tarayıcıyı yavaşlatıyordu.
const FACEAPI_LOOP_MS = 400;

// Turkce duygu isimleri (face-api etiketi → Turkce)
const FACEAPI_TR = {
  happy:    'mutlu',
  sad:      'üzgün',
  angry:    'kızgın',
  surprised: 'şaşkın',
  fearful:  'korkmuş',
  disgusted: 'iğrenmiş',
  neutral:  'nötr'
};

// 📚 PERFORMANS: Bu sabitler ve DOM referansları eskiden döngünün İÇİNDE
//    her karede yeniden oluşturuluyordu. Bir kez tanımlayıp tekrar kullanıyoruz.
const INDICATOR_EMOJIS = {
  happy: '😄', sad: '😢', angry: '😠',
  surprised: '😲', fearful: '😨', disgusted: '🤢', neutral: '😐'
};
const INDICATOR_COLORS = {
  happy: '#22c55e', sad: '#3b82f6', angry: '#ef4444',
  surprised: '#f59e0b', fearful: '#8b5cf6', disgusted: '#6b7280', neutral: '#7c3aed'
};
const emotionIndEl   = document.getElementById('emotion-indicator');
const emotionEmojiEl = document.getElementById('emotion-emoji');
const emotionLabelEl = document.getElementById('emotion-label');
const emotionBarEl   = document.getElementById('emotion-bar');

/**
 * face-api.js modellerini yükler (bir kez yapılır).
 * Modeller /static/models klasöründen alınır.
 */
async function loadFaceApiModels() {
  if (faceApiLoaded) return true; // Zaten yüklendi

  // Kütüphane henüz yüklenmemiş olabilir (defer ile geliyor)
  if (typeof faceapi === 'undefined') {
    console.error('❌ face-api.js henüz yüklenmedi. Birkaç saniye sonra tekrar deneyin.');
    return false;
  }

  try {
    console.log('🧠 face-api.js modelleri yükleniyor...');
    const MODEL_URL = '/static/models';
    
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
      faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL)
    ]);

    // Detektör ayarlarını bir kez oluştur (her karede yeniden oluşturmak israftı)
    // inputSize 224: küçük giriş boyutu = daha hızlı analiz (varsayılan 416'ya göre ~3x)
    faceApiOptions = new faceapi.TinyFaceDetectorOptions({
      inputSize: 224,
      scoreThreshold: 0.3
    });

    faceApiLoaded = true;
    console.log('✅ face-api.js modelleri hazır!');
    return true;
  } catch (err) {
    console.error('❌ face-api.js model yükleme hatası:', err);
    return false;
  }
}

/**
 * Duygu algılama döngüsünü başlatır.
 * Kamera açıldıktan sonra çağrılır.
 */
async function startFaceApiDetection() {
  const ok = await loadFaceApiModels();
  if (!ok) {
    console.error('Modeller yüklenemedi, duygu algılama başlamadı.');
    return;
  }

  faceApiRunning = true;
  console.log('🎭 Duygu algılama döngüsü başladı (face-api.js)');
  runFaceApiLoop();
}

/**
 * Ana algılama döngüsü.
 * setTimeout kullanıyoruz (FACEAPI_LOOP_MS aralıkla — CPU dostu).
 */
async function runFaceApiLoop() {
  if (!faceApiRunning || !cameraActive) return;

  // Video hazır mı kontrol et
  if (cameraVideo && cameraVideo.readyState === 4) {
    try {
      const detection = await faceapi
        .detectSingleFace(cameraVideo, faceApiOptions)
        .withFaceExpressions();

      if (detection && detection.expressions) {
        const expressions = detection.expressions;
        
        // En yüksek skorlu duyguyu bul
        const dominantEmotion = Object.keys(expressions).reduce(
          (a, b) => expressions[a] > expressions[b] ? a : b
        );
        const confidence = expressions[dominantEmotion];
        const emotionTr  = FACEAPI_TR[dominantEmotion] || 'nötr';

        // Duyguyu güncelle (hem 3D avatar hem chat mod)
        if (dominantEmotion !== currentEmotion) {
          currentEmotion = dominantEmotion;
          console.log(`🎭 face-api.js: ${dominantEmotion} (${(confidence * 100).toFixed(0)}%)`);
        }

        // ── Canlı Duygu Göstergesi Widgetı ──────────────────
        // (Sabitler ve DOM referansları modül seviyesinde tanımlı — bkz. yukarısı)
        if (emotionIndEl && emotionEmojiEl && emotionLabelEl && emotionBarEl) {
          emotionIndEl.classList.remove('hidden');
          emotionEmojiEl.textContent  = INDICATOR_EMOJIS[dominantEmotion] || '😐';
          emotionLabelEl.textContent  = emotionTr;
          emotionBarEl.style.width    = `${(confidence * 100).toFixed(0)}%`;
          emotionBarEl.style.background = INDICATOR_COLORS[dominantEmotion] || '#7c3aed';
        }

        // Chat avatarini güncelle
        // (3D avatar sadece mesaj gönderilince güncellenir — handleSend içinde)
        updateAvatarEmotion(dominantEmotion, emotionTr);

        // Call Mode status yazısı
        if (window.isCallModeActive) {
          const statusEl = document.getElementById('call-status-text');
          if (statusEl && currentAvatarState === 'listening') {
            statusEl.textContent = `Dinliyor... (🎭 ${emotionTr.toUpperCase()})`;
          }
        }
      }
    } catch (err) {
      // Sessiz hata — döngüyü kırma
    }
  }

  // Bir sonraki analiz turunu planla
  if (faceApiRunning) {
    setTimeout(runFaceApiLoop, FACEAPI_LOOP_MS);
  }
}

/**
 * Duygu algılama döngüsünü durdurur.
 */
function stopFaceApiDetection() {
  faceApiRunning = false;
  console.log('🎭 Duygu algılama durduruldu.');
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


// ── Kamera / Görüntülü Görüşme Butonu Event Listener ─────────────────────────────
if (btnCameraToggle) {
  btnCameraToggle.addEventListener('click', () => {
    // Faz 6: Kameraya tıklayınca doğrudan Call Mode açılsın.
    if (!window.isCallModeActive) {
      startCallMode();
    } else {
      endCallMode();
    }
  });
}


/* ================================================================
   FAZ 6: GÖRÜNTÜLÜ GÖRÜŞME (CALL MODE) MANTIĞI
   ================================================================ */
window.isCallModeActive = false;

function startCallMode() {
  window.isCallModeActive = true;
  
  // 1. Overlay'i Göster
  const overlay = document.getElementById('call-overlay');
  if (overlay) overlay.classList.remove('hidden');
  
  // 2. 3D Avatarı Başlat (Eğer henüz başlatılmadıysa)
  if (typeof init3DAvatar === 'function' && !window._3DAvatarInitialized) {
    init3DAvatar();
    window._3DAvatarInitialized = true;
  }
  
  // 3. TTS'i aç (Sesli Yanıt zorunlu)
  if (!ttsEnabled && btnTtsToggle) btnTtsToggle.click();
  
  // 4. Kamerayı Aç (Duygu analizi için)
  if (!cameraActive) toggleCamera();
  
  // 5. Mikrofonu Dinlemeye Başla
  startRecording();
}

function endCallMode() {
  window.isCallModeActive = false;
  
  // 1. Overlay'i Gizle
  const overlay = document.getElementById('call-overlay');
  if (overlay) overlay.classList.add('hidden');
  
  // 2. Kamerayı Kapat
  if (cameraActive) toggleCamera();
  
  // 3. Dinlemeyi Durdur
  stopRecording();
  
  // 4. Konuşan Sesi Durdur
  if (window.speechSynthesis) window.speechSynthesis.cancel();
}

// Call mode içi butonlar
const btnEndCall = document.getElementById('btn-end-call');
if (btnEndCall) {
  btnEndCall.addEventListener('click', endCallMode);
}

const btnCallMic = document.getElementById('btn-call-mic');
if (btnCallMic) {
  btnCallMic.addEventListener('click', () => {
    if (isRecording) {
      recognition.stop();
      btnCallMic.classList.remove('btn-mic-active');
      btnCallMic.classList.add('btn-mic-muted');
      document.getElementById('call-status-text').textContent = 'Sessizde';
    } else {
      startRecording();
      btnCallMic.classList.add('btn-mic-active');
      btnCallMic.classList.remove('btn-mic-muted');
    }
  });
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
// 📚 face-api.js "surprised/fearful/disgusted" etiketi kullanır — her iki
//    yazım da eklendi, yoksa bu duygular sessizce "nötr" görünüyordu.
const EMOTION_EMOJIS = {
  happy:     '😊',
  sad:       '😢',
  angry:     '😠',
  surprise:  '😲', surprised: '😲',
  fear:      '😰', fearful:   '😰',
  disgust:   '😖', disgusted: '😖',
  neutral:   '🤖'
};

// Duygu → Avatar halka rengi eşlemesi
const EMOTION_COLORS = {
  happy:    { from: '#22c55e', to: '#4ade80' },   // Yeşil
  sad:      { from: '#3b82f6', to: '#60a5fa' },   // Mavi
  angry:    { from: '#ef4444', to: '#f87171' },   // Kırmızı
  surprise: { from: '#f59e0b', to: '#fbbf24' },   // Sarı
  surprised:{ from: '#f59e0b', to: '#fbbf24' },
  fear:     { from: '#8b5cf6', to: '#a78bfa' },   // Mor
  fearful:  { from: '#8b5cf6', to: '#a78bfa' },
  disgust:  { from: '#6b7280', to: '#9ca3af' },   // Gri
  disgusted:{ from: '#6b7280', to: '#9ca3af' },
  neutral:  { from: '#C56A45', to: '#E07A50' }
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
  const avatarRing  = document.querySelector('.avatar-ring');
  const avatarEl    = document.getElementById('eva-avatar');
  if (!avatarRing) return;

  const colors = EMOTION_COLORS[emotion] || EMOTION_COLORS.neutral;
  avatarRing.style.background = `linear-gradient(135deg, ${colors.from}, ${colors.to})`;

  if (avatarEl) {
    avatarEl.title = emotion !== 'neutral'
      ? `Eva — ${emotionTr}`
      : 'Eva';
  }
}

/**
 * Kamera kapatıldığında avatarı orijinal haline döndürür.
 */
function resetAvatarEmotion() {
  const avatarRing  = document.querySelector('.avatar-ring');
  const avatarEl    = document.getElementById('eva-avatar');

  if (avatarRing) avatarRing.style.background = '';

  if (typeof isLegacyChatMode !== 'undefined' && isLegacyChatMode) {
    if (avatarEl) avatarEl.title = activeLegacyAncestorName || 'Karakter';
    return;
  }

  const avatarEmoji = document.querySelector('.avatar-emoji');
  if (avatarEmoji) avatarEmoji.textContent = 'E';
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
  const initialEl = document.getElementById('sidebar-user-initial');
  if (initialEl) initialEl.textContent = (username || 'A').charAt(0).toUpperCase();

  // Hoşgeldin mesajı
  addMessage(
    `Merhaba ${username}! Ben Eva. Sana karşı dürüst, bazen sert ama her zaman gerçekçi bir dostun olmaya çalışacağım. Ne konuşmak istersin?`,
    'eva'
  );

  // Sol paneli doldur
  await fetchConversations();
  if (typeof fetchSidebarCharacters === 'function') {
    await fetchSidebarCharacters();
  }

  // Backend sağlık kontrolü
  const isHealthy = await checkBackendHealth();
  if (!isHealthy) {
    addMessage("⚠️ Backend'e bağlanamıyorum. Backend'in çalıştığından emin ol.", 'eva', true);
  }

  userInput.focus();
}

init();
