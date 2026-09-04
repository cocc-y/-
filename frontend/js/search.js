/**
 * ShopSmart AI — Direct Search (No AI needed)
 */
const Search = {
    inputEl: null,
    btnEl: null,
    resultsEl: null,
    statusEl: null,
    isSearching: false,

    init() {
        this.inputEl = document.getElementById('search-input');
        this.btnEl = document.getElementById('btn-search');
        this.resultsEl = document.getElementById('search-results');
        this.statusEl = document.getElementById('search-status');

        if (!this.btnEl) return;

        this.compareBtnEl = document.getElementById('btn-compare');
        this.btnEl.addEventListener('click', () => this.doSearch());
        if (this.compareBtnEl) {
            this.compareBtnEl.addEventListener('click', () => this.doCompare());
        }
        this.inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.doSearch();
        });

        // Tag buttons
        document.querySelectorAll('.search-tag').forEach(tag => {
            tag.addEventListener('click', () => {
                this.inputEl.value = tag.dataset.q;
                this.doSearch();
            });
        });
    },

    async doSearch() {
        const query = this.inputEl.value.trim();
        if (!query || this.isSearching) return;

        this.isSearching = true;
        this.btnEl.disabled = true;
        this.btnEl.textContent = '正在搜索...';

        // Show loading
        this.statusEl.style.display = 'flex';
        this.statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在京东、淘宝、天猫、拼多多、苏宁易购上搜索...';

        // Show skeleton cards
        this.resultsEl.innerHTML = Array(6).fill('<div class="product-skeleton"></div>').join('');

        try {
            const data = await API.get(`/api/search?q=${encodeURIComponent(query)}`);

            if (data.error) {
                this.statusEl.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${data.error}`;
                this.resultsEl.innerHTML = '';
            } else {
                this.renderResults(data, query);
            }
        } catch (err) {
            this.statusEl.innerHTML = '<i class="fas fa-exclamation-circle"></i> 服务器连接错误';
            this.resultsEl.innerHTML = '';
        }

        this.isSearching = false;
        this.btnEl.disabled = false;
        this.btnEl.textContent = '搜索';
    },

    renderResults(data, query) {
        const results = data.results || [];
        const sources = data.sources_found || [];

        // Status bar
        if (results.length === 0) {
            this.statusEl.innerHTML = `<i class="fas fa-info-circle"></i> 未找到 "${query}" 的结果。请尝试其他关键词。`;
            this.resultsEl.innerHTML = '';
            return;
        }

        let statusHtml = `<i class="fas fa-check-circle"></i> 找到 <strong>${results.length}</strong> 个 "${query}" 的结果`;
        if (sources.length > 0) {
            statusHtml += ' &mdash; 来源: ' + sources.join(', ');
        }
        this.statusEl.innerHTML = statusHtml;

        // Keep results around so the track action can read them by index.
        this._results = results;

        // Render product cards
        this.resultsEl.innerHTML = results.map((r, i) => {
            const source = r.source || 'Web';
            const badgeClass = this._sourceBadgeClass(source);
            const snippet = r.snippet
                ? `<div class="product-snippet">${r.snippet}</div>`
                : '';
            const viewBtn = r.url
                ? `<a href="${r.url}" target="_blank" rel="noopener" class="btn-visit"><i class="fas fa-external-link-alt"></i> 在 ${source} 上查看</a>`
                : '';
            const priceBtn = r.url
                ? `<button class="btn-check-price" onclick="Search.fetchPrice('${r.url}', ${i})" id="price-btn-${i}"><i class="fas fa-tag"></i> 查看价格</button>`
                : '';

            return `
                <div class="product-card">
                    <div class="product-header">
                        <span class="product-source-badge ${badgeClass}">${source}</span>
                        <div class="product-name">${r.product_name || '产品'}</div>
                    </div>
                    ${snippet}
                    <div class="product-price-display" id="price-display-${i}"></div>
                    <div class="product-footer">
                        <div class="product-actions">
                            ${priceBtn}
                            ${viewBtn}
                        </div>
                        <div class="track-row">
                            <input type="number" min="0" step="1000" class="track-target-input"
                                   id="track-target-${i}" placeholder="目标价 (¥) — 可选">
                            <button class="btn-track" id="track-btn-${i}" onclick="Search.trackProduct(${i})">
                                <i class="fas fa-bell"></i> 关注
                            </button>
                        </div>
                    </div>
                </div>`;
        }).join('');
    },

    async doCompare() {
        const query = this.inputEl.value.trim();
        if (!query || this.isSearching) return;

        this.isSearching = true;
        if (this.compareBtnEl) this.compareBtnEl.disabled = true;
        this.btnEl.disabled = true;

        this.statusEl.style.display = 'flex';
        this.statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在比较各平台价格（可能需要几秒）...';
        this.resultsEl.innerHTML = Array(4).fill('<div class="product-skeleton"></div>').join('');

        try {
            const data = await API.compare(query);
            if (data.error) {
                this.statusEl.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${data.error}`;
                this.resultsEl.innerHTML = '';
            } else {
                this.renderComparison(data, query);
            }
        } catch (err) {
            console.error('Compare error:', err);
            this.statusEl.innerHTML = '<i class="fas fa-exclamation-circle"></i> 服务器连接错误';
            this.resultsEl.innerHTML = '';
        }

        this.isSearching = false;
        if (this.compareBtnEl) this.compareBtnEl.disabled = false;
        this.btnEl.disabled = false;
    },

    renderComparison(data, query) {
        const offers = data.offers || [];
        if (offers.length === 0) {
            this.statusEl.innerHTML = `<i class="fas fa-info-circle"></i> 未找到 "${query}" 的可比价产品。`;
            this.resultsEl.innerHTML = '';
            return;
        }

        const cheapest = data.cheapest_source;
        let statusHtml = `<i class="fas fa-balance-scale"></i> 比较 <strong>${offers.length}</strong> 个 "${query}" 的来源`;
        if (data.priced_count > 0 && cheapest) {
            statusHtml += ' &mdash; 最便宜: <strong>' + cheapest + '</strong>';
        } else {
            statusHtml += ' &mdash; 尚未从任何来源获取到价格（页面可能已屏蔽抓取）。';
        }
        this.statusEl.innerHTML = statusHtml;

        const rows = offers.map(o => {
            const badge = this._sourceBadgeClass(o.source);
            const priceCell = o.price
                ? `<span class="cmp-price">${o.price_formatted}</span>`
                : '<span class="cmp-price no-price">—</span>';
            const best = o.is_cheapest
                ? '<span class="cmp-best"><i class="fas fa-crown"></i> 最便宜</span>' : '';
            const link = o.url
                ? `<a href="${o.url}" target="_blank" rel="noopener" class="cmp-link"><i class="fas fa-external-link-alt"></i> 查看</a>`
                : '';
            return `
                <div class="cmp-row ${o.is_cheapest ? 'cheapest' : ''}">
                    <span class="product-source-badge ${badge}">${o.source}</span>
                    <span class="cmp-name">${o.product_name || '产品'}</span>
                    ${priceCell}
                    ${best}
                    ${link}
                </div>`;
        }).join('');

        this.resultsEl.innerHTML = `<div class="compare-table">${rows}</div>`;
    },

    async trackProduct(index) {
        const r = (this._results || [])[index];
        if (!r) return;
        const btn = document.getElementById(`track-btn-${index}`);
        const targetEl = document.getElementById(`track-target-${index}`);
        const targetRaw = targetEl ? targetEl.value.trim() : '';

        // Reuse a price already fetched for this card, if any.
        const displayEl = document.getElementById(`price-display-${index}`);
        let currentPrice = null;
        if (displayEl) {
            const m = displayEl.textContent.replace(/[^\d]/g, '');
            if (m) currentPrice = Number(m);
        }

        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在保存...'; }

        try {
            const payload = {
                name: r.product_name || '产品',
                url: r.url || null,
                source: r.source || null,
            };
            if (currentPrice) payload.current_price = currentPrice;
            if (targetRaw) payload.target_price = Number(targetRaw);

            const data = await API.post('/api/track', payload);
            if (data.success) {
                if (btn) { btn.innerHTML = '<i class="fas fa-check"></i> 已关注'; btn.classList.add('tracked'); }
                if (typeof Dashboard !== 'undefined') Dashboard.refresh();
            } else {
                if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-bell"></i> 关注'; }
                alert(data.error || '无法关注产品。');
            }
        } catch (e) {
            console.error('Track error:', e);
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-bell"></i> 关注'; }
            alert('关注时连接错误。');
        }
    },

    async fetchPrice(url, index) {
        const btn = document.getElementById(`price-btn-${index}`);
        const display = document.getElementById(`price-display-${index}`);
        if (!btn || !display) return;

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在获取价格...';

        try {
            const data = await API.post('/api/scrape-price', { url });

            if (data.price) {
                display.innerHTML = `<span class="product-price">${data.price_formatted || data.price}</span>`;
                btn.style.display = 'none';
            } else {
                display.innerHTML = '<span class="product-price no-price">无法获取价格。请在原页面查看。</span>';
                btn.style.display = 'none';
            }
        } catch (err) {
            display.innerHTML = '<span class="product-price no-price">连接错误</span>';
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-tag"></i> 重试';
        }
    },

    _sourceBadgeClass(source) {
        const map = {
            '京东': 'jd', '淘宝': 'taobao', '天猫': 'tmall',
            '拼多多': 'pdd', '苏宁易购': 'suning',
            '什么值得买': 'smzdm', '唯品会': 'vip', '当当': 'dangdang',
        };
        return map[source] || 'web';
    }
};
