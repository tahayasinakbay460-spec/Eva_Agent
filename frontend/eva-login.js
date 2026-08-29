/**
 * auth.js — EVA Kimlik Doğrulama Mantığı
 * =========================================
 * - localStorage'da token yönetimi
 * - Login / Register API çağrıları
 * - Tab geçişleri
 * - Parçacık animasyonu (canvas)
 * - Şifre güç göstergesi
 */

const API_BASE = '/api';

/* ================================================================
   TOKEN YÖNETİMİ
   ================================================================ */

function saveSession(tokenResponse) {
  localStorage.setItem('eva_token', tokenResponse.access_token);
  localStorage.setItem('eva_user_id', tokenResponse.user_id);
  localStorage.setItem('eva_username', tokenResponse.username);
}

function getToken() {
  return localStorage.getItem('eva_token');
}

function clearSession() {
  localStorage.removeItem('eva_token');
  localStorage.removeItem('eva_user_id');
  localStorage.removeItem('eva_username');
}

/* ================================================================
   SAYFA BAŞLANGIÇ KONTROLÜ
   ================================================================ */

/**
 * Eğer token varsa → token geçerli mi kontrol et
 * Geçerliyse direkt chat'e yönlendir.
 */
async function checkExistingSession() {
  const token = getToken();
  if (!token) return; // Zaten giriş sayfasındayız yani token yok o yuzden ana chat ekranına gitmiyoruz 

  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (response.ok) {
      // Token hâlâ geçerli → chat'e git
      goToChat();
    } else {
      // Token süresi dolmuş → temizle
      clearSession();
    }
  } catch {
    // Backend çalışmıyor — giriş sayfasında kal
  }
}

function goToChat() {
  window.location.href = '/chat'; // token geçerliyse kullaniciyi otomatik olarak chat ekranına yönlendiriyoruz
}

/* ================================================================
   SEKME GEÇİŞİ
   ================================================================ */

function switchTab(tab) {
  const loginWrapper = document.getElementById('form-login-wrapper');
  const registerWrapper = document.getElementById('form-register-wrapper');
  const tabLogin = document.getElementById('tab-login');
  const tabRegister = document.getElementById('tab-register');

  // Hata mesajlarını temizle
  hideError('login-error');
  hideError('register-error');

  if (tab === 'login') {
    loginWrapper.classList.add('active');
    registerWrapper.classList.remove('active');
    tabLogin.classList.add('active');
    tabRegister.classList.remove('active');

    // Kısa gecikme ile animasyon
    setTimeout(() => {
      loginWrapper.style.opacity = '1';
      loginWrapper.style.transform = 'translateY(0)';
    }, 10);
  } else {
    registerWrapper.classList.add('active');
    loginWrapper.classList.remove('active');
    tabRegister.classList.add('active');
    tabLogin.classList.remove('active');

    setTimeout(() => {
      registerWrapper.style.opacity = '1';
      registerWrapper.style.transform = 'translateY(0)';
    }, 10);
  }
}

/* ================================================================
   GİRİŞ
   ================================================================ */

async function handleLogin(event) {
  event.preventDefault();

  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('btn-login');

  hideError('login-error');
  setButtonLoading(btn, true);

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      showError('login-error', data.detail || 'Giriş başarısız.');
      return;
    }

    // Başarılı giriş
    saveSession(data);
    playSuccessAnimation();

    // Kısa gecikme ile chat'e geçiş (animasyon için)
    setTimeout(goToChat, 700);

  } catch (err) {
    showError('login-error', 'Bağlantı hatası. Backend çalışıyor mu?');
  } finally {
    setButtonLoading(btn, false);
  }
}

/* ================================================================
   KAYIT
   ================================================================ */

async function handleRegister(event) {
  event.preventDefault();

  const username = document.getElementById('reg-username').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const btn = document.getElementById('btn-register');

  hideError('register-error');
  setButtonLoading(btn, true);

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      showError('register-error', data.detail || 'Kayıt başarısız.');
      return;
    }

    // Başarılı kayıt = otomatik giriş
    saveSession(data);
    playSuccessAnimation();

    setTimeout(goToChat, 700);

  } catch (err) {
    showError('register-error', 'Bağlantı hatası. Backend çalışıyor mu?');
  } finally {
    setButtonLoading(btn, false);
  }
}

/* ================================================================
   YARDIMCI FONKSİYONLAR
   ================================================================ */

function showError(elementId, message) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = '⚠️ ' + message;
  el.style.display = 'block';
  // Animasyonu tekrar tetikle
  el.style.animation = 'none';
  el.offsetHeight; // reflow
  el.style.animation = 'shakeError 0.4s ease';
}

function hideError(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.style.display = 'none';
}

function setButtonLoading(btn, loading) {
  const text = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.btn-spinner');
  btn.disabled = loading;
  if (loading) {
    text.style.display = 'none';
    spinner.style.display = 'inline-block';
  } else {
    text.style.display = 'inline';
    spinner.style.display = 'none';
  }
}

function playSuccessAnimation() {
  const card = document.getElementById('auth-card');
  card.classList.add('success');
}

/* ─── Şifre Göster/Gizle ─────────────────────────────────────── */
function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
}

/* ─── Şifre Güç Göstergesi ───────────────────────────────────── */
function updatePasswordStrength(password) {
  const fill = document.getElementById('strength-fill');
  const label = document.getElementById('strength-label');
  if (!fill || !label) return;

  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  const levels = [
    { pct: '0%', color: 'transparent', text: 'Şifre gücü' },
    { pct: '25%', color: '#f43f5e', text: 'Çok zayıf' },
    { pct: '45%', color: '#fb923c', text: 'Zayıf' },
    { pct: '65%', color: '#facc15', text: 'Orta' },
    { pct: '85%', color: '#34d399', text: 'Güçlü' },
    { pct: '100%', color: '#10b981', text: '💪 Çok güçlü' },
  ];

  const level = levels[Math.min(score, 5)];
  fill.style.width = level.pct;
  fill.style.backgroundColor = level.color;
  label.textContent = level.text;
}

/* ================================================================
   PARÇACIK ANİMASYONU (CANVAS)
   ================================================================ */

class ParticleSystem {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.resize();
    this.init();
    window.addEventListener('resize', () => this.resize());
    this.animate();
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  init() {
    const count = Math.floor((window.innerWidth * window.innerHeight) / 18000);
    for (let i = 0; i < count; i++) {
      this.particles.push(this.createParticle());
    }
  }

  createParticle() {
    return {
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      size: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.5 + 0.1,
      color: this.randomColor(),
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: Math.random() * 0.02 + 0.01,
    };
  }

  randomColor() {
    const colors = ['99, 102, 241', '168, 85, 247', '34, 211, 238', '236, 72, 153'];
    return colors[Math.floor(Math.random() * colors.length)];
  }

  animate() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    this.particles.forEach(p => {
      // Hareket
      p.x += p.vx;
      p.y += p.vy;
      p.pulse += p.pulseSpeed;

      // Sınır kontrolü
      if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1;

      // Nabız opacity
      const alpha = p.opacity * (0.7 + 0.3 * Math.sin(p.pulse));

      // Çiz
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      this.ctx.fillStyle = `rgba(${p.color}, ${alpha})`;
      this.ctx.fill();
    });

    // Yakın parçacıkları bağlayan çizgiler
    for (let i = 0; i < this.particles.length; i++) {
      for (let j = i + 1; j < this.particles.length; j++) {
        const dx = this.particles[i].x - this.particles[j].x;
        const dy = this.particles[i].y - this.particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 120) {
          const alpha = (1 - dist / 120) * 0.15;
          this.ctx.beginPath();
          this.ctx.moveTo(this.particles[i].x, this.particles[i].y);
          this.ctx.lineTo(this.particles[j].x, this.particles[j].y);
          this.ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`;
          this.ctx.lineWidth = 0.5;
          this.ctx.stroke();
        }
      }
    }

    requestAnimationFrame(() => this.animate());
  }
}

/* ================================================================
   BAŞLANGIÇ
   ================================================================ */

document.addEventListener('DOMContentLoaded', () => {
  checkExistingSession();
});

window.switchTab = switchTab;
window.handleLogin = handleLogin;
window.handleRegister = handleRegister;
window.togglePassword = togglePassword;
window.updatePasswordStrength = updatePasswordStrength;
