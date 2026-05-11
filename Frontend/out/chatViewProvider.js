"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatViewProvider = void 0;
const vscode = __importStar(require("vscode"));
const BACKEND_URL = "http://127.0.0.1:8000";
const AUTH_TOKEN_KEY = "autogit.authToken";
const ACTIVE_SESSION_KEY = "autogit.activeSessionId";
class ChatViewProvider {
    constructor(context, output) {
        this.context = context;
        this.output = output;
        this.currentUser = null;
        this.sessionSummaries = [];
    }
    resolveWebviewView(webviewView) {
        this.view = webviewView;
        this.output.appendLine("Webview resolved: autogit.chatView");
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.context.extensionUri]
        };
        webviewView.webview.html = this.getHtml(webviewView.webview);
        webviewView.webview.onDidReceiveMessage(async (message) => {
            if (!isWebviewMessage(message)) {
                return;
            }
            switch (message.type) {
                case "bootstrap":
                    await this.sendAuthState();
                    break;
                case "register":
                    await this.handleRegister(message);
                    break;
                case "login":
                    await this.handleLogin(message);
                    break;
                case "signOut":
                    await this.handleSignOut();
                    break;
                case "newChat":
                    await this.handleNewChat(message.title);
                    break;
                case "selectSession":
                    await this.handleSelectSession(message.sessionId);
                    break;
                case "requestHistory":
                    await this.postCurrentSessionHistory();
                    break;
                case "clearHistory":
                    await this.handleNewChat();
                    break;
                case "openPdf":
                    await this.handleOpenPdf(message.path);
                    break;
                case "userMessage":
                    await this.handleUserMessage(message.text, message.sessionId);
                    break;
                default:
                    break;
            }
        });
    }
    async sendAuthState() {
        const token = await this.getStoredToken();
        if (!token) {
            this.currentUser = null;
            this.currentSessionId = undefined;
            this.sessionSummaries = [];
            this.view?.webview.postMessage({ type: "authState", authenticated: false, sessions: [] });
            return;
        }
        try {
            const bootstrap = await this.fetchJson("/auth/bootstrap", {
                headers: this.authHeaders(token)
            });
            if (!bootstrap.authenticated || !bootstrap.user) {
                await this.clearAuthenticationState();
                this.view?.webview.postMessage({ type: "authState", authenticated: false, sessions: [] });
                return;
            }
            this.currentUser = bootstrap.user;
            this.sessionSummaries = bootstrap.sessions ?? [];
            this.currentSessionId = this.resolveSessionId(bootstrap.active_session_id ?? (await this.getActiveSessionId()), this.sessionSummaries);
            await this.setActiveSessionId(this.currentSessionId);
            this.view?.webview.postMessage({
                type: "authState",
                authenticated: true,
                user: bootstrap.user,
                sessions: this.sessionSummaries,
                active_session_id: this.currentSessionId
            });
            await this.postCurrentSessionHistory();
        }
        catch (error) {
            this.output.appendLine(`Auth state load failed: ${this.normalizeError(error)}`);
            await this.clearAuthenticationState();
            this.view?.webview.postMessage({ type: "authState", authenticated: false, sessions: [] });
        }
    }
    async handleRegister(message) {
        const email = typeof message.email === "string" ? message.email.trim() : "";
        const password = typeof message.password === "string" ? message.password : "";
        const username = typeof message.username === "string" ? message.username.trim() : "";
        if (!email || !password) {
            this.postError("Email and password are required to create an account.");
            return;
        }
        try {
            const response = await this.fetchJson("/auth/register", {
                method: "POST",
                headers: this.jsonHeaders(),
                body: JSON.stringify({ email, password, username: username || undefined })
            });
            await this.setAuthenticatedUser(response.token, response.user, response.sessions, response.active_session_id);
            await this.postCurrentSessionHistory();
        }
        catch (error) {
            this.postError(this.normalizeError(error));
        }
    }
    async handleLogin(message) {
        const email = typeof message.email === "string" ? message.email.trim() : "";
        const password = typeof message.password === "string" ? message.password : "";
        if (!email || !password) {
            this.postError("Email and password are required to sign in.");
            return;
        }
        try {
            const response = await this.fetchJson("/auth/login", {
                method: "POST",
                headers: this.jsonHeaders(),
                body: JSON.stringify({ email, password })
            });
            await this.setAuthenticatedUser(response.token, response.user, response.sessions, response.active_session_id);
            await this.postCurrentSessionHistory();
        }
        catch (error) {
            this.postError(this.normalizeError(error));
        }
    }
    async handleSignOut() {
        await this.clearAuthenticationState();
        this.view?.webview.postMessage({ type: "signedOut" });
        this.view?.webview.postMessage({ type: "authState", authenticated: false, sessions: [] });
    }
    async handleNewChat(title) {
        if (!this.currentUser) {
            this.postError("Sign in first to start a chat.");
            return;
        }
        try {
            const session = await this.fetchJson("/chats/sessions", {
                method: "POST",
                headers: this.authJsonHeaders(),
                body: JSON.stringify({ title: title || "New chat" })
            });
            this.currentSessionId = session.id;
            await this.setActiveSessionId(session.id);
            await this.sendAuthState();
            await this.postCurrentSessionHistory();
        }
        catch (error) {
            this.postError(this.normalizeError(error));
        }
    }
    async handleSelectSession(sessionId) {
        const selectedSessionId = typeof sessionId === "string" ? sessionId.trim() : "";
        if (!selectedSessionId || !this.currentUser) {
            return;
        }
        this.currentSessionId = selectedSessionId;
        await this.setActiveSessionId(selectedSessionId);
        await this.sendAuthState();
        await this.postCurrentSessionHistory();
    }
    /**
     * Core message handler — sends to backend /chat which calls agent.process_message().
     * The agent runs the full agentic loop and returns the final text response.
     * For commit/push operations the agent always auto-proceeds and includes
     * the commit message in its response text (e.g. "📝 Commit message: ...").
     */
    async handleUserMessage(text, sessionId) {
        const message = typeof text === "string" ? text.trim() : "";
        if (!message) {
            return;
        }
        if (!this.currentUser) {
            this.postError("Sign in first to send messages.");
            return;
        }
        // Show loading indicator in the webview
        this.view?.webview.postMessage({ type: "thinking" });
        try {
            const response = await this.fetchJson("/chat", {
                method: "POST",
                headers: this.authJsonHeaders(),
                body: JSON.stringify({
                    message,
                    session_id: sessionId || this.currentSessionId || undefined
                })
            });
            this.currentSessionId = response.session_id;
            await this.setActiveSessionId(response.session_id);
            // Send the agent's response text to the webview
            this.view?.webview.postMessage({
                type: "agentResponse",
                text: response.response,
                session_id: response.session_id,
                session_title: response.session_title
            });
            // Refresh session list and history
            await this.sendAuthState();
            await this.postCurrentSessionHistory();
        }
        catch (error) {
            this.view?.webview.postMessage({ type: "thinkingDone" });
            this.postError(this.normalizeError(error));
        }
    }
    async handleOpenPdf(path) {
        const filePath = typeof path === "string" ? path.trim() : "";
        if (!filePath || !filePath.toLowerCase().endsWith(".pdf")) {
            vscode.window.showErrorMessage("Invalid PDF path.");
            return;
        }
        try {
            await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(filePath));
        }
        catch (error) {
            const msg = error instanceof Error ? error.message : "Failed to open PDF";
            vscode.window.showErrorMessage(msg);
        }
    }
    async setAuthenticatedUser(token, user, sessions, activeSessionId) {
        await this.context.globalState.update(AUTH_TOKEN_KEY, token);
        this.currentUser = user;
        this.sessionSummaries = sessions;
        this.currentSessionId = this.resolveSessionId(activeSessionId ?? sessions[0]?.id, sessions);
        await this.setActiveSessionId(this.currentSessionId);
        this.view?.webview.postMessage({
            type: "authState",
            authenticated: true,
            user,
            sessions,
            active_session_id: this.currentSessionId
        });
    }
    async postCurrentSessionHistory() {
        if (!this.currentUser || !this.currentSessionId) {
            this.view?.webview.postMessage({
                type: "sessionHistory",
                session_id: "",
                title: "New chat",
                messages: []
            });
            return;
        }
        try {
            const history = await this.fetchJson(`/chats/sessions/${encodeURIComponent(this.currentSessionId)}`, { headers: this.authHeaders(await this.getStoredToken()) });
            this.view?.webview.postMessage({
                type: "sessionHistory",
                session_id: history.session_id,
                title: history.title,
                messages: history.messages
            });
        }
        catch (error) {
            this.output.appendLine(`Load history failed: ${this.normalizeError(error)}`);
            this.view?.webview.postMessage({
                type: "sessionHistory",
                session_id: this.currentSessionId,
                title: "New chat",
                messages: []
            });
        }
    }
    async clearAuthenticationState() {
        await this.context.globalState.update(AUTH_TOKEN_KEY, undefined);
        await this.setActiveSessionId(undefined);
        this.currentUser = null;
        this.currentSessionId = undefined;
        this.sessionSummaries = [];
    }
    async getStoredToken() {
        return this.context.globalState.get(AUTH_TOKEN_KEY);
    }
    async getActiveSessionId() {
        return this.context.globalState.get(ACTIVE_SESSION_KEY);
    }
    async setActiveSessionId(sessionId) {
        await this.context.globalState.update(ACTIVE_SESSION_KEY, sessionId);
    }
    postError(text) {
        this.view?.webview.postMessage({ type: "error", text });
    }
    jsonHeaders() {
        return { "Content-Type": "application/json" };
    }
    authHeaders(token) {
        const headers = this.jsonHeaders();
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }
        return headers;
    }
    authJsonHeaders() {
        return this.authHeaders(this.context.globalState.get(AUTH_TOKEN_KEY));
    }
    async fetchJson(path, init) {
        const controller = new AbortController();
        // 3-minute timeout — agent tool chains can take time
        const timeout = setTimeout(() => controller.abort(), 180000);
        const backendUrl = `${BACKEND_URL}${path}`;
        try {
            this.output.appendLine(`${init?.method ?? "GET"} ${backendUrl}`);
            const startedAt = Date.now();
            const response = await fetch(backendUrl, { ...init, signal: controller.signal });
            this.output.appendLine(`Response ${response.status} in ${Date.now() - startedAt}ms`);
            if (!response.ok) {
                throw new Error(await this.readErrorMessage(response));
            }
            return (await response.json());
        }
        finally {
            clearTimeout(timeout);
        }
    }
    async readErrorMessage(response) {
        try {
            const payload = (await response.json());
            if (typeof payload.detail === "string" && payload.detail.trim()) {
                return payload.detail;
            }
        }
        catch {
            // Fall back to raw text
        }
        const body = await response.text();
        return body || `Backend error (${response.status})`;
    }
    normalizeError(error) {
        if (error instanceof Error) {
            if (error.name === "AbortError") {
                return "Request timed out. The agent may still be running — check the backend logs.";
            }
            const cause = error.cause;
            if (cause?.code) {
                return `Connection failed (${cause.code}). Check that the backend is running at 127.0.0.1:8000.`;
            }
            if (cause?.message) {
                return `Connection failed. ${cause.message}`;
            }
            return error.message || "Connection failed. Check that the backend is running at 127.0.0.1:8000.";
        }
        return "Unexpected error contacting the backend.";
    }
    resolveSessionId(sessionId, sessions) {
        if (sessionId && sessions.some((s) => s.id === sessionId)) {
            return sessionId;
        }
        return sessions[0]?.id;
    }
    getHtml(webview) {
        const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", "styles.css"));
        const iconUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", "icon.png"));
        const userIconUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", "user.svg"));
        const logoUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", "logo-dark.png"));
        const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, "media", "script.js"));
        const nonce = getNonce();
        const cachebust = Math.random();
        return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} https:; font-src ${webview.cspSource} https:; img-src ${webview.cspSource} data:; script-src 'nonce-${nonce}';" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link href="${styleUri}?v=${cachebust}" rel="stylesheet" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" />
    <title>AutoGit</title>
  </head>
  <body>
    <div class="page" data-logo-icon="${iconUri}" data-user-icon="${userIconUri}">
      <header class="brand">
        <div class="brand-lockup">
          <button id="sidebarToggle" class="sidebar-toggle" type="button">
            <i class="fas fa-bars"></i>
          </button>
          <img class="brand-logo" src="${logoUri}" alt="AutoGit" />
        </div>
        <div class="brand-actions">
          <div class="brand-actions-top">
            <div id="userBar" class="user-bar hidden">
              <span class="user-bar-label">Signed in as</span>
              <span id="usernameDisplay" class="user-bar-name"></span>
            </div>
          </div>
          <button id="newChatBtn" class="new-chat-header" type="button">
            <span class="new-chat-plus" aria-hidden="true">+</span>
            <span>New chat</span>
          </button>
        </div>
      </header>

      <div class="workspace-container">
        <aside id="sidebar" class="sidebar">
          <div class="sidebar-header">
            <h3>Previous Chats</h3>
            <button id="closeSidebar" class="close-sidebar" type="button">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div id="sessionList" class="session-list"></div>
        </aside>

        <main class="workspace-main">

          <div id="startupGate" class="startup-gate">
            <div class="startup-card">
              <div class="startup-kicker">AutoGit account check</div>
              <div class="startup-title">Preparing your workspace</div>
              <div class="startup-text">Checking whether you are already signed in...</div>
            </div>
          </div>

          <section id="authView" class="panel auth-shell hidden">
            <div class="auth-container">
              <div class="auth-intro">
                <h1 style="font-size: 28px; margin: 0 0 12px 0; text-align: center;">Welcome to AutoGit</h1>
                <p style="color: var(--muted); margin: 0 0 24px 0; text-align: center; font-size: 14px; line-height: 1.5;">
                  Your AI-powered Git assistant for seamless version control and intelligent code collaboration.
                </p>
                <div class="features-grid">
                  <div class="feature-item">
                    <div class="feature-icon"><i class="fas fa-brain"></i></div>
                    <div class="feature-text">AI-Powered Commits</div>
                  </div>
                  <div class="feature-item">
                    <div class="feature-icon"><i class="fas fa-code-merge"></i></div>
                    <div class="feature-text">Conflict Resolution</div>
                  </div>
                  <div class="feature-item">
                    <div class="feature-icon"><i class="fas fa-book"></i></div>
                    <div class="feature-text">Auto Documentation</div>
                  </div>
                  <div class="feature-item">
                    <div class="feature-icon"><i class="fas fa-comments"></i></div>
                    <div class="feature-text">Chat Interface</div>
                  </div>
                </div>
              </div>

              <div class="auth-divider"></div>

              <div class="auth-card" style="margin: 0 auto; max-width: 380px;">
                <div id="loginMode">
                  <h2 style="margin-top: 0; text-align: center;">Sign in</h2>
                  <form id="loginForm" class="auth-form">
                    <label class="auth-field">
                      <span>Email</span>
                      <input id="loginEmail" type="email" autocomplete="email" placeholder="name@example.com" required />
                    </label>
                    <label class="auth-field">
                      <span>Password</span>
                      <input id="loginPassword" type="password" autocomplete="current-password" placeholder="Your password" required />
                    </label>
                    <button id="loginBtn" class="auth-primary" type="submit" style="width: 100%;">Sign in</button>
                  </form>
                  <div style="text-align: center;">
                    <button id="switchToRegister" class="auth-toggle" type="button">Create account</button>
                  </div>
                </div>

                <div id="registerMode" class="hidden">
                  <h2 style="margin-top: 0; text-align: center;">Create account</h2>
                  <form id="registerForm" class="auth-form">
                    <label class="auth-field">
                      <span>Email</span>
                      <input id="registerEmail" type="email" autocomplete="email" placeholder="name@example.com" required />
                    </label>
                    <label class="auth-field">
                      <span>Username</span>
                      <input id="registerUsername" type="text" autocomplete="nickname" placeholder="Your display name" />
                    </label>
                    <label class="auth-field">
                      <span>Password</span>
                      <input id="registerPassword" type="password" autocomplete="new-password" placeholder="Create a password" required />
                    </label>
                    <button id="registerBtn" class="auth-primary" type="submit" style="width: 100%;">Create account</button>
                  </form>
                  <div style="text-align: center;">
                    <button id="switchToLogin" class="auth-toggle" type="button">Back to sign in</button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section id="workspaceShell" class="workspace hidden">
            <section class="panel">
              <div class="panel-header quick-actions-head">
                <h2 class="section-title">Quick Actions</h2>
                <button id="signOutBtn" class="sign-out hidden" type="button">Sign out</button>
              </div>
              <div class="actions-grid">
                <button class="quick-action" type="button" data-message="commit the code">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M5.8 12.7h4.4"></path>
                      <path d="M3.2 8.3C3.2 6.2 4.9 4.5 7 4.5c.7-1.4 2-2.2 3.6-2.2 2.3 0 4.2 1.9 4.2 4.2 1 .3 1.7 1.2 1.7 2.3 0 1.3-1 2.3-2.3 2.3H3.8C2.3 11.1 1 9.8 1 8.3c0-1.4 1-2.5 2.2-2.8"></path>
                      <path d="M8 10.7V6.8"></path>
                      <path d="M6.6 8.2 8 6.8l1.4 1.4"></path>
                    </svg>
                  </span>
                  <span>Commit</span>
                </button>
                <button class="quick-action" type="button" data-message="push the code">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M8 13.5V3.2"></path>
                      <path d="M5.5 5.7 8 3.2l2.5 2.5"></path>
                      <path d="M2.3 13.8h11.4"></path>
                    </svg>
                  </span>
                  <span>Push</span>
                </button>
                <button class="quick-action" type="button" data-message="pull the latest code">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M8 2.5v10.3"></path>
                      <path d="M5.5 10.3 8 12.8l2.5-2.5"></path>
                      <path d="M2.3 2.2h11.4"></path>
                    </svg>
                  </span>
                  <span>Pull</span>
                </button>
                <button class="quick-action" type="button" data-message="create a new branch">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="4" cy="3.5" r="1.6"></circle>
                      <circle cx="12" cy="3.5" r="1.6"></circle>
                      <circle cx="8" cy="12.4" r="1.6"></circle>
                      <path d="M4 5.1v2.5c0 1.5 1.2 2.7 2.7 2.7H8"></path>
                      <path d="M12 5.1v2.5c0 1.5-1.2 2.7-2.7 2.7H8"></path>
                    </svg>
                  </span>
                  <span>Branch</span>
                </button>
                <button class="quick-action" type="button" data-message="show git status">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M5.4 3.2h8.1"></path>
                      <path d="M5.4 8h8.1"></path>
                      <path d="M5.4 12.8h8.1"></path>
                      <circle cx="2.8" cy="3.2" r="0.7" fill="currentColor" stroke="none"></circle>
                      <circle cx="2.8" cy="8" r="0.7" fill="currentColor" stroke="none"></circle>
                      <circle cx="2.8" cy="12.8" r="0.7" fill="currentColor" stroke="none"></circle>
                    </svg>
                  </span>
                  <span>Status</span>
                </button>
                <button class="quick-action" type="button" data-message="resolve merge conflicts">
                  <span class="qa-icon" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M8 1.8 14.3 13H1.7L8 1.8Z"></path>
                      <path d="M8 6v3.8"></path>
                      <circle cx="8" cy="11.7" r="0.7" fill="currentColor" stroke="none"></circle>
                    </svg>
                  </span>
                  <span>Conflicts</span>
                </button>
              </div>
            </section>

            <section class="panel messages-panel">
              <div class="panel-header">
                <h2 class="section-title">Message Area</h2>
                <span id="chatSubtitle" class="panel-hint">Pick a previous chat or start a new one</span>
              </div>
              <div id="emptyState" class="empty-state">
                <div class="empty-title">Start with a quick action</div>
                <div class="empty-text">Use Commit, Push, Pull, Branch, Status, or Conflicts above to begin, or type your request below.</div>
              </div>
              <section id="chat" class="chat"></section>
              <div id="loading" class="loading hidden" aria-live="polite">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </div>
            </section>

            <section class="panel input-panel">
              <h2 class="section-title">Input Area</h2>
              <form id="inputForm" class="input-wrap">
                <textarea id="input" rows="1" placeholder="Ask AutoGit..." aria-label="Chat input"></textarea>
                <button id="sendBtn" type="submit" aria-label="Send message">➤</button>
              </form>
            </section>
          </section>

        </main>
      </div>
    </div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`;
    }
}
exports.ChatViewProvider = ChatViewProvider;
ChatViewProvider.viewType = "autogit.chatView";
function getNonce() {
    let text = "";
    const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}
function isWebviewMessage(value) {
    return typeof value === "object" && value !== null && "type" in value;
}
//# sourceMappingURL=chatViewProvider.js.map