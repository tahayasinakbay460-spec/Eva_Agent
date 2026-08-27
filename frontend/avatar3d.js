/**
 * avatar3d.js — Faz 7: Gerçekçi İnsan Avatarı
 * ================================================
 * Duygu durumuna göre önceden oluşturulmuş gerçekçi
 * AI yüzü görselleri arasında geçiş yapar.
 */

'use strict';

let currentAvatarState   = 'neutral';
let currentAvatarEmotion = 'neutral';
let _speakingInterval    = null;

// Duygu → görsel dosya adı
const EMOTION_FILES = {
  happy:     'happy.jpg',
  sad:       'sad.jpg',
  angry:     'angry.jpg',
  surprised: 'surprised.jpg',
  fearful:   'fearful.jpg',
  disgusted: 'disgusted.jpg',
  neutral:   'neutral.jpg',
};

// ─── Duygu Güncelle ──────────────────────────────────────────────────────────
function update3DAvatarEmotion(emotion) {
  currentAvatarEmotion = emotion;
  const avatarImg = document.getElementById('human-avatar-img');
  if (!avatarImg) return;

  const fileName = EMOTION_FILES[emotion] || EMOTION_FILES.neutral;
  avatarImg.src = `/static/avatars/${fileName}`;
  
  // Duyguya göre çok hafif gölge rengi değişimi (opsiyonel estetik dokunuş)
  const colors = {
    happy: 'rgba(34,197,94,0.4)',
    sad: 'rgba(59,130,246,0.4)',
    angry: 'rgba(239,68,68,0.4)',
    surprised: 'rgba(245,158,11,0.4)',
    fearful: 'rgba(139,92,246,0.4)',
    disgusted: 'rgba(107,114,128,0.4)',
    neutral: 'rgba(124,58,237,0.3)'
  };
  
  avatarImg.style.boxShadow = `0 0 40px ${colors[emotion] || colors.neutral}`;
  avatarImg.style.borderColor = colors[emotion] || colors.neutral;
}

// ─── Durum Güncelle ──────────────────────────────────────────────────────────
function set3DAvatarState(state) {
  currentAvatarState = state;
  const avatarImg = document.getElementById('human-avatar-img');
  if (!avatarImg) return;

  if (state === 'speaking') {
    _startSpeakingAnimation();
  } else {
    _stopSpeakingAnimation();
    update3DAvatarEmotion(currentAvatarEmotion);
  }
}

// ─── Konuşurken Animasyon ───────────────────────────────────────────────
function _startSpeakingAnimation() {
  if (_speakingInterval) return;
  const avatarImg = document.getElementById('human-avatar-img');
  if (!avatarImg) return;

  let pulse = false;
  _speakingInterval = setInterval(() => {
    pulse = !pulse;
    if(pulse) {
        avatarImg.style.transform = 'scale(1.03)';
    } else {
        avatarImg.style.transform = 'scale(1.0)';
    }
  }, 300);
}

function _stopSpeakingAnimation() {
  if (_speakingInterval) {
    clearInterval(_speakingInterval);
    _speakingInterval = null;
    const avatarImg = document.getElementById('human-avatar-img');
    if (avatarImg) avatarImg.style.transform = 'scale(1.0)';
  }
}

// 📚 Not: updateAvatarEmotion() ve resetAvatarEmotion() script.js'te tanımlıdır.
//    Burada da tanımlıydılar ama script.js sonra yüklendiği için onları eziyordu —
//    kafa karışıklığını önlemek için buradaki kopyalar kaldırıldı.

function init3DAvatar() {
  console.log('✅ Gerçekçi İnsan Avatarı hazır');
  update3DAvatarEmotion('neutral');
  set3DAvatarState('listening');
}
