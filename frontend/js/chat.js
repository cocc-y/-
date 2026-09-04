/**
 * ShopSmart AI — Chat Interface Logic
 */
const Chat = {
    messagesEl: null,
    inputEl: null,
    sendBtn: null,
    isProcessing: false,

    init() {
        this.messagesEl = document.getElementById('chat-messages');
        this.inputEl = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('btn-send');

        // Input events
        this.inputEl.addEventListener('input', () => this.onInputChange());
        this.inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Quick action buttons
        document.querySelectorAll('.quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const msg = btn.dataset.msg;
                this.inputEl.value = msg;
                this.sendMessage();
            });
        });

        // Clear chat
        document.getElementById('btn-clear-chat').addEventListener('click', () => {
            this.clearChat();
        });

        // Load history
        this.loadHistory();
    },

    onInputChange() {
        const hasText = this.inputEl.value.trim().length > 0;
        this.sendBtn.disabled = !hasText || this.isProcessing;
        // Auto-resize
        this.inputEl.style.height = 'auto';
        this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 120) + 'px';
    },

    async sendMessage() {
        const text = this.inputEl.value.trim();
        if (!text || this.isProcessing) return;

        // Clear welcome
        const welcome = this.messagesEl.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        // Show user message
        this.appendMessage('user', text);
        this.inputEl.value = '';
        this.inputEl.style.height = 'auto';
        this.sendBtn.disabled = true;
        this.isProcessing = true;

        // Show typing
        this.showTyping();

        try {
            const data = await API.sendMessage(text);
            this.hideTyping();

            // Show assistant message with tool calls
            this.appendMessage('assistant', data.response, data.tool_calls);

            // Refresh dashboard data
            if (typeof Dashboard !== 'undefined') Dashboard.refresh();
            if (typeof Notifications !== 'undefined') Notifications.refresh();

        } catch (err) {
            this.hideTyping();
            this.appendMessage('assistant', '❌ 无法连接到服务器。请检查网络。');
        }

        this.isProcessing = false;
        this.onInputChange();
    },

    appendMessage(role, content, toolCalls = []) {
        const div = document.createElement('div');
        div.className = `message ${role}`;

        const avatar = role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

        let toolHtml = '';
        if (toolCalls && toolCalls.length > 0) {
            const chips = toolCalls.map(tc =>
                `<span class="tool-chip"><i class="fas fa-wrench"></i> ${tc.tool}</span>`
            ).join('');
            toolHtml = `<div class="tool-calls">${chips}</div>`;
        }

        // Parse markdown for assistant messages
        let htmlContent = content;
        if (role === 'assistant' && typeof marked !== 'undefined') {
            try {
                htmlContent = marked.parse(content);
            } catch (e) {
                htmlContent = content.replace(/\n/g, '<br>');
            }
        } else {
            htmlContent = content.replace(/\n/g, '<br>');
        }

        div.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">${htmlContent}${toolHtml}</div>
        `;

        this.messagesEl.appendChild(div);
        this.scrollToBottom();
    },

    showTyping() {
        const div = document.createElement('div');
        div.className = 'typing-indicator';
        div.id = 'typing';
        div.innerHTML = `
            <div class="message-avatar" style="background:var(--bg-surface);color:var(--accent-purple);border:1px solid var(--border-color)">
                <i class="fas fa-robot"></i>
            </div>
            <div>
                <div class="typing-dots"><span></span><span></span><span></span></div>
                <div class="typing-label">ShopSmart 正在思考...</div>
            </div>
        `;
        this.messagesEl.appendChild(div);
        this.scrollToBottom();
    },

    hideTyping() {
        const el = document.getElementById('typing');
        if (el) el.remove();
    },

    scrollToBottom() {
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    },

    async loadHistory() {
        try {
            const data = await API.getChatHistory();
            if (data.history && data.history.length > 0) {
                const welcome = this.messagesEl.querySelector('.welcome-message');
                if (welcome) welcome.remove();

                data.history.forEach(msg => {
                    this.appendMessage(msg.role, msg.content);
                });
            }
        } catch (e) {
            console.warn('Chat.loadHistory failed:', e);
        }
    },

    async clearChat() {
        if (!confirm('清除全部聊天记录？')) return;
        try {
            await API.clearChat();
            this.messagesEl.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon"><i class="fas fa-shopping-cart"></i></div>
                    <h3>你好！我是 ShopSmart AI 🛒</h3>
                    <p>我可以帮您搜索产品、比较价格和关注好 deal。</p>
                    <div class="quick-actions">
                        <button class="quick-btn" data-msg="最新iPhone 16价格"><i class="fas fa-mobile-alt"></i> 搜索 iPhone 16</button>
                        <button class="quick-btn" data-msg="游戏本推荐"><i class="fas fa-laptop"></i> 游戏本对比</button>
                        <button class="quick-btn" data-msg="蓝牙耳机推荐"><i class="fas fa-headphones"></i> 蓝牙耳机</button>
                        <button class="quick-btn" data-msg="查看关注的产品"><i class="fas fa-list"></i> 正在关注</button>
                    </div>
                </div>`;
            // Rebind quick buttons
            document.querySelectorAll('.quick-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.inputEl.value = btn.dataset.msg;
                    this.sendMessage();
                });
            });
        } catch (e) {
            console.warn('Chat.clearChat failed:', e);
        }
    }
};
