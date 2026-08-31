import { postJSON } from "./js/api.js";

const SESSION_KEY = "yasin_pwa_session_id";
const ACTOR_KEY = "yasin_pwa_actor";

function sessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = "pwa-" + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36));
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function actorId() {
  return localStorage.getItem(ACTOR_KEY) || "pwa-user";
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function addMessage(list, role, text) {
  const item = document.createElement("div");
  item.className = "yasin-chat-message yasin-chat-" + role;
  item.innerHTML = `<div class="yasin-chat-role">${role === "user" ? "You" : "Yasin"}</div><div>${escapeHtml(text)}</div>`;
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;
}

function buildChat() {
  const dialog = document.createElement("dialog");
  dialog.className = "yasin-chat-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="yasin-chat-shell">
      <div class="yasin-chat-header">
        <div><strong>Yasin</strong><div class="hint">Uses the existing Yasin Interface engine.</div></div>
        <button type="submit" class="btn-ghost" aria-label="Close">Close</button>
      </div>
      <div id="yasin-chat-list" class="yasin-chat-list" aria-live="polite"></div>
      <div class="yasin-chat-compose">
        <label class="sr-only" for="yasin-chat-input">Message Yasin</label>
        <input id="yasin-chat-input" autocomplete="off" maxlength="2000" placeholder="Ask about status, an execution, or a control action…">
        <button id="yasin-chat-send" type="button" class="btn-primary">Send</button>
      </div>
    </form>`;

  document.body.appendChild(dialog);
  const list = dialog.querySelector("#yasin-chat-list");
  const input = dialog.querySelector("#yasin-chat-input");
  const send = dialog.querySelector("#yasin-chat-send");

  async function submit() {
    const text = input.value.trim();
    if (!text || send.disabled) return;
    input.value = "";
    addMessage(list, "user", text);
    send.disabled = true;
    const result = await postJSON("/api/interface", {
      text,
      thread_id: sessionId(),
      actor: actorId(),
      yasin_user_id: actorId(),
    });
    if (result.ok && result.data) {
      addMessage(list, "assistant", result.data.answer || result.data.error || "No response.");
      if (result.data.confirmation_required && result.data.confirmation_token) {
        addMessage(list, "assistant", `Confirmation token: ${result.data.confirmation_token}`);
      }
    } else {
      addMessage(list, "assistant", result.message || "Yasin Interface is unavailable.");
    }
    send.disabled = false;
    input.focus();
  }

  send.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  });

  return dialog;
}

function boot() {
  const open = document.getElementById("yasin-chat-open");
  if (!open) return;
  const dialog = buildChat();
  open.addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    const input = dialog.querySelector("#yasin-chat-input");
    if (input) input.focus();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
