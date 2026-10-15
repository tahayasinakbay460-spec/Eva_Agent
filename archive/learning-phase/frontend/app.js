// Backend adresi. Deploy ederken burayı değiştireceğiz.
const API_URL = "http://127.0.0.1:8000";

const chatEl = document.getElementById("chat");
const emptyEl = document.getElementById("empty");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const sendEl = document.getElementById("send");
const usernameEl = document.getElementById("username");
const statusEl = document.getElementById("status");

let waiting = false;

// --- Kullanıcı adı: tarayıcıda hatırlanır ---
try {
  usernameEl.value = localStorage.getItem("eva-username") || "";
} catch {}
usernameEl.addEventListener("input", () => {
  try { localStorage.setItem("eva-username", usernameEl.value.trim()); } catch {}
});

function getUsername() {
  return usernameEl.value.trim() || "misafir";
}

// --- Ekrana mesaj basma ---
function addMessage(kind, text) {
  emptyEl.hidden = true;

  const row = document.createElement("div");
  row.className = `row ${kind}`;

  if (kind === "eva") {
    const avatar = document.createElement("div");
    avatar.className = "avatar small";
    avatar.textContent = "E";
    row.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text; // textContent: gelen yazı HTML olarak çalıştırılmaz
  row.appendChild(bubble);

  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
  return row;
}

function showTyping() {
  const row = addMessage("eva", "");
  row.querySelector(".bubble").innerHTML =
    '<span class="typing"><span></span><span></span><span></span></span>';
  return row;
}

// --- Backend'e mesaj gönderme ---
async function sendMessage(text) {
  const response = await fetch(`${API_URL}/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: getUsername(), message: text }),
  });

  if (!response.ok) {
    let detail = `Sunucu ${response.status} hatası döndürdü.`;
    try {
      const data = await response.json();
      if (data.detail) {
        detail += " " + (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      }
    } catch {}
    throw new Error(detail);
  }

  const data = await response.json(); // { content: "...", agent: "Eva" }
  return data.content;
}

async function handleSubmit(event) {
  event.preventDefault();
  const text = inputEl.value.trim();
  if (!text || waiting) return;

  addMessage("user", text);
  inputEl.value = "";
  autoResize();
  setWaiting(true);

  const typingRow = showTyping();
  try {
    const reply = await sendMessage(text);
    typingRow.remove();
    addMessage("eva", reply);
    setStatus(true);
  } catch (err) {
    typingRow.remove();
    const offline = err instanceof TypeError; // fetch hiç ulaşamadıysa TypeError fırlatır
    addMessage("error", offline
      ? "Backend'e ulaşılamadı. Uvicorn çalışıyor mu? (uvicorn app.main:app --reload)"
      : err.message);
    if (offline) setStatus(false);
  } finally {
    setWaiting(false);
    inputEl.focus();
  }
}

// --- Yardımcılar ---
function setWaiting(value) {
  waiting = value;
  sendEl.disabled = value;
}

function setStatus(online) {
  statusEl.textContent = online ? "çevrimiçi" : "bağlantı yok";
  statusEl.className = `status ${online ? "online" : "offline"}`;
}

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = inputEl.scrollHeight + "px";
}

async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/`);
    setStatus(response.ok);
  } catch {
    setStatus(false);
  }
}

// --- Olaylar ---
formEl.addEventListener("submit", handleSubmit);
inputEl.addEventListener("input", autoResize);
inputEl.addEventListener("keydown", (event) => {
  // Enter gönderir, Shift+Enter yeni satır
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

checkHealth();
inputEl.focus();
