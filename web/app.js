const chatListEl = document.getElementById("chatList");
const messagesEl = document.getElementById("messages");
const summaryEl = document.getElementById("summary");
const newChatBtn = document.getElementById("newChatBtn");
const deleteChatBtn = document.getElementById("deleteChatBtn");
const clearStorageBtn = document.getElementById("clearStorageBtn");
const useLLMCheckbox = document.getElementById("useLLM");
const sendBtn = document.getElementById("sendBtn");
const messageInput = document.getElementById("messageInput");
const namesInput = document.getElementById("namesInput");
const projectCodeInput = document.getElementById("projectCode");
const cabinetCodeInput = document.getElementById("cabinetCode");
const statusEl = document.getElementById("status");

const STORAGE_KEY = "digroup_chats";

let chats = loadChats();
let activeChatId = chats.length ? chats[0].id : null;

if (!activeChatId) {
  activeChatId = createChat();
}

renderChatList();
renderChat();

newChatBtn.addEventListener("click", () => {
  activeChatId = createChat();
  renderChatList();
  renderChat();
});

deleteChatBtn.addEventListener("click", () => {
  if (!activeChatId) return;
  chats = chats.filter((chat) => chat.id !== activeChatId);
  if (!chats.length) {
    activeChatId = createChat();
  } else {
    activeChatId = chats[0].id;
  }
  saveChats();
  renderChatList();
  renderChat();
});

clearStorageBtn.addEventListener("click", () => {
  if (confirm("Очистить все чаты?")) {
    localStorage.removeItem(STORAGE_KEY);
    location.reload();
  }
});

sendBtn.addEventListener("click", async () => {
  const text = messageInput.value.trim();
  const names = parseNames(namesInput.value);
  const hasNames = names.length > 0;
  if (!text && !hasNames) return;

  const mode = getMode();

  const chat = getActiveChat();
  const userContent = text || `Позиции (${names.length}):\n${names.join("\n")}`;
  chat.messages.push({ role: "user", content: userContent });
  chat.mode = mode;
  chat.projectCode = projectCodeInput.value.trim();
  chat.cabinetCode = cabinetCodeInput.value.trim();
  chat.namesText = namesInput.value.trim();
  chat.useLLM = useLLMCheckbox.checked;
  saveChats();
  renderChat();

  messageInput.value = "";
  statusEl.textContent = "Отправка...";

  try {
    const historyWithoutLast = chat.messages.slice(0, -1);
    const payload = {
      message: text || "Позиции для расчёта",
      names: names.length ? names : null,
      history: historyWithoutLast,
      project_code: chat.projectCode || null,
      cabinet_code: chat.cabinetCode || null,
      mode: mode,
      use_llm: useLLMCheckbox.checked,
    };
    console.log("Sending payload:", JSON.stringify(payload, null, 2));

    const response = await fetch("/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Ошибка API");
    }
    const replyText = data.reply || formatDataAsText(data.data);
    chat.messages.push({ role: "assistant", content: replyText });
    chat.lastData = data.data || null;
    saveChats();
    renderChat();
    renderSummary();
    statusEl.textContent = "Готов";
  } catch (err) {
    chat.messages.push({ role: "assistant", content: `Ошибка запроса: ${err.message}` });
    saveChats();
    renderChat();
    statusEl.textContent = "Ошибка";
  }
});

function parseNames(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function getMode() {
  const selected = document.querySelector("input[name=mode]:checked");
  return selected ? selected.value : "auto";
}

function createChat() {
  const id = `chat_${Date.now()}`;
  chats.unshift({
    id,
    title: "Новый чат",
    messages: [],
    mode: "auto",
    projectCode: "",
    cabinetCode: "",
    namesText: "",
    useLLM: useLLMCheckbox.checked,
    lastData: null,
  });
  saveChats();
  return id;
}

function getActiveChat() {
  return chats.find((c) => c.id === activeChatId);
}

function renderChatList() {
  chatListEl.innerHTML = "";
  chats.forEach((chat) => {
    const item = document.createElement("div");
    item.className = `chat-item ${chat.id === activeChatId ? "active" : ""}`;
    item.textContent = chat.title;
    item.addEventListener("click", () => {
      activeChatId = chat.id;
      renderChatList();
      renderChat();
    });
    chatListEl.appendChild(item);
  });
}

function renderChat() {
  const chat = getActiveChat();
  if (!chat) return;

  const lastUser = [...chat.messages].reverse().find((m) => m.role === "user");
  if (lastUser) {
    chat.title = lastUser.content.slice(0, 28);
  }

  messagesEl.innerHTML = "";
  chat.messages.forEach((msg) => {
    const row = document.createElement("div");
    row.className = `message ${msg.role === "user" ? "user" : "assistant"}`;
    const role = document.createElement("div");
    role.className = "role";
    role.textContent = msg.role === "user" ? "Вы" : "AI";
    const content = document.createElement("div");
    content.className = "content";
    content.textContent = msg.content;
    row.appendChild(role);
    row.appendChild(content);
    messagesEl.appendChild(row);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;

  projectCodeInput.value = chat.projectCode || "";
  cabinetCodeInput.value = chat.cabinetCode || "";
  namesInput.value = chat.namesText || "";
  messageInput.value = "";
  useLLMCheckbox.checked = chat.useLLM !== undefined ? chat.useLLM : true;

  const modeInput = document.querySelector(`input[name=mode][value=${chat.mode}]`);
  if (modeInput) modeInput.checked = true;

  renderSummary();
}

function renderSummary() {
  const chat = getActiveChat();
  summaryEl.innerHTML = "";
  if (!chat || !chat.lastData) return;

  const data = chat.lastData;
  const block = document.createElement("div");
  block.className = "block";

  const totalProjects = Object.keys(data.total_time_by_project || {}).length;
  const totalCabinets = Object.keys(data.total_time_by_cabinet || {}).length;

  block.innerHTML = `
    <div><strong>Итог:</strong> проектов=${totalProjects}, шкафов=${totalCabinets}</div>
    <div style="margin-top:6px;"><strong>Время по шкафам:</strong></div>
    <div>${formatKeyValues(data.total_time_by_cabinet)}</div>
    <div style="margin-top:6px;"><strong>Время по проектам:</strong></div>
    <div>${formatKeyValues(data.total_time_by_project)}</div>
    <div style="margin-top:6px;"><strong>Ненайденные:</strong></div>
    <div>${(data.not_found_items || []).join(", ") || "—"}</div>
  `;

  summaryEl.appendChild(block);
}

function formatKeyValues(obj) {
  if (!obj) return "—";
  const entries = Object.entries(obj);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${k}: ${v} мин`).join("<br>");
}

function formatDataAsText(data) {
  if (!data) return "(нет данных)";
  const foundCount = data.found_items?.length || 0;
  const notFoundCount = data.not_found_items?.length || 0;
  const totalByCabinet = data.total_time_by_cabinet || {};
  const totalByProject = data.total_time_by_project || {};
  
  let text = `Найдено позиций: ${foundCount}`;
  if (notFoundCount > 0) {
    text += `\nНе найдено: ${notFoundCount}`;
  }
  text += "\n\nВремя по шкафам:";
  for (const [k, v] of Object.entries(totalByCabinet)) {
    text += `\n- ${k}: ${v} мин`;
  }
  text += "\n\nВремя по проектам:";
  for (const [k, v] of Object.entries(totalByProject)) {
    text += `\n- ${k}: ${v} мин`;
  }
  return text;
}

function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveChats() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}
