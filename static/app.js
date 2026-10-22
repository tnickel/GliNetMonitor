// GL.iNet Gateway Network Monitor Frontend Logic

class GliNetMonitorApp {
    constructor() {
        this.selectedClientIp = null;
        this.selectedClientData = null;
        this.clients = [];
        this.domainFilter = 'all';
        this.domainSort = 'count';
        this.domainSearch = '';
        this.autoRefreshTimer = null;
        this.isStreamPaused = false;
        
        // Chart instances
        this.miniChart = null;
        this.trendChart = null;

        this.init();
    }

    init() {
        this.bindEvents();
        this.initCharts();
        this.startAutoRefresh(5);

        // Initial Data Load
        this.refreshAll();
    }

    bindEvents() {
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetTab = btn.getAttribute('data-tab');
                this.switchTab(targetTab);
            });
        });

        // Client search
        const clientSearch = document.getElementById('clientSearchInput');
        clientSearch.addEventListener('input', (e) => {
            this.renderClientsList(e.target.value);
        });

        // Domain search
        const domainSearch = document.getElementById('domainSearchInput');
        let domainSearchDebounce;
        domainSearch.addEventListener('input', (e) => {
            clearTimeout(domainSearchDebounce);
            domainSearchDebounce = setTimeout(() => {
                this.domainSearch = e.target.value;
                if (this.selectedClientIp) {
                    this.loadClientDomains(this.selectedClientIp);
                }
            }, 250);
        });

        // Filter pills for client domains
        document.querySelectorAll('.filter-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                this.domainFilter = pill.getAttribute('data-filter');
                if (this.selectedClientIp) {
                    this.loadClientDomains(this.selectedClientIp);
                }
            });
        });

        // Sort select for client domains
        const domainSort = document.getElementById('domainSortSelect');
        domainSort.addEventListener('change', (e) => {
            this.domainSort = e.target.value;
            if (this.selectedClientIp) {
                this.loadClientDomains(this.selectedClientIp);
            }
        });

        // Network domain search
        const netDomainSearch = document.getElementById('networkDomainSearchInput');
        let netSearchDebounce;
        netDomainSearch.addEventListener('input', (e) => {
            clearTimeout(netSearchDebounce);
            netSearchDebounce = setTimeout(() => {
                this.loadNetworkDomains(e.target.value);
            }, 300);
        });

        // Manual Sync button
        const btnSync = document.getElementById('btnManualSync');
        btnSync.addEventListener('click', () => this.triggerSync());

        // Auto Refresh selector
        const refreshSelect = document.getElementById('autoRefreshSelect');
        refreshSelect.addEventListener('change', (e) => {
            const sec = parseInt(e.target.value, 10);
            this.startAutoRefresh(sec);
        });

        // Pause stream button
        const btnPause = document.getElementById('btnPauseStream');
        btnPause.addEventListener('click', () => {
            this.isStreamPaused = !this.isStreamPaused;
            btnPause.innerHTML = this.isStreamPaused 
                ? '<i class="fa-solid fa-play"></i> <span>Fortsetzen</span>'
                : '<i class="fa-solid fa-pause"></i> <span>Pausieren</span>';
            btnPause.classList.toggle('btn-primary', this.isStreamPaused);
        });
    }

    switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
        });

        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === tabId);
        });

        // Specific tab actions
        if (tabId === 'tab-network') {
            this.loadNetworkDomains();
        } else if (tabId === 'tab-livestream') {
            this.loadLiveStream();
        } else if (tabId === 'tab-trends') {
            this.loadTrends();
        }
    }

    startAutoRefresh(seconds) {
        if (this.autoRefreshTimer) {
            clearInterval(this.autoRefreshTimer);
            this.autoRefreshTimer = null;
        }

        if (seconds > 0) {
            this.autoRefreshTimer = setInterval(() => {
                this.refreshLight();
            }, seconds * 1000);
        }
    }

    async refreshAll() {
        await Promise.all([
            this.loadStatus(),
            this.loadSummary(),
            this.loadClients()
        ]);

        const activeTab = document.querySelector('.tab-pane.active')?.id;
        if (activeTab === 'tab-network') {
            this.loadNetworkDomains();
        } else if (activeTab === 'tab-livestream') {
            this.loadLiveStream();
        } else if (activeTab === 'tab-trends') {
            this.loadTrends();
        }
    }

    async refreshLight() {
        await this.loadStatus();
        await this.loadSummary();
        await this.loadClients(true);

        const activeTab = document.querySelector('.tab-pane.active')?.id;
        if (activeTab === 'tab-clients' && this.selectedClientIp) {
            this.loadClientDomains(this.selectedClientIp, true);
        } else if (activeTab === 'tab-livestream' && !this.isStreamPaused) {
            this.loadLiveStream();
        }
    }

    async triggerSync() {
        const icon = document.getElementById('syncIcon');
        icon.classList.add('rotating');
        try {
            const resp = await fetch('/api/sync', { method: 'POST' });
            const data = await resp.json();
            this.showToast(`Synchronisiert: ${data.new_queries || 0} neue Anfragen erfasst`);
            await this.refreshAll();
        } catch (e) {
            this.showToast('Fehler bei der Synchronisation: ' + e, 'danger');
        } finally {
            icon.classList.remove('rotating');
        }
    }

    // --- Status & KPI ---
    async loadStatus() {
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();
            const badge = document.getElementById('gatewayStatusBadge');
            const text = document.getElementById('gatewayStatusText');
            const dot = badge.querySelector('.status-dot');

            const isOnline = data.collector?.router_online;
            if (isOnline) {
                dot.className = 'status-dot pulsing';
                text.textContent = `GL-MT2500 Online`;
            } else {
                dot.className = 'status-dot offline';
                text.textContent = 'Gateway Offline / Fehler';
            }
        } catch (e) {
            console.error('Failed to load status:', e);
        }
    }

    async loadSummary() {
        try {
            const resp = await fetch('/api/summary');
            const data = await resp.json();

            document.getElementById('kpiTotalQueries').textContent = (data.total_queries || 0).toLocaleString('de-DE');
            document.getElementById('kpiActiveClients').textContent = (data.active_clients || 0).toLocaleString('de-DE');
            document.getElementById('kpiUniqueDomains').textContent = (data.unique_domains || 0).toLocaleString('de-DE');
            document.getElementById('kpiBlockedQueries').textContent = (data.blocked_queries || 0).toLocaleString('de-DE');
            document.getElementById('kpiLatency').textContent = `${data.avg_latency_ms || 0} ms`;
        } catch (e) {
            console.error('Failed to load summary:', e);
        }
    }

    // --- Clients ---
    async loadClients(silent = false) {
        try {
            const resp = await fetch('/api/clients');
            this.clients = await resp.json();

            document.getElementById('clientsCount').textContent = this.clients.length;
            this.renderClientsList();

            // Select first client if none selected
            if (!this.selectedClientIp && this.clients.length > 0) {
                this.selectClient(this.clients[0]);
            }
        } catch (e) {
            console.error('Failed to load clients:', e);
        }
    }

    getDeviceIcon(name, ip) {
        const lower = (name + ' ' + ip).toLowerCase();
        if (lower.includes('phone') || lower.includes('p30') || lower.includes('redmi') || lower.includes('pixel') || lower.includes('galaxy') || lower.includes('mobile')) {
            return 'fa-mobile-screen-button';
        }
        if (lower.includes('homey') || lower.includes('bridge') || lower.includes('tuya') || lower.includes('shelly') || lower.includes('esp')) {
            return 'fa-microchip';
        }
        if (lower.includes('tv') || lower.includes('shield') || lower.includes('firetv') || lower.includes('chromecast')) {
            return 'fa-tv';
        }
        if (lower.includes('wlan0') || lower.includes('repeater') || lower.includes('ap')) {
            return 'fa-wifi';
        }
        return 'fa-desktop';
    }

    renderClientsList(filter = '') {
        const container = document.getElementById('clientsListContainer');
        const search = filter.toLowerCase().trim();

        const filtered = this.clients.filter(c => {
            if (!search) return true;
            return (c.name && c.name.toLowerCase().includes(search)) || c.ip.includes(search);
        });

        if (filtered.length === 0) {
            container.innerHTML = '<div class="empty-state">Keine passenden Geräte gefunden.</div>';
            return;
        }

        container.innerHTML = filtered.map(c => {
            const isSelected = c.ip === this.selectedClientIp ? 'selected' : '';
            const icon = this.getDeviceIcon(c.name, c.ip);
            const displayName = (c.name && c.name !== c.ip) ? c.name : c.ip;

            return `
                <div class="client-item ${isSelected}" data-ip="${c.ip}">
                    <div class="client-icon"><i class="fa-solid ${icon}"></i></div>
                    <div class="client-info">
                        <div class="client-name" title="${displayName}">${displayName}</div>
                        <div class="client-ip">${c.ip}</div>
                    </div>
                    <div class="client-stat-badge">
                        <span class="client-stat-count">${c.total_queries.toLocaleString('de-DE')}</span>
                        <span class="client-stat-label">${c.unique_domains || 0} Domains</span>
                    </div>
                </div>
            `;
        }).join('');

        // Attach click handlers
        container.querySelectorAll('.client-item').forEach(item => {
            item.addEventListener('click', () => {
                const ip = item.getAttribute('data-ip');
                const clientObj = this.clients.find(c => c.ip === ip);
                if (clientObj) {
                    this.selectClient(clientObj);
                }
            });
        });
    }

    selectClient(client) {
        this.selectedClientIp = client.ip;
        this.selectedClientData = client;

        // Update list UI
        document.querySelectorAll('.client-item').forEach(el => {
            el.classList.toggle('selected', el.getAttribute('data-ip') === client.ip);
        });

        // Update Header Banner
        const icon = this.getDeviceIcon(client.name, client.ip);
        document.getElementById('detailDeviceAvatar').innerHTML = `<i class="fa-solid ${icon}"></i>`;
        const displayName = (client.name && client.name !== client.ip) ? client.name : client.ip;
        document.getElementById('detailClientName').textContent = displayName;
        document.getElementById('detailClientIp').textContent = client.ip;
        document.getElementById('detailClientMeta').textContent = `Erstmals gesehen: ${this.formatTime(client.first_seen)} &bull; Zuletzt aktiv: ${this.formatTime(client.last_seen)}`;
        document.getElementById('detailTotalQueries').textContent = (client.total_queries || 0).toLocaleString('de-DE');
        document.getElementById('detailUniqueDomains').textContent = (client.unique_domains || 0).toLocaleString('de-DE');

        // Load Domains for this client
        this.loadClientDomains(client.ip);
    }

    async loadClientDomains(clientIp, silent = false) {
        const tbody = document.getElementById('clientDomainsTbody');
        if (!silent) {
            tbody.innerHTML = '<tr><td colspan="4" class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Lade Webadressen...</td></tr>';
        }

        try {
            const params = new URLSearchParams({
                status: this.domainFilter,
                sort: this.domainSort,
                limit: 100
            });
            if (this.domainSearch) {
                params.append('search', this.domainSearch);
            }

            const resp = await fetch(`/api/clients/${clientIp}/domains?${params.toString()}`);
            const data = await resp.json();

            const domains = data.domains || [];
            if (domains.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Keine Webadressen für dieses Gerät gefunden.</td></tr>';
                this.updateMiniChart([]);
                return;
            }

            // Update Table
            tbody.innerHTML = domains.map(d => {
                const statusBadge = d.is_blocked
                    ? `<span class="status-badge blocked"><i class="fa-solid fa-ban"></i> Blockiert</span>`
                    : `<span class="status-badge allowed"><i class="fa-solid fa-check"></i> Erlaubt</span>`;

                return `
                    <tr>
                        <td>
                            <div class="domain-cell">
                                <i class="fa-solid fa-globe domain-icon"></i>
                                <span class="domain-name" title="${d.domain}">${d.domain}</span>
                            </div>
                        </td>
                        <td>
                            <div class="count-cell">
                                <span class="count-badge">${d.count.toLocaleString('de-DE')}</span>
                                <div class="progress-bar-bg">
                                    <div class="progress-bar-fill" style="width: ${Math.min(100, d.percentage * 2)}%;"></div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <strong>${d.percentage}%</strong>
                        </td>
                        <td>
                            <span class="time-cell" title="${d.last_accessed}">${this.formatRelativeTime(d.last_accessed)}</span>
                        </td>
                    </tr>
                `;
            }).join('');

            // Update Mini Chart (Top 5)
            this.updateMiniChart(domains.slice(0, 5));

        } catch (e) {
            console.error('Failed to load client domains:', e);
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state text-danger">Fehler beim Laden der Webadressen.</td></tr>';
        }
    }

    // --- Tab 2: Network Top Domains ---
    async loadNetworkDomains(search = '') {
        const tbody = document.getElementById('networkDomainsTbody');
        try {
            const params = new URLSearchParams({ limit: 50 });
            if (search) params.append('search', search);

            const resp = await fetch(`/api/domains?${params.toString()}`);
            const list = await resp.json();

            if (!list || list.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Keine Domains im Netzwerk gefunden.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map((item, idx) => {
                return `
                    <tr>
                        <td style="color: var(--text-subtle); font-weight: 600;">#${idx + 1}</td>
                        <td>
                            <div class="domain-cell">
                                <i class="fa-solid fa-globe domain-icon"></i>
                                <span class="domain-name" title="${item.domain}">${item.domain}</span>
                            </div>
                        </td>
                        <td>
                            <strong style="color: var(--primary); font-size: 14px;">${item.total_count.toLocaleString('de-DE')}</strong>
                        </td>
                        <td>
                            <span class="badge" style="background: rgba(139, 92, 246, 0.15); color: var(--secondary);">
                                <i class="fa-solid fa-laptop"></i> ${item.client_count} Rechner
                            </span>
                        </td>
                        <td>
                            <span class="time-cell" title="${item.last_accessed}">${this.formatRelativeTime(item.last_accessed)}</span>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error('Failed to load network domains:', e);
        }
    }

    // --- Tab 3: Live Stream ---
    async loadLiveStream() {
        const tbody = document.getElementById('liveStreamTbody');
        try {
            const resp = await fetch('/api/activity?limit=40');
            const list = await resp.json();

            if (!list || list.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Noch keine Live-Aktivität aufgezeichnet.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map(item => {
                const isBlocked = item.status === 'NXDOMAIN' || (item.reason && item.reason.includes('BlackList'));
                const statusBadge = isBlocked
                    ? `<span class="status-badge blocked">Blockiert</span>`
                    : `<span class="status-badge allowed">Erlaubt</span>`;

                const timeStr = item.timestamp ? new Date(item.timestamp).toLocaleTimeString('de-DE') : '-';

                return `
                    <tr>
                        <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${timeStr}</td>
                        <td>
                            <div style="font-weight: 600; font-size: 13px;">${item.client_name || item.client_ip}</div>
                            <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-subtle);">${item.client_ip}</div>
                        </td>
                        <td>
                            <span class="domain-name" title="${item.domain}">${item.domain}</span>
                        </td>
                        <td>
                            <span class="badge" style="background: rgba(255,255,255,0.06); font-family: var(--font-mono);">${item.query_type || 'A'}</span>
                        </td>
                        <td>${statusBadge}</td>
                        <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${item.elapsed_ms ? item.elapsed_ms.toFixed(1) : '0'} ms</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error('Failed to load live stream:', e);
        }
    }

    // --- Tab 4: Trends & Charts ---
    initCharts() {
        // 1. Mini Chart for selected client
        const ctxMini = document.getElementById('clientMiniChart').getContext('2d');
        this.miniChart = new Chart(ctxMini, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Aufrufe',
                    data: [],
                    backgroundColor: 'rgba(6, 182, 212, 0.75)',
                    hoverBackgroundColor: 'rgba(6, 182, 212, 1)',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#152238',
                        titleColor: '#F8FAFC',
                        bodyColor: '#06B6D4',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94A3B8', font: { family: 'JetBrains Mono', size: 11 } },
                        grid: { display: false }
                    },
                    y: {
                        ticks: { color: '#64748B', font: { size: 10 } },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' }
                    }
                }
            }
        });

        // 2. Trend Chart (24h)
        const ctxTrend = document.getElementById('trendChartCanvas').getContext('2d');
        this.trendChart = new Chart(ctxTrend, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Anfragen pro Stunde',
                        data: [],
                        borderColor: '#06B6D4',
                        backgroundColor: 'rgba(6, 182, 212, 0.15)',
                        fill: true,
                        tension: 0.35,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Aktive Rechner',
                        data: [],
                        borderColor: '#8B5CF6',
                        backgroundColor: 'rgba(139, 92, 246, 0.15)',
                        fill: false,
                        borderDash: [5, 5],
                        tension: 0.35,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        labels: { color: '#94A3B8', font: { family: 'Outfit', size: 12 } }
                    },
                    tooltip: {
                        backgroundColor: '#152238',
                        titleColor: '#F8FAFC',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#94A3B8', font: { family: 'Inter', size: 11 } },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: { color: '#06B6D4', font: { size: 11 } },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#8B5CF6', font: { size: 11 } },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    updateMiniChart(topDomains) {
        if (!this.miniChart) return;
        this.miniChart.data.labels = topDomains.map(d => {
            const dom = d.domain;
            return dom.length > 25 ? dom.substring(0, 22) + '...' : dom;
        });
        this.miniChart.data.datasets[0].data = topDomains.map(d => d.count);
        this.miniChart.update();
    }

    async loadTrends() {
        if (!this.trendChart) return;
        try {
            const resp = await fetch('/api/trends?hours=24');
            const data = await resp.json();

            const labels = data.map(d => {
                const parts = d.hour_slot.split(' ');
                return parts[1] || d.hour_slot;
            });
            const queryCounts = data.map(d => d.query_count);
            const activeClients = data.map(d => d.active_clients);

            this.trendChart.data.labels = labels;
            this.trendChart.data.datasets[0].data = queryCounts;
            this.trendChart.data.datasets[1].data = activeClients;
            this.trendChart.update();
        } catch (e) {
            console.error('Failed to load trends:', e);
        }
    }

    // --- Helpers ---
    formatTime(isoString) {
        if (!isoString) return '-';
        try {
            const d = new Date(isoString);
            return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
        } catch {
            return isoString;
        }
    }

    formatRelativeTime(isoString) {
        if (!isoString) return '-';
        try {
            const d = new Date(isoString);
            const now = new Date();
            const diffSec = Math.floor((now - d) / 1000);

            if (diffSec < 5) return 'gerade eben';
            if (diffSec < 60) return `vor ${diffSec}s`;
            const diffMin = Math.floor(diffSec / 60);
            if (diffMin < 60) return `vor ${diffMin}m`;
            const diffHours = Math.floor(diffMin / 60);
            if (diffHours < 24) return `vor ${diffHours}h`;
            return d.toLocaleDateString('de-DE');
        } catch {
            return isoString;
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `
            <i class="fa-solid fa-circle-info" style="color: var(--primary);"></i>
            <span>${message}</span>
        `;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
}

// Instantiate on load
document.addEventListener('DOMContentLoaded', () => {
    window.gliApp = new GliNetMonitorApp();
});
