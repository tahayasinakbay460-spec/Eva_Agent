/**
 * legacy.js — Dijital Miras Sistemi (v2 — Modern UI)
 * ====================================================
 * Tam sayfa modal tabanlı modern miras yönetim sistemi.
 * 4 Ana Panel: Karakterlerim, Karakter Oluştur, Miras Anahtarı Gir, Miras Oluştur
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════════
// GLOBAL DEĞİŞKENLER
// ══════════════════════════════════════════════════════════════════════════════

// Göreli yol kullanılır — frontend'i backend sunduğu için her ortamda çalışır
// (localhost'a sabitlenirse başka bilgisayardan/sunucudan erişim bozulur)
const LEGACY_API = '/api/legacy';

let activeLegacyAncestorId = null;
let activeLegacyAncestorName = null;
let activeLegacyAncestorPhoto = null;  // Sohbette avatar olarak gösterilir
let legacyChatHistory = [];
let isLegacyChatMode = false;

// ══════════════════════════════════════════════════════════════════════════════
// TOAST NOTIFICATION SİSTEMİ
// ══════════════════════════════════════════════════════════════════════════════

function showToast(message, type = 'info', duration = 3000) {
  const container = document.getElementById('toast-container') || createToastContainer();
  
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️'
  };
  
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close" onclick="this.parentElement.remove()">✕</button>
  `;
  
  container.appendChild(toast);
  
  // Animasyonla giriş
  requestAnimationFrame(() => toast.classList.add('toast-show'));
  
  // Otomatik kaldır
  setTimeout(() => {
    toast.classList.add('toast-hide');
    setTimeout(() => toast.remove(), 400);
  }, duration);
}

function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  document.body.appendChild(container);
  return container;
}

// ══════════════════════════════════════════════════════════════════════════════
// API YARDIMCI
// ══════════════════════════════════════════════════════════════════════════════

async function legacyFetch(endpoint, method = 'GET', body = null) {
  const token = localStorage.getItem('eva_token');
  if (!token) {
    showToast('Oturum süresi dolmuş. Lütfen tekrar giriş yapın.', 'error');
    window.location.href = '/';
    return null;
  }
  
  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  };
  
  if (body && method !== 'GET') {
    if (body instanceof FormData) {
      options.body = body;
    } else {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
  }
  
  try {
    const response = await fetch(`${LEGACY_API}${endpoint}`, options);
    
    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem('eva_token');
      window.location.href = '/';
      return null;
    }
    
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.detail || 'Bir hata oluştu');
    }
    
    return data;
    
  } catch (error) {
    console.error('Legacy API Hatası:', error);
    throw error;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL PANEL AÇ / KAPAT
// ══════════════════════════════════════════════════════════════════════════════

function toggleLegacyPanel() {
  const modal = document.getElementById('legacy-modal');
  if (!modal) return;
  
  const isOpen = modal.classList.contains('legacy-modal-open');
  
  if (isOpen) {
    closeLegacyModal();
  } else {
    openLegacyModal();
  }
}

function openLegacyModal() {
  const modal = document.getElementById('legacy-modal');
  if (!modal) return;
  
  modal.classList.add('legacy-modal-open');
  document.body.classList.add('legacy-modal-active');
  document.body.style.overflow = 'hidden';
  
  // Ana menüyü göster
  showLegacySection('legacy-home');
}

function closeLegacyModal() {
  const modal = document.getElementById('legacy-modal');
  if (!modal) return;
  
  modal.classList.remove('legacy-modal-open');
  document.body.classList.remove('legacy-modal-active');
  document.body.style.overflow = '';
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION NAVİGASYONU
// ══════════════════════════════════════════════════════════════════════════════

function showLegacySection(sectionId) {
  // Tüm sectionları gizle
  document.querySelectorAll('.legacy-section').forEach(s => s.classList.remove('active'));
  
  // İstenen sectionı göster
  const target = document.getElementById(sectionId);
  if (target) {
    target.classList.add('active');
    
    // Section'a özel yükleme
    if (sectionId === 'legacy-characters') {
      loadAncestors();
    } else if (sectionId === 'legacy-master-security') {
      loadMasterSecurity();
    }
  }
}

// Geri butonları için
function goToHome() {
  showLegacySection('legacy-home');
}

function goToCharacters() {
  showLegacySection('legacy-characters');
}

// ══════════════════════════════════════════════════════════════════════════════
// ANA MENÜ — 4 PANEL KARTI
// ══════════════════════════════════════════════════════════════════════════════
// HTML'de statik olarak tanımlanır, JS sadece navigasyon yapar.

// ══════════════════════════════════════════════════════════════════════════════
// KARAKTERLERİM — ATA LİSTELEME
// ══════════════════════════════════════════════════════════════════════════════

async function loadAncestors() {
  const listEl = document.getElementById('legacy-char-list');
  if (!listEl) return;
  
  listEl.innerHTML = `
    <div class="legacy-loader">
      <div class="legacy-loader-spinner"></div>
      <span>Karakterler yükleniyor...</span>
    </div>
  `;
  
  try {
    const ancestors = await legacyFetch('/ancestors');
    
    if (!ancestors || ancestors.length === 0) {
      listEl.innerHTML = `
        <div class="legacy-empty-state">
          <div class="legacy-empty-icon">🏛️</div>
          <h3>Henüz bir karakter oluşturmadınız</h3>
          <p>Sevdiklerinizi dijital dünyada ölümsüzleştirmek için yeni bir karakter oluşturun.</p>
          <button onclick="showCreateForm()" class="legacy-action-btn legacy-action-btn-primary">
            <span class="legacy-action-icon">✨</span>
            Karakter Oluştur
          </button>
        </div>
      `;
      return;
    }
    
    listEl.innerHTML = `
      <div class="legacy-char-grid">
        ${ancestors.map(ancestor => `
          <div class="legacy-char-card" data-id="${ancestor.id}">
            <div class="legacy-char-card-header">
              <div class="legacy-char-avatar">
                ${ancestor.photo_url 
                  ? `<img src="${ancestor.photo_url}" alt="${ancestor.full_name}" />`
                  : `<span class="legacy-char-avatar-letter">${ancestor.full_name.charAt(0).toUpperCase()}</span>`
                }
              </div>
              <div class="legacy-char-status ${ancestor.has_legacy_key ? 'has-key' : ''}">
                ${ancestor.has_legacy_key ? '🔑' : ''}
              </div>
            </div>
            <div class="legacy-char-card-body">
              <h3 class="legacy-char-name">
                ${ancestor.full_name}
                ${ancestor.is_legacy_import ? '<span title="Miras Alınan Karakter" style="font-size: 0.8em; margin-left: 5px;">👑</span>' : ''}
              </h3>
              <span class="legacy-char-relation">${ancestor.relation_type}</span>
              <div class="legacy-char-stats">
                <span class="legacy-char-stat">
                  <span class="stat-icon">📝</span>
                  ${ancestor.memory_count} anı
                </span>
              </div>
            </div>
            <div class="legacy-char-card-actions">
              <button onclick="openAncestorDetail(${ancestor.id})" class="legacy-char-btn" title="Detay & Yönet">
                <span>📋</span> Detay
              </button>
              <button onclick="startLegacyChat(${ancestor.id}, '${ancestor.full_name.replace(/'/g, "\\'")}')" class="legacy-char-btn legacy-char-btn-chat" title="Sohbet Et">
                <span>💬</span> Sohbet
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    
  } catch (error) {
    listEl.innerHTML = `<div class="legacy-error-state">❌ Hata: ${error.message}</div>`;
  } finally {
    if (typeof fetchSidebarCharacters === 'function') fetchSidebarCharacters();
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// KARAKTER OLUŞTUR
// ══════════════════════════════════════════════════════════════════════════════

function showCreateForm() {
  // Formu sıfırla — önceki düzenleme modundan kalan editId'yi de temizle
  const form = document.getElementById('legacy-create-form');
  if (form) {
    form.reset();
    delete form.dataset.editId;
  }
  const titleEl = document.querySelector('#legacy-create .legacy-section-title');
  if (titleEl) titleEl.textContent = '✨ Yeni Karakter Oluştur';
  
  showLegacySection('legacy-create');
}

async function saveNewAncestor() {
  const fullName = document.getElementById('legacy-name').value.trim();
  const relation_type = document.getElementById('legacy-relationship').value.trim();
  const birthYear = document.getElementById('legacy-birth-year').value.trim();
  const deathYear = document.getElementById('legacy-death-year').value.trim();
  const temperament = document.getElementById('legacy-temperament').value.trim();
  const backstory = document.getElementById('legacy-backstory').value.trim();
  
  if (!fullName || !relation_type) {
    showToast('İsim ve akrabalık alanları zorunludur.', 'warning');
    return;
  }
  
  const saveBtn = document.getElementById('legacy-save-btn');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<div class="btn-spinner"></div> Kaydediliyor...';
  }
  
  try {
    const formData = new FormData();
    formData.append('full_name', fullName);
    formData.append('relation_type', relation_type);
    if (birthYear) formData.append('birth_year', birthYear);
    if (deathYear) formData.append('death_year', deathYear);
    if (temperament) formData.append('temperament', temperament);
    if (backstory) formData.append('backstory', backstory);

    // Dosyalar
    const photoFile = document.getElementById('legacy-photo')?.files[0];
    const audioFile = document.getElementById('legacy-audio')?.files[0];
    const videoFile = document.getElementById('legacy-video')?.files[0];
    const pdfFile = document.getElementById('legacy-pdf')?.files[0];
    
    if (photoFile) formData.append('photo', photoFile);
    if (audioFile) formData.append('audio', audioFile);
    if (videoFile) formData.append('video', videoFile);
    if (pdfFile) formData.append('pdf', pdfFile);

    const editId = document.getElementById('legacy-create-form').dataset.editId;
    const method = editId ? 'PUT' : 'POST';
    const endpoint = editId ? `/ancestors/${editId}` : '/ancestors';

    await legacyFetch(endpoint, method, formData);
    
    showToast(`✨ "${fullName}" başarıyla ${editId ? 'güncellendi' : 'oluşturuldu'}!`, 'success');
    if (typeof fetchSidebarCharacters === 'function') fetchSidebarCharacters();
    
    // Formu sıfırla
    const form = document.getElementById('legacy-create-form');
    if (form) {
      form.reset();
      delete form.dataset.editId;
    }
    document.querySelector('#legacy-create .legacy-section-title').textContent = '✨ Yeni Karakter Oluştur';
    
    // Karakterlerim sayfasına geç
    showLegacySection('legacy-characters');
    
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<span class="btn-icon">💾</span> Kaydet';
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ATA DÜZENLEME
// ══════════════════════════════════════════════════════════════════════════════
// Not: deleteAncestor() aşağıda "ATA SİLME" bölümünde tanımlıdır (tek tanım).

async function editAncestor(id) {
  try {
    const ancestor = await legacyFetch(`/ancestors/${id}`);
    
    // Doldur
    document.getElementById('legacy-name').value = ancestor.full_name || '';
    document.getElementById('legacy-relationship').value = ancestor.relation_type || '';
    document.getElementById('legacy-birth-year').value = ancestor.birth_year || '';
    document.getElementById('legacy-death-year').value = ancestor.death_year || '';
    document.getElementById('legacy-temperament').value = ancestor.temperament || '';
    document.getElementById('legacy-backstory').value = ancestor.backstory || '';
    
    // Dosyalar için inputları temizle (kullanıcı yeni seçerse güncellenir)
    document.getElementById('legacy-photo').value = '';
    document.getElementById('legacy-audio').value = '';
    document.getElementById('legacy-video').value = '';
    document.getElementById('legacy-pdf').value = '';

    const form = document.getElementById('legacy-create-form');
    form.dataset.editId = id;
    
    document.querySelector('#legacy-create .legacy-section-title').textContent = '✏️ Karakteri Düzenle';
    
    showLegacySection('legacy-create');
  } catch (error) {
    showToast('Karakter bilgileri alınamadı: ' + error.message, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// ATA DETAY PANELİ
// ══════════════════════════════════════════════════════════════════════════════

async function openAncestorDetail(ancestorId) {
  showLegacySection('legacy-detail');
  
  const detailEl = document.getElementById('legacy-detail-content');
  if (!detailEl) return;
  
  detailEl.innerHTML = `
    <div class="legacy-loader">
      <div class="legacy-loader-spinner"></div>
      <span>Detaylar yükleniyor...</span>
    </div>
  `;
  
  try {
    const ancestor = await legacyFetch(`/ancestors/${ancestorId}`);
    const memories = await legacyFetch(`/ancestors/${ancestorId}/memories`);
    const keys = await legacyFetch(`/ancestors/${ancestorId}/key`);
    
    detailEl.innerHTML = `
      <!-- Profil Header -->
      <div class="legacy-profile-header">
        <div class="legacy-profile-avatar-wrap">
          <div class="legacy-profile-avatar">
            ${ancestor.photo_url 
              ? `<img src="${ancestor.photo_url}" alt="${ancestor.full_name}" />`
              : `<span class="legacy-profile-avatar-letter">${ancestor.full_name.charAt(0).toUpperCase()}</span>`
            }
          </div>
          <div class="legacy-profile-avatar-glow"></div>
        </div>
        <div class="legacy-profile-info">
          <h2 class="legacy-profile-name">${ancestor.full_name}</h2>
          <span class="legacy-profile-rel">${ancestor.relation_type}</span>
          ${ancestor.birth_year ? `
            <span class="legacy-profile-years">
              🎂 ${ancestor.birth_year}${ancestor.death_year ? ' — ✝ ' + ancestor.death_year : ' — Hayatta'}
            </span>
          ` : ''}
        </div>
        <div class="legacy-profile-actions">
          <button onclick="startLegacyChat(${ancestor.id}, '${ancestor.full_name.replace(/'/g, "\\'")}')" 
                  class="legacy-action-btn legacy-action-btn-primary">
            💬 Sohbet Et
          </button>
          <button onclick="editAncestor(${ancestor.id})" 
                  class="legacy-action-btn" title="Düzenle">
            ✏️ Düzenle
          </button>
          <button onclick="deleteAncestor(${ancestor.id}, '${ancestor.full_name.replace(/'/g, "\\'")}')" 
                  class="legacy-action-btn legacy-action-btn-danger">
            🗑️ Sil
          </button>
        </div>
      </div>
      
      <!-- Bilgi Tabları -->
      <!-- 🔑 İZİN MODELİ: Anahtar ve Switch sekmeleri, miras alınan karakterlerde
           SADECE orijinal sahibi "aktarılabilir" izni verdiyse görünür.
           İzin yoksa karakter tek kişiye özeldir, zincir devam ettirilemez. -->
      <div class="legacy-tabs">
        <button class="legacy-tab active" onclick="switchDetailTab(this, 'tab-info')">📖 Bilgiler</button>
        <button class="legacy-tab" onclick="switchDetailTab(this, 'tab-memories')">📝 Anılar (${memories.length})</button>
        ${(ancestor.is_legacy_import && ancestor.is_transferable) ? `
          <button class="legacy-tab" onclick="switchDetailTab(this, 'tab-keys')">🔑 Miras Anahtarı</button>
          <button class="legacy-tab" onclick="switchDetailTab(this, 'tab-switch')">⏰ Dead Man's Switch</button>
        ` : ''}
        ${(ancestor.is_legacy_import && !ancestor.is_transferable) ? `
          <span class="legacy-transfer-note" title="Orijinal sahibi aktarım izni vermemiş">🔒 Tek kişiye özel miras</span>
        ` : ''}
      </div>
      
      <!-- Tab İçerikleri -->
      <div class="legacy-tab-content active" id="tab-info">
        ${ancestor.temperament ? `
          <div class="legacy-info-card">
            <div class="legacy-info-card-icon">🎭</div>
            <div class="legacy-info-card-body">
              <h4>Mizaç Özellikleri</h4>
              <p>${ancestor.temperament}</p>
            </div>
          </div>
        ` : '<div class="legacy-info-empty">Mizaç bilgisi eklenmemiş.</div>'}
        
        ${ancestor.backstory ? `
          <div class="legacy-info-card">
            <div class="legacy-info-card-icon">📖</div>
            <div class="legacy-info-card-body">
              <h4>Hayat Hikayesi</h4>
              <p>${ancestor.backstory}</p>
            </div>
          </div>
        ` : '<div class="legacy-info-empty">Hayat hikayesi eklenmemiş.</div>'}
      </div>
      
      <div class="legacy-tab-content" id="tab-memories">
        <div class="legacy-section-toolbar">
          <button onclick="showAddMemoryForm(${ancestor.id})" class="legacy-action-btn legacy-action-btn-sm">
            ➕ Anı Ekle
          </button>
        </div>
        <div id="legacy-memories-list">
          ${memories.length === 0 
            ? '<div class="legacy-info-empty">Henüz anı eklenmemiş. Anı ekleyerek dijital mirası zenginleştirin.</div>'
            : memories.map(m => `
              <div class="legacy-memory-card">
                <div class="legacy-memory-card-left">
                  <span class="legacy-memory-type-badge">${m.memory_type}</span>
                </div>
                <div class="legacy-memory-card-body">
                  <h4>${m.title || 'Başlıksız Anı'}</h4>
                  <p>${m.content.substring(0, 200)}${m.content.length > 200 ? '...' : ''}</p>
                </div>
              </div>
            `).join('')
          }
        </div>
        
        <!-- Anı Ekleme Formu (gizli) -->
        <div id="legacy-add-memory-form" class="legacy-inline-form hidden" data-ancestor-id="${ancestor.id}">
          <h4>➕ Yeni Anı Ekle</h4>
          <input type="text" id="legacy-memory-title" class="legacy-modern-input" placeholder="Anının başlığı (opsiyonel)" />
          <textarea id="legacy-memory-content" class="legacy-modern-textarea" rows="4" 
                    placeholder="Anının içeriği... (en az 10 karakter)"></textarea>
          <div class="legacy-inline-form-actions">
            <button onclick="saveMemory(${ancestor.id})" class="legacy-action-btn legacy-action-btn-primary legacy-action-btn-sm">
              💾 Kaydet
            </button>
            <button onclick="document.getElementById('legacy-add-memory-form').classList.add('hidden')" 
                    class="legacy-action-btn legacy-action-btn-sm">İptal</button>
          </div>
        </div>
      </div>
      
      <div class="legacy-tab-content" id="tab-keys">
        ${keySecurityInfoHtml()}
        <div class="legacy-section-toolbar legacy-key-toolbar">
          ${keyValiditySelectHtml()}
          ${keyTransferSelectHtml()}
          <button onclick="generateLegacyKey(${ancestor.id})" class="legacy-action-btn legacy-action-btn-sm">
            🔑 Anahtar Üret
          </button>
        </div>
        <div id="legacy-keys-list">
          ${keys.length === 0 
            ? '<div class="legacy-info-empty">Henüz miras anahtarı üretilmemiş.</div>'
            : keys.map(k => renderKeyCard(k)).join('')
          }
        </div>
      </div>
      
      <div class="legacy-tab-content" id="tab-switch">
        <div class="legacy-info-card" style="margin-bottom: 20px;">
          <div class="legacy-info-card-icon">ℹ️</div>
          <div class="legacy-info-card-body">
            <h4>Dead Man's Switch Nedir?</h4>
            <p>Eğer belirlediğiniz süre boyunca (örneğin 6 ay) EVA sistemine giriş yapmazsanız, sistem otomatik olarak belirlediğiniz mirasçıya (heir) miras anahtarını gönderir. Böylece siz yokken bile mirasçınız bu anahtarı kullanarak sisteme girip, sizin dijital kopyanızla sohbet edebilir.</p>
          </div>
        </div>
        ${keys.length > 0 ? `
          <div class="legacy-section-toolbar">
            <button onclick="showDeadManForm(${ancestor.id}, ${keys[0].id})" class="legacy-action-btn legacy-action-btn-sm">
              ⏰ Switch Ayarla
            </button>
          </div>
        ` : ''}
        <div id="legacy-deadman-section">
          ${keys.length === 0 
            ? '<div class="legacy-info-empty">Önce bir miras anahtarı üretin, sonra Dead Man\'s Switch ayarlayabilirsiniz.</div>'
            : '<div class="legacy-loader"><div class="legacy-loader-spinner"></div><span>Yükleniyor...</span></div>'
          }
        </div>
        
        <!-- Dead Man's Switch Formu (gizli) -->
        <div id="legacy-deadman-form" class="legacy-inline-form hidden" data-ancestor-id="${ancestor.id}">
          <h4>⏰ Yeni Dead Man's Switch</h4>
          <input type="email" id="legacy-deadman-email" class="legacy-modern-input" placeholder="Bildirim e-posta adresi" />
          <input type="number" id="legacy-deadman-days" class="legacy-modern-input" value="180" min="30" max="3650" 
                 placeholder="Gün sayısı (30-3650)" />
          <p class="legacy-form-hint-text">Belirtilen süre boyunca sisteme giriş yapmazsanız, miras anahtarınız bu e-posta adresine gönderilecektir.</p>
          <div class="legacy-inline-form-actions">
            <button id="legacy-deadman-save-btn" class="legacy-action-btn legacy-action-btn-primary legacy-action-btn-sm">
              💾 Kaydet
            </button>
            <button onclick="document.getElementById('legacy-deadman-form').classList.add('hidden')" 
                    class="legacy-action-btn legacy-action-btn-sm">İptal</button>
          </div>
        </div>
      </div>
    `;
    
    // Dead Man's Switch'leri yükle
    if (keys.length > 0) {
      loadDeadManSwitches();
    }
    
  } catch (error) {
    detailEl.innerHTML = `<div class="legacy-error-state">❌ Hata: ${error.message}</div>`;
  }
}

// Tab değiştirme
function switchDetailTab(btn, tabId) {
  // Aktif tab butonunu değiştir
  document.querySelectorAll('.legacy-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  
  // Aktif içeriği değiştir
  document.querySelectorAll('.legacy-tab-content').forEach(c => c.classList.remove('active'));
  const target = document.getElementById(tabId);
  if (target) target.classList.add('active');
}

// ══════════════════════════════════════════════════════════════════════════════
// ANI YÖNETİMİ
// ══════════════════════════════════════════════════════════════════════════════

function showAddMemoryForm(ancestorId) {
  const form = document.getElementById('legacy-add-memory-form');
  if (form) {
    form.classList.remove('hidden');
    form.dataset.ancestorId = ancestorId;
    document.getElementById('legacy-memory-title').value = '';
    document.getElementById('legacy-memory-content').value = '';
  }
}

async function saveMemory(ancestorId) {
  const title = document.getElementById('legacy-memory-title').value.trim();
  const content = document.getElementById('legacy-memory-content').value.trim();
  
  if (!content || content.length < 10) {
    showToast('Anı içeriği en az 10 karakter olmalıdır.', 'warning');
    return;
  }
  
  try {
    await legacyFetch(`/ancestors/${ancestorId}/memories`, 'POST', {
      title: title || null,
      content: content,
      memory_type: 'text'
    });
    
    showToast('Anı başarıyla kaydedildi!', 'success');
    openAncestorDetail(ancestorId);
    
  } catch (error) {
    showToast('Anı kaydedilemedi: ' + error.message, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// MİRAS ANAHTARI
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Anahtarı maskeler: sadece son 4 karakteri gösterir.
 * Örn: "EVA-A1B2-C3D4-E5F6" → "EVA-••••-••••-E5F6"
 * Güvenlik: Ekrana bakan biri anahtarın tamamını göremez.
 */
function maskLegacyKey(key) {
  const parts = key.split('-');
  if (parts.length < 4) return '••••••••';
  return `${parts[0]}-••••-••••-${parts[3]}`;
}

/** Anahtar kartındaki 👁️ butonuyla göster/gizle yapar. */
function toggleKeyVisibility(btn) {
  const card = btn.closest('.legacy-key-card');
  const codeEl = card ? card.querySelector('.legacy-key-value') : null;
  if (!codeEl) return;
  
  const isMasked = codeEl.dataset.masked === '1';
  if (isMasked) {
    codeEl.textContent = codeEl.dataset.key;
    codeEl.dataset.masked = '0';
    btn.textContent = '🙈';
    btn.title = 'Gizle';
  } else {
    codeEl.textContent = maskLegacyKey(codeEl.dataset.key);
    codeEl.dataset.masked = '1';
    btn.textContent = '👁️';
    btn.title = 'Göster';
  }
}

/** Karttaki 📋 butonuyla tam anahtarı panoya kopyalar (maskeli olsa bile). */
function copyKeyFromCard(btn) {
  const card = btn.closest('.legacy-key-card');
  const codeEl = card ? card.querySelector('.legacy-key-value') : null;
  if (codeEl) copyToClipboard(codeEl.dataset.key);
}

/**
 * Tek bir anahtar kartının HTML'ini üretir (maskeli + süre bilgili).
 * Hem karakter detayında hem master güvenlik panelinde kullanılır.
 */
function renderKeyCard(k) {
  const expired = k.is_expired;
  const badgeClass = expired ? 'inactive' : (k.is_active ? 'active' : 'inactive');
  const badgeText = expired ? '⌛ Süresi Doldu' : (k.is_active ? '✅ Aktif' : '❌ Devre Dışı');
  const expiryText = k.expires_at
    ? `⏳ Son geçerlilik: ${new Date(k.expires_at).toLocaleDateString('tr-TR')}`
    : '♾️ Süresiz anahtar';
  const transferText = k.is_transferable
    ? '🔁 Nesiller arası aktarılabilir'
    : '🔒 Tek kişiye özel';
  
  return `
    <div class="legacy-key-card ${(!k.is_active || expired) ? 'inactive' : ''}">
      <div class="legacy-key-main">
        <code class="legacy-key-value" data-key="${k.key_hash}" data-masked="1">${maskLegacyKey(k.key_hash)}</code>
        <span class="legacy-key-expiry">${expiryText} &nbsp;·&nbsp; ${transferText}</span>
      </div>
      <div class="legacy-key-actions">
        <button onclick="toggleKeyVisibility(this)" class="legacy-icon-btn" title="Göster">👁️</button>
        <button onclick="copyKeyFromCard(this)" class="legacy-icon-btn" title="Kopyala">📋</button>
        <span class="legacy-key-badge ${badgeClass}">${badgeText}</span>
      </div>
    </div>
  `;
}

/** Anahtar üretirken geçerlilik süresi seçtiren dropdown HTML'i. */
function keyValiditySelectHtml() {
  return `
    <select id="legacy-key-validity" class="legacy-modern-input legacy-key-validity" title="Anahtar geçerlilik süresi">
      <option value="">♾️ Süresiz</option>
      <option value="30">30 gün geçerli</option>
      <option value="90">90 gün geçerli</option>
      <option value="180">180 gün geçerli</option>
      <option value="365" selected>1 yıl geçerli</option>
      <option value="1825">5 yıl geçerli</option>
    </select>
  `;
}

/**
 * İzin modeli: Anahtar üretirken aktarılabilirlik seçtiren dropdown.
 * 🔒 Tek kişiye özel → varis karakteri başkasına AKTARAMAZ (varsayılan, güvenli)
 * 🔁 Aktarılabilir  → varis de kendi anahtarını üretip zinciri sürdürebilir
 */
function keyTransferSelectHtml() {
  return `
    <select id="legacy-key-transferable" class="legacy-modern-input legacy-key-validity" title="Mirasçınız karakteri başkasına aktarabilsin mi?">
      <option value="0" selected>🔒 Tek kişiye özel</option>
      <option value="1">🔁 Nesiller arası aktarılabilir</option>
    </select>
  `;
}

/** Anahtar bölümlerinde gösterilen kısa güvenlik bilgilendirmesi. */
function keySecurityInfoHtml() {
  return `
    <div class="legacy-info-card legacy-key-security-info">
      <div class="legacy-info-card-icon">🔒</div>
      <div class="legacy-info-card-body">
        <h4>Anahtar Güvenliği</h4>
        <p>Miras anahtarınız <strong>şifre gibidir</strong> — sadece güvendiğiniz mirasçınızla paylaşın.
        Anahtarlar ekranda <strong>gizli</strong> gösterilir; görmek için 👁️ butonunu kullanın.
        <strong>Süreli anahtar</strong> üretmenizi öneririz: süresi dolan anahtar kendiliğinden geçersiz olur,
        yanlış ellere geçse bile kullanılamaz.
        <strong>Aktarılabilirlik</strong> sizin kararınız: "🔒 Tek kişiye özel" anahtarla giren mirasçı
        karakteri başkasına aktaramaz; "🔁 Aktarılabilir" seçerseniz mirasçınız da kendi anahtarını
        üretip mirası gelecek nesillere taşıyabilir.</p>
      </div>
    </div>
  `;
}

async function generateLegacyKey(ancestorId) {
  // Geçerlilik süresi seçilmişse oku (boş = süresiz)
  const validityEl = document.getElementById('legacy-key-validity');
  const validDays = (validityEl && validityEl.value) ? parseInt(validityEl.value) : null;
  
  // İzin modeli: aktarılabilirlik seçimi (varsayılan: tek kişiye özel)
  const transferEl = document.getElementById('legacy-key-transferable');
  const isTransferable = !!(transferEl && transferEl.value === '1');
  
  try {
    const result = await legacyFetch(`/ancestors/${ancestorId}/key`, 'POST', {
      valid_days: validDays,
      is_transferable: isTransferable
    });
    
    // Güvenlik: Anahtarın tamamını toast'ta GÖSTERMİYORUZ — panoya kopyalıyoruz.
    try {
      await navigator.clipboard.writeText(result.key_hash);
      showToast('🔑 Yeni miras anahtarı üretildi ve panoya kopyalandı!', 'success', 5000);
    } catch(e) {
      showToast('🔑 Yeni miras anahtarı üretildi! Listeden 📋 ile kopyalayabilirsiniz.', 'success', 5000);
    }
    
    // Sadece detay sayfası açıksa yenile — master panelden üretildiyse
    // görünüm detay sayfasına zıplamasın (orayı loadMasterSecurity yeniler)
    const detailSection = document.getElementById('legacy-detail');
    if (detailSection && detailSection.classList.contains('active')) {
      openAncestorDetail(ancestorId);
    }
    
  } catch (error) {
    showToast('Anahtar üretilemedi: ' + error.message, 'error');
  }
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Kopyalandı!', 'success', 2000);
  }).catch(err => {
    console.error('Kopyalama hatası:', err);
    prompt('Anahtarınız (kopyalayın):', text);
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// ATA SİLME
// ══════════════════════════════════════════════════════════════════════════════

async function deleteAncestor(ancestorId, name) {
  const confirmed = confirm(
    `⚠️ "${name}" profilini ve tüm anılarını, anahtarlarını silmek istediğinize emin misiniz?\n\nBu işlem geri alınamaz!`
  );
  
  if (!confirmed) return;
  
  try {
    await legacyFetch(`/ancestors/${ancestorId}`, 'DELETE');
    
    showToast(`"${name}" başarıyla silindi.`, 'success');
    if (activeLegacyAncestorId === ancestorId) {
      leaveLegacyChatMode();
      if (typeof startNewChat === 'function') startNewChat();
    }
    if (typeof fetchSidebarCharacters === 'function') fetchSidebarCharacters();
    showLegacySection('legacy-characters');
    
  } catch (error) {
    showToast('Silme hatası: ' + error.message, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// DEAD MAN'S SWITCH
// ══════════════════════════════════════════════════════════════════════════════

function showDeadManForm(ancestorId, keyId) {
  const form = document.getElementById('legacy-deadman-form');
  if (form) {
    form.classList.remove('hidden');
    form.dataset.ancestorId = ancestorId;
    form.dataset.keyId = keyId;
    
    const saveBtn = document.getElementById('legacy-deadman-save-btn');
    if (saveBtn) {
      saveBtn.onclick = () => saveDeadManSwitch(ancestorId, keyId);
    }
  }
}

async function saveDeadManSwitch(ancestorId, keyId) {
  const email = document.getElementById('legacy-deadman-email').value.trim();
  const days = parseInt(document.getElementById('legacy-deadman-days').value) || 180;
  
  if (!email) {
    showToast('E-posta adresi zorunludur.', 'warning');
    return;
  }
  
  try {
    await legacyFetch('/deadman', 'POST', {
      ancestor_id: ancestorId,
      legacy_key_id: keyId,
      notify_email: email,
      inactive_days: days
    });
    
    showToast(`⏰ Dead Man's Switch ayarlandı! ${days} gün boyunca giriş yapmazsanız, miras anahtarınız ${email} adresine gönderilecek.`, 'success', 5000);
    
    document.getElementById('legacy-deadman-form').classList.add('hidden');
    loadDeadManSwitches();
    
  } catch (error) {
    showToast('Switch ayarlanamadı: ' + error.message, 'error');
  }
}

async function loadDeadManSwitches() {
  const container = document.getElementById('legacy-deadman-section');
  if (!container) return;
  
  try {
    const switches = await legacyFetch('/deadman');
    
    if (!switches || switches.length === 0) {
      container.innerHTML = '<div class="legacy-info-empty">Henüz Dead Man\'s Switch ayarlanmamış.</div>';
      return;
    }
    
    container.innerHTML = switches.map(sw => `
      <div class="legacy-switch-card ${sw.triggered ? 'triggered' : ''}">
        <div class="legacy-switch-info">
          <strong>${sw.ancestor_name}</strong>
          <span>📧 ${sw.notify_email}</span>
          <span>⏱️ ${sw.inactive_days} gün</span>
        </div>
        <span class="legacy-switch-status ${sw.triggered ? 'triggered' : 'active'}">
          ${sw.triggered ? '🔴 Tetiklendi' : '🟢 Aktif'}
        </span>
      </div>
    `).join('');
    
  } catch (error) {
    container.innerHTML = `<div class="legacy-error-state">❌ Hata: ${error.message}</div>`;
  }
}

async function deadManCheckin() {
  try {
    const result = await legacyFetch('/deadman/checkin', 'POST');
    console.log('⏰ Check-in:', result.message);
  } catch (error) {
    console.error('Check-in hatası:', error);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// MİRAS ANAHTARI İLE GİRİŞ
// ══════════════════════════════════════════════════════════════════════════════

async function enterWithLegacyKey() {
  const keyInput = document.getElementById('legacy-key-input');
  if (!keyInput) return;
  
  const keyValue = keyInput.value.trim();
  if (!keyValue) {
    showToast('Lütfen bir miras anahtarı girin.', 'warning');
    return;
  }
  
  const enterBtn = document.getElementById('legacy-enter-btn');
  if (enterBtn) {
    enterBtn.disabled = true;
    enterBtn.innerHTML = '<div class="btn-spinner"></div> Doğrulanıyor...';
  }
  
  try {
    const result = await legacyFetch('/enter', 'POST', { legacy_key: keyValue }); // Fix key name based on API
    
    showToast(`🔑 ${result.ancestor_name} karakterlerinize eklendi!`, 'success');
    if (typeof fetchSidebarCharacters === 'function') fetchSidebarCharacters();
    
    // Karakterler listesine dön ve listeyi güncelle
    showLegacySection('legacy-characters');
    // Input'u temizle
    keyInput.value = '';
    
  } catch (error) {
    showToast('Geçersiz anahtar: ' + error.message, 'error');
  } finally {
    if (enterBtn) {
      enterBtn.disabled = false;
      enterBtn.innerHTML = '<span class="btn-icon">🔓</span> Giriş Yap';
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// SOL PANEL — KARAKTER LİSTESİ
// ══════════════════════════════════════════════════════════════════════════════

async function fetchSidebarCharacters() {
  const listEl = document.getElementById('sidebar-character-list');
  if (!listEl) return;

  try {
    const ancestors = await legacyFetch('/ancestors') || [];
    renderSidebarCharacters(ancestors);
  } catch (error) {
    console.error('Karakter listesi yüklenemedi:', error);
  }
}

function renderSidebarCharacters(ancestors) {
  const listEl = document.getElementById('sidebar-character-list');
  const labelEl = document.querySelector('.sidebar-char-label');
  if (!listEl) return;

  if (!ancestors || ancestors.length === 0) {
    listEl.innerHTML = '<div class="sidebar-char-empty">Kasa’dan karakter ekle, sohbet burada durur.</div>';
    if (labelEl) labelEl.style.display = '';
    return;
  }

  listEl.innerHTML = '';
  for (const ancestor of ancestors) {
    const item = document.createElement('div');
    item.className = `sidebar-char-item${ancestor.id === activeLegacyAncestorId ? ' active' : ''}`;
    item.dataset.id = String(ancestor.id);

    const avatar = document.createElement('div');
    avatar.className = 'sidebar-char-avatar';
    if (ancestor.photo_url) {
      const img = document.createElement('img');
      img.src = ancestor.photo_url;
      img.alt = ancestor.full_name || '';
      avatar.appendChild(img);
    } else {
      avatar.textContent = (ancestor.full_name || '?').charAt(0).toUpperCase();
    }

    const name = document.createElement('span');
    name.className = 'sidebar-char-name';
    name.textContent = ancestor.full_name || 'Karakter';
    name.title = ancestor.full_name || '';

    item.appendChild(avatar);
    item.appendChild(name);
    item.addEventListener('click', () => {
      startLegacyChat(ancestor.id, ancestor.full_name);
    });
    listEl.appendChild(item);
  }
}

function highlightSidebarCharacter(ancestorId) {
  document.querySelectorAll('.sidebar-char-item').forEach((el) => {
    el.classList.toggle('active', ancestorId != null && parseInt(el.dataset.id, 10) === ancestorId);
  });
}

function applyEvaHeader() {
  const headerTitle = document.querySelector('.header-title');
  if (headerTitle) headerTitle.textContent = 'Eva';

  const statusEl = document.getElementById('status-text');
  if (statusEl && !statusEl.classList.contains('thinking')) {
    statusEl.textContent = '● Çevrimiçi';
  }

  const emojiEl = document.querySelector('.avatar-emoji');
  if (emojiEl) emojiEl.textContent = 'E';

  const userInputEl = document.getElementById('user-input');
  if (userInputEl) userInputEl.placeholder = 'Bir şey yazın…';
}

function applyCharacterHeader(name, photoUrl) {
  const headerTitle = document.querySelector('.header-title');
  if (headerTitle) headerTitle.textContent = name;

  const statusEl = document.getElementById('status-text');
  if (statusEl && !statusEl.classList.contains('thinking')) {
    statusEl.textContent = `● ${name} ile sohbet`;
  }

  const emojiEl = document.querySelector('.avatar-emoji');
  if (emojiEl) {
    if (photoUrl) {
      emojiEl.innerHTML = `<img src="${photoUrl}" alt="" />`;
    } else {
      emojiEl.textContent = (name || '?').charAt(0).toUpperCase();
    }
  }

  const userInputEl = document.getElementById('user-input');
  if (userInputEl) {
    userInputEl.placeholder = `${name} ile konuş...`;
    userInputEl.focus();
  }
}

function getLegacyStatusText() {
  if (isLegacyChatMode && activeLegacyAncestorName) {
    return `● ${activeLegacyAncestorName} ile sohbet`;
  }
  return '● Çevrimiçi';
}

// ══════════════════════════════════════════════════════════════════════════════
// ATA PERSONA SOHBET MODU
// ══════════════════════════════════════════════════════════════════════════════

function leaveLegacyChatMode() {
  isLegacyChatMode = false;
  activeLegacyAncestorId = null;
  activeLegacyAncestorName = null;
  activeLegacyAncestorPhoto = null;
  legacyChatHistory = [];
  applyEvaHeader();
  removeLegacyModeIndicator();
  highlightSidebarCharacter(null);
}

function exitLegacyChat() {
  leaveLegacyChatMode();
  if (typeof startNewChat === 'function') startNewChat();
}

async function startLegacyChat(ancestorId, ancestorName) {
  isLegacyChatMode = true;
  activeLegacyAncestorId = ancestorId;
  activeLegacyAncestorName = ancestorName;
  activeLegacyAncestorPhoto = null;
  legacyChatHistory = [];

  if (typeof activeConversationId !== 'undefined') {
    activeConversationId = null;
  }
  document.querySelectorAll('.conv-item').forEach((el) => el.classList.remove('active'));
  highlightSidebarCharacter(ancestorId);
  removeLegacyModeIndicator();
  closeLegacyModal();
  if (typeof closeSidebar === 'function') closeSidebar();

  const chatWindowEl = document.getElementById('chat-window');
  if (chatWindowEl) chatWindowEl.innerHTML = '';

  try {
    const history = await legacyFetch(`/ancestors/${ancestorId}/chat`);
    activeLegacyAncestorName = history.ancestor_name || ancestorName;
    activeLegacyAncestorPhoto = history.photo_url || null;
    applyCharacterHeader(activeLegacyAncestorName, activeLegacyAncestorPhoto);

    if (!history.messages || history.messages.length === 0) {
      return;
    }

    for (const msg of history.messages) {
      if (typeof addMessage === 'function') {
        addMessage(msg.content, msg.role === 'assistant' ? 'eva' : 'user');
      }
      legacyChatHistory.push({ role: msg.role, content: msg.content });
    }
    if (legacyChatHistory.length > 20) {
      legacyChatHistory = legacyChatHistory.slice(-20);
    }
  } catch (error) {
    applyCharacterHeader(ancestorName, null);
    if (typeof addMessage === 'function') {
      addMessage(`Sohbet geçmişi yüklenemedi: ${error.message}`, 'eva', true);
    }
  }

  const userInputEl = document.getElementById('user-input');
  if (userInputEl) userInputEl.focus();
}

async function sendLegacyChatMessage(message) {
  try {
    const result = await legacyFetch('/chat', 'POST', {
      ancestor_id: activeLegacyAncestorId,
      message: message,
      history: legacyChatHistory
    });

    legacyChatHistory.push({ role: 'user', content: message });
    legacyChatHistory.push({ role: 'assistant', content: result.response });

    if (legacyChatHistory.length > 20) {
      legacyChatHistory = legacyChatHistory.slice(-20);
    }

    return result.response;
  } catch (error) {
    throw new Error(`Sohbet hatası: ${error.message}`);
  }
}

function addLegacyModeIndicator() {
  // Eski kırmızı çarpı göstergesi kaldırıldı — çıkış Eva sohbetine tıklayarak olur.
}

function removeLegacyModeIndicator() {
  const indicator = document.getElementById('legacy-mode-indicator');
  if (indicator) indicator.remove();
}

// ══════════════════════════════════════════════════════════════════════════════
// KENDİ MİRASIM (MASTER SECURITY)
// ══════════════════════════════════════════════════════════════════════════════

async function loadMasterSecurity() {
  const container = document.getElementById('legacy-master-content');
  if (!container) return;
  
  container.innerHTML = '<div class="legacy-loader"><div class="legacy-loader-spinner"></div><span>Yükleniyor...</span></div>';
  
  try {
    // Kullanıcının master persona'sını kontrol et, yoksa otomatik oluştur
    let data = await legacyFetch('/master');
    
    if (!data.has_master) {
      // Otomatik oluştur — EVA zaten kullanıcıyı tanıyor
      const formData = new FormData();
      formData.append('full_name', 'Benim Mirasım');
      formData.append('backstory', 'EVA tarafından otomatik oluşturuldu');
      await legacyFetch('/master', 'POST', formData);
      data = await legacyFetch('/master');
    }
    
    const ancestor = data.ancestor;
    const keys = await legacyFetch('/ancestors/' + ancestor.id + '/key');
    
    // ─── Profil Tamamlama Bölümü ─────────────────────────────────────────
    // 📚 EVA kişiliği zaten sohbetlerden tanıyor; ama fotoğraf ve ses gibi
    //    medya dosyaları yoksa, mirasçı karakteri "göremez ve duyamaz".
    //    Burada eksikler kullanıcıya gösterilir ve opsiyonel olarak
    //    tamamlaması rica edilir.
    const missingItems = [];
    if (!ancestor.photo_url) missingItems.push('📷 Fotoğraf');
    if (!ancestor.audio_url) missingItems.push('🎙️ Ses kaydı');
    if (!ancestor.temperament) missingItems.push('🎭 Mizaç özellikleri');
    if (!ancestor.backstory || ancestor.backstory === 'EVA tarafından otomatik oluşturuldu') {
      missingItems.push('📖 Hayat hikayesi');
    }
    
    let profileHtml = '';
    if (missingItems.length > 0) {
      profileHtml = `
        <div class="legacy-info-card" style="margin-bottom: 15px; border-left: 3px solid #f59e0b;">
          <div class="legacy-info-card-icon">💡</div>
          <div class="legacy-info-card-body">
            <h4>Profilinizi Zenginleştirin (Opsiyonel)</h4>
            <p>Mirasçınızın sizi görebilmesi ve daha iyi tanıyabilmesi için şunları ekleyebilirsiniz:
            <strong>${missingItems.join(', ')}</strong>. Bu tamamen isteğe bağlıdır —
            EVA sizi sohbetlerinizden zaten tanıyor.</p>
            <button onclick="document.getElementById('legacy-master-profile-form').classList.toggle('hidden')"
                    class="legacy-action-btn legacy-action-btn-sm" style="margin-top: 10px;">
              ➕ Şimdi Tamamla
            </button>
          </div>
        </div>
        <div id="legacy-master-profile-form" class="legacy-inline-form hidden" style="margin-bottom: 25px;">
          <h4>🛡️ Miras Profilini Tamamla</h4>
          ${!ancestor.photo_url ? `
            <label class="legacy-modern-label">📷 Fotoğrafınız</label>
            <input type="file" id="master-profile-photo" class="legacy-modern-input" accept="image/*" />
          ` : ''}
          ${!ancestor.audio_url ? `
            <label class="legacy-modern-label">🎙️ Ses Kaydınız</label>
            <input type="file" id="master-profile-audio" class="legacy-modern-input" accept="audio/*" />
          ` : ''}
          <label class="legacy-modern-label">🎭 Mizaç Özellikleriniz</label>
          <textarea id="master-profile-temperament" class="legacy-modern-textarea" rows="2"
                    placeholder="Ör: Esprili, dobra, ailesine düşkün...">${ancestor.temperament || ''}</textarea>
          <label class="legacy-modern-label">📖 Hayat Hikayeniz</label>
          <textarea id="master-profile-backstory" class="legacy-modern-textarea" rows="3"
                    placeholder="Ör: 2004'te doğdum, üniversitede okudum...">${(ancestor.backstory && ancestor.backstory !== 'EVA tarafından otomatik oluşturuldu') ? ancestor.backstory : ''}</textarea>
          <div class="legacy-inline-form-actions">
            <button onclick="saveMasterProfile(${ancestor.id})" class="legacy-action-btn legacy-action-btn-primary legacy-action-btn-sm">
              💾 Kaydet
            </button>
            <button onclick="document.getElementById('legacy-master-profile-form').classList.add('hidden')"
                    class="legacy-action-btn legacy-action-btn-sm">İptal</button>
          </div>
        </div>
      `;
    }
    
    // Anahtar listesi HTML — ortak kart üreticiyi kullan (maskeli + süre bilgili)
    let keysHtml = '';
    if (keys.length === 0) {
      keysHtml = '<div class="legacy-info-empty">Henüz miras anahtarı üretilmemiş. Yukarıdaki butona basarak ilk anahtarınızı oluşturun.</div>';
    } else {
      keysHtml = keys.map(k => renderKeyCard(k)).join('');
    }
    
    // Switch butonu
    let switchBtn = '';
    if (keys.length > 0) {
      switchBtn = '<button onclick="showDeadManForm(' + ancestor.id + ', ' + keys[0].id + ')" class="legacy-action-btn legacy-action-btn-sm" style="margin-bottom: 15px;">⏰ Switch Ayarla</button>';
    } else {
      switchBtn = '<div class="legacy-info-empty">Önce bir miras anahtarı üretin, sonra switch ayarlayabilirsiniz.</div>';
    }
    
    container.innerHTML = 
      '<div class="legacy-info-card" style="margin-bottom: 25px;">' +
        '<div class="legacy-info-card-icon">ℹ️</div>' +
        '<div class="legacy-info-card-body">' +
          '<h4>Dijital Miras Sistemi</h4>' +
          '<p>EVA sizi zaten tanıyor — tüm sohbet geçmişiniz ve kişiliğiniz vektör veritabanında kayıtlı. ' +
          'Burada sadece <strong>miras anahtarınızı</strong> oluşturup, mirasçınıza verebilirsiniz. ' +
          'Mirasçınız bu anahtarla sisteme girdiğinde, EVA\'nın sizin hakkınızda bildiği her şeyi kullanarak ' +
          'sizinle konuşabilecek.</p>' +
        '</div>' +
      '</div>' +
      
      profileHtml +
      
      '<h3 style="color: #fff; margin-bottom: 15px;">🔑 Miras Anahtarlarım</h3>' +
      keySecurityInfoHtml() +
      '<div class="legacy-section-toolbar legacy-key-toolbar" style="margin-bottom: 15px;">' +
        keyValiditySelectHtml() +
        keyTransferSelectHtml() +
        '<button onclick="generateLegacyKey(' + ancestor.id + '); setTimeout(loadMasterSecurity, 800);" class="legacy-action-btn legacy-action-btn-primary">' +
          '➕ Yeni Miras Anahtarı Üret' +
        '</button>' +
      '</div>' +
      
      '<div id="legacy-keys-list">' + keysHtml + '</div>' +
      
      '<h3 style="margin-top: 40px; margin-bottom: 15px; color: #fff;">⏰ Dead Man\'s Switch</h3>' +
      '<div class="legacy-info-card" style="margin-bottom: 15px;">' +
        '<div class="legacy-info-card-icon">⏰</div>' +
        '<div class="legacy-info-card-body">' +
          '<h4>Dead Man\'s Switch Nedir?</h4>' +
          '<p>Belirlediğiniz süre boyunca (örneğin 6 ay) EVA\'ya giriş yapmazsanız, ' +
          'sistem otomatik olarak mirasçınıza miras anahtarını gönderir.</p>' +
        '</div>' +
      '</div>' +
      switchBtn +
      '<div id="legacy-deadman-section"></div>' +
      
      '<div id="legacy-deadman-form" class="legacy-inline-form hidden" data-ancestor-id="' + ancestor.id + '">' +
        '<h4>⏰ Yeni Dead Man\'s Switch</h4>' +
        '<input type="email" id="legacy-deadman-email" class="legacy-modern-input" placeholder="Mirasçının e-posta adresi" />' +
        '<input type="number" id="legacy-deadman-days" class="legacy-modern-input" value="180" min="30" max="3650" placeholder="Gün sayısı (30-3650)" />' +
        '<p class="legacy-form-hint-text">Belirtilen süre boyunca sisteme giriş yapmazsanız, miras anahtarınız bu e-posta adresine gönderilecektir.</p>' +
        '<div class="legacy-inline-form-actions">' +
          '<button id="legacy-deadman-save-btn" class="legacy-action-btn legacy-action-btn-primary legacy-action-btn-sm">💾 Kaydet</button>' +
          '<button onclick="document.getElementById(\'legacy-deadman-form\').classList.add(\'hidden\')" class="legacy-action-btn legacy-action-btn-sm">İptal</button>' +
        '</div>' +
      '</div>';
    
    if (keys.length > 0) {
      loadDeadManSwitches();
    }
  } catch (error) {
    container.innerHTML = '<div class="legacy-error-state">❌ Hata: ' + error.message + '</div>';
  }
}

/**
 * Master persona profilini tamamla/güncelle (Miras Kasası).
 * Sadece doldurulan alanlar gönderilir — boş bırakılanlar değişmez.
 */
async function saveMasterProfile(ancestorId) {
  const formData = new FormData();
  
  const photoInput = document.getElementById('master-profile-photo');
  const audioInput = document.getElementById('master-profile-audio');
  const temperament = document.getElementById('master-profile-temperament')?.value.trim();
  const backstory = document.getElementById('master-profile-backstory')?.value.trim();
  
  if (photoInput?.files[0]) formData.append('photo', photoInput.files[0]);
  if (audioInput?.files[0]) formData.append('audio', audioInput.files[0]);
  if (temperament) formData.append('temperament', temperament);
  if (backstory) formData.append('backstory', backstory);
  
  // Hiçbir alan doldurulmamışsa gönderme
  let hasData = false;
  for (const _ of formData.keys()) { hasData = true; break; }
  if (!hasData) {
    showToast('Kaydedilecek bir bilgi girmediniz.', 'warning');
    return;
  }
  
  try {
    await legacyFetch(`/ancestors/${ancestorId}`, 'PUT', formData);
    showToast('🛡️ Miras profiliniz güncellendi!', 'success');
    loadMasterSecurity();
  } catch (error) {
    showToast('Profil güncellenemedi: ' + error.message, 'error');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// SAYFA YÜKLENDİĞİNDE
// ══════════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    if (localStorage.getItem('eva_token')) {
      deadManCheckin();
    }
  }, 3000);
});
