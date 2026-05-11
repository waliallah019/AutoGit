const vscode = acquireVsCodeApi();

const page = document.querySelector(".page");
const logoIconUri = page?.dataset.logoIcon || "";
const userIconUri = page?.dataset.userIcon || "";

const authView = document.getElementById("authView");
const workspaceShell = document.getElementById("workspaceShell");
const startupGate = document.getElementById("startupGate");
const authStatus = document.getElementById("authStatus");
const registerForm = document.getElementById("registerForm");
const loginForm = document.getElementById("loginForm");
const registerUsername = document.getElementById("registerUsername");
const registerEmail = document.getElementById("registerEmail");
const registerPassword = document.getElementById("registerPassword");
const loginEmail = document.getElementById("loginEmail");
const loginPassword = document.getElementById("loginPassword");
const loginMode = document.getElementById("loginMode");
const registerMode = document.getElementById("registerMode");
const switchToRegister = document.getElementById("switchToRegister");
const switchToLogin = document.getElementById("switchToLogin");
const userBar = document.getElementById("userBar");
const usernameDisplay = document.getElementById("usernameDisplay");
const signOutBtn = document.getElementById("signOutBtn");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebar = document.getElementById("sidebar");
const closeSidebar = document.getElementById("closeSidebar");
const newChatBtn = document.getElementById("newChatBtn");
const sessionList = document.getElementById("sessionList");
const sessionSubtitle = document.getElementById("chatSubtitle");
const chat = document.getElementById("chat");
const input = document.getElementById("input");
const form = document.getElementById("inputForm");
const sendBtn = document.getElementById("sendBtn");
const loading = document.getElementById("loading");
const quickActions = Array.from(document.querySelectorAll(".quick-action"));
const emptyState = document.getElementById("emptyState");

const state = {
  authenticated: false,
  sessions: [],
  activeSessionId: null,
  currentUser: null,
};

// Sidebar toggle functionality
if (sidebarToggle) {
  sidebarToggle.addEventListener("click", () => {
    sidebar?.classList.toggle("hidden");
  });
}

if (closeSidebar) {
  closeSidebar.addEventListener("click", () => {
    sidebar?.classList.add("hidden");
  });
}

function getTimeLabel() {
  return new Date().toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function setLoading(isLoading) {
  loading.classList.toggle("hidden", !isLoading);
  sendBtn.disabled = isLoading || !state.authenticated;
  input.disabled = isLoading || !state.authenticated;
  newChatBtn.disabled = isLoading || !state.authenticated;
  signOutBtn.disabled = isLoading || !state.authenticated;
  quickActions.forEach((button) => {
    button.disabled = isLoading || !state.authenticated;
  });

  [registerUsername, registerEmail, registerPassword, loginEmail, loginPassword].forEach((element) => {
    if (element) {
      element.disabled = isLoading;
    }
  });

  Array.from(sessionList.querySelectorAll("button")).forEach((button) => {
    button.disabled = isLoading || !state.authenticated;
  });
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function updateEmptyState() {
  if (!emptyState) {
    return;
  }

  const hasUserMessage = !!chat.querySelector(".bubble.user");
  emptyState.classList.toggle("hidden", hasUserMessage);
}

function setViewMode(authenticated) {
  authView?.classList.toggle("hidden", authenticated);
  workspaceShell?.classList.toggle("hidden", !authenticated);
  startupGate.classList.add("hidden");
  if (authenticated) {
    sidebar?.classList.add("hidden");
    if (sidebarToggle) {
      sidebarToggle.classList.remove("hidden");
    }
    if (newChatBtn) {
      newChatBtn.classList.remove("hidden");
    }
  } else {
    if (sidebarToggle) {
      sidebarToggle.classList.add("hidden");
    }
    if (newChatBtn) {
      newChatBtn.classList.add("hidden");
    }
  }
}

function setStartupMode() {
  authView?.classList.add("hidden");
  workspaceShell?.classList.add("hidden");
  startupGate?.classList.remove("hidden");
  if (sidebarToggle) {
    sidebarToggle.classList.add("hidden");
  }
  if (newChatBtn) {
    newChatBtn.classList.add("hidden");
  }
}

function renderSessionList(sessions, activeSessionId) {
  sessionList.innerHTML = "";

  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "No saved chats yet. Create one to start storing history.";
    sessionList.appendChild(empty);
    return;
  }

  sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item${session.id === activeSessionId ? " active" : ""}`;
    button.dataset.sessionId = session.id;

    const title = document.createElement("div");
    title.className = "session-title";
    title.textContent = session.title || "New chat";

    const meta = document.createElement("div");
    meta.className = "session-meta";
    meta.textContent = `${session.message_count} messages`;

    button.appendChild(title);
    button.appendChild(meta);

    button.addEventListener("click", () => {
      setLoading(true);
      vscode.postMessage({ type: "selectSession", sessionId: session.id });
    });

    sessionList.appendChild(button);
  });
}

function createBubble(role, text, isError) {
  const wrapper = document.createElement("div");
  wrapper.className = `bubble ${role}${isError ? " error" : ""}`;

  const row = document.createElement("div");
  row.className = "bubble-row";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  if (role === "assistant" && logoIconUri) {
    const avatarIcon = document.createElement("img");
    avatarIcon.src = logoIconUri;
    avatarIcon.alt = "";
    avatarIcon.setAttribute("aria-hidden", "true");
    avatar.appendChild(avatarIcon);
  } else if (role === "user" && userIconUri) {
    const avatarIcon = document.createElement("img");
    avatarIcon.src = userIconUri;
    avatarIcon.alt = "";
    avatarIcon.setAttribute("aria-hidden", "true");
    avatar.appendChild(avatarIcon);
  }

  const content = document.createElement("div");
  content.className = "bubble-content";

  const textBlock = document.createElement("div");
  textBlock.className = "bubble-text";
  textBlock.textContent = text;

  const time = document.createElement("div");
  time.className = "bubble-time";
  time.textContent = getTimeLabel();

  content.appendChild(textBlock);
  content.appendChild(time);
  row.appendChild(avatar);
  row.appendChild(content);
  wrapper.appendChild(row);

  return wrapper;
}

function extractPdfPath(text) {
  if (typeof text !== "string") return null;
  // Windows: C:\path\file.pdf  OR  Unix: /path/to/file.pdf
  const match = text.match(/([A-Za-z]:\\[^\n]+?\.pdf|\/[^\n\s]+?\.pdf)/i);
  return match ? match[1] : null;
}

function addPdfButton(wrapper, pdfPath) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pdf-link";
  button.textContent = "Open PDF";
  button.addEventListener("click", () => {
    vscode.postMessage({ type: "openPdf", path: pdfPath });
  });
  wrapper.appendChild(button);
}

function addMessage(role, text, isError) {
  const bubble = createBubble(role, text, isError);
  if (!isError && role === "assistant") {
    const pdfPath = extractPdfPath(text);
    if (pdfPath) {
      addPdfButton(bubble, pdfPath);
    }
  }
  chat.appendChild(bubble);
  updateEmptyState();
  scrollToBottom();
}

function renderHistory(items) {
  chat.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    updateEmptyState();
    return;
  }

  items.forEach((item) => {
    addMessage(item.role, item.content, false);
  });

  updateEmptyState();
}

function setActiveSessionLabel(title) {
  sessionSubtitle.textContent = title || "Pick a previous chat or start a new one";
}

function applyAuthenticatedState(message) {
  state.authenticated = !!message.authenticated;
  state.currentUser = message.user || null;
  state.sessions = Array.isArray(message.sessions) ? message.sessions : [];
  state.activeSessionId = message.active_session_id || null;

  setViewMode(true);
  if (userBar) {
    userBar.classList.remove("hidden");
  }
  if (signOutBtn) {
    signOutBtn.classList.remove("hidden");
  }
  if (usernameDisplay && state.currentUser) {
    usernameDisplay.textContent = state.currentUser.username || state.currentUser.email || "You";
  }
  if (authStatus) {
    authStatus.textContent = state.currentUser
      ? `Signed in as ${state.currentUser.username || state.currentUser.email}`
      : "Account ready.";
  }

  renderSessionList(state.sessions, state.activeSessionId);
  const activeSession = state.sessions.find((session) => session.id === state.activeSessionId);
  setActiveSessionLabel(activeSession ? activeSession.title : "Pick a previous chat or start a new one");
  setLoading(false);
}

function sendMessage(rawText) {
  const text = (rawText ?? input.value).trim();
  if (!text || !state.authenticated) {
    return;
  }

  addMessage("user", text, false);
  input.value = "";
  input.style.height = "auto";
  setLoading(true);

  vscode.postMessage({ type: "userMessage", text, sessionId: state.activeSessionId || undefined });
}

function setAuthMode(isRegister) {
  if (isRegister) {
    loginMode?.classList.add("hidden");
    registerMode?.classList.remove("hidden");
  } else {
    loginMode?.classList.remove("hidden");
    registerMode?.classList.add("hidden");
  }
}

function submitRegister(event) {
  event.preventDefault();
  setLoading(true);
  vscode.postMessage({
    type: "register",
    username: registerUsername?.value || "",
    email: registerEmail?.value || "",
    password: registerPassword?.value || "",
  });
}

function submitLogin(event) {
  event.preventDefault();
  setLoading(true);
  vscode.postMessage({
    type: "login",
    email: loginEmail?.value || "",
    password: loginPassword?.value || "",
  });
}

registerForm?.addEventListener("submit", submitRegister);
loginForm?.addEventListener("submit", submitLogin);
switchToRegister?.addEventListener("click", (event) => {
  event.preventDefault();
  setAuthMode(true);
});
switchToLogin?.addEventListener("click", (event) => {
  event.preventDefault();
  setAuthMode(false);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
});

quickActions.forEach((button) => {
  button.addEventListener("click", () => {
    const actionMessage = button.dataset.message || "";
    sendMessage(actionMessage);
  });
});

newChatBtn.addEventListener("click", () => {
  setLoading(true);
  chat.innerHTML = "";
  updateEmptyState();
  vscode.postMessage({ type: "newChat" });
});

signOutBtn.addEventListener("click", () => {
  setLoading(true);
  vscode.postMessage({ type: "signOut" });
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage();
});

window.addEventListener("message", (event) => {
  const message = event.data;
  if (!message || typeof message.type !== "string") {
    return;
  }

  switch (message.type) {
    case "authState":
      if (message.authenticated) {
        applyAuthenticatedState(message);
      } else {
        state.authenticated = false;
        state.currentUser = null;
        state.activeSessionId = null;
        state.sessions = [];
        setViewMode(false);
        setAuthMode(false);
        if (userBar) {
          userBar.classList.add("hidden");
        }
        if (signOutBtn) {
          signOutBtn.classList.add("hidden");
        }
        if (usernameDisplay) {
          usernameDisplay.textContent = "";
        }
        if (authStatus) {
          authStatus.textContent = "";
        }
        chat.innerHTML = "";
      }
      setLoading(false);
      break;
    case "sessionHistory":
      state.activeSessionId = message.session_id || null;
      renderHistory(Array.isArray(message.messages) ? message.messages : []);
      setActiveSessionLabel(message.title || "New chat");
      renderSessionList(state.sessions, state.activeSessionId);
      setLoading(false);
      break;
    case "assistantMessage":
      renderHistory(Array.isArray(message.messages) ? message.messages : []);
      if (message.title) {
        setActiveSessionLabel(message.title);
      }
      setLoading(false);
      break;
    case "sessionList":
      state.sessions = Array.isArray(message.sessions) ? message.sessions : [];
      state.activeSessionId = message.activeSessionId || state.activeSessionId;
      renderSessionList(state.sessions, state.activeSessionId);
      setLoading(false);
      break;
    case "signedOut":
      state.authenticated = false;
      state.currentUser = null;
      state.activeSessionId = null;
      state.sessions = [];
      chat.innerHTML = "";
      setViewMode(false);
      setAuthMode(false);
      if (signOutBtn) {
        signOutBtn.classList.add("hidden");
      }
      if (authStatus) {
        authStatus.textContent = "";
      }
      setLoading(false);
      break;

    case "thinking":
      setLoading(true);
      break;

    case "thinkingDone":
      setLoading(false);
      break;

    case "agentResponse":
      // agent response comes as a single text string
      addMessage("assistant", message.text || "", false);
      if (message.session_title) {
        setActiveSessionLabel(message.session_title);
      }
      setLoading(false);
      break;
    
    case "error":
      addMessage("assistant", message.text || "Request failed", true);
      setLoading(false);
      break;
    default:
      break;
  }
});

setStartupMode();
setAuthMode(false);
setLoading(false);
updateEmptyState();
vscode.postMessage({ type: "bootstrap" });
