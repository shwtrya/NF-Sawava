// Password Visibility Toggle
function togglePasswordVisibility(inputId, btn) {
  const inp = document.getElementById(inputId);
  if (!inp) return;
  const isPw = (inp.type === 'password');
  inp.type = isPw ? 'text' : 'password';
  if (btn) {
    const eyeOpen = btn.querySelector('.eye-open');
    const eyeClosed = btn.querySelector('.eye-closed');
    if (eyeOpen && eyeClosed) {
      eyeOpen.style.display = isPw ? 'none' : 'block';
      eyeClosed.style.display = isPw ? 'block' : 'none';
    }
  }
}

// Email & Sensitive Data Masking Helper
function maskEmail(email) {
  if (!email || typeof email !== 'string') return '-';
  const parts = email.split('@');
  if (parts.length !== 2) return email;
  const user = parts[0];
  const domain = parts[1];
  if (user.length <= 2) {
    return user[0] + '***@' + domain;
  }
  const start = user.substring(0, 2);
  const end = user.length > 4 ? user.substring(user.length - 1) : '';
  return start + '****' + end + '@' + domain;
}

// HTML & Attribute Sanitization Helpers (XSS Protection)
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/'/g, "\\'")
    .replace(/"/g, '&quot;')
    .replace(/\n/g, ' ');
}

// Modern Enhanced Toast System
function showToast(msg, type) {
  const t = document.getElementById('toast');
  const msgEl = document.getElementById('toast-msg');
  if (!t || !msgEl) return;

  let iconHtml = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  let toastClass = 'toast-info';

  const m = String(msg).toLowerCase();
  if (type === 'error' || m.includes('gagal') || m.includes('error') || m.includes('invalid') || m.includes('dead') || m.includes('bad') || m.includes('✕')) {
    iconHtml = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    toastClass = 'toast-error';
  } else if (type === 'warn' || m.includes('warning') || m.includes('perhatian') || m.includes('⚠️') || m.includes('hold') || m.includes('locked')) {
    iconHtml = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
    toastClass = 'toast-warn';
  } else if (type === 'success' || m.includes('berhasil') || m.includes('disalin') || m.includes('live') || m.includes('sukses') || m.includes('✓') || m.includes('✅')) {
    iconHtml = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
    toastClass = 'toast-success';
  }

  const cleanMsg = msg.replace(/^[✓✕⚠✅❌📋\s]+/, '').trim();
  msgEl.textContent = cleanMsg || msg;

  t.className = 'toast ' + toastClass + ' show';
  const iconSpan = t.querySelector('span:first-child');
  if (iconSpan) iconSpan.innerHTML = iconHtml;

  if (window.toastTimer) clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => {
    t.classList.remove('show');
  }, 2800);
}


let bulkRunning = false;
let bulkResults = [];
let bulkFilter = 'ALL';
let chartStatusObj = null;
let chartCountryObj = null;
let chartPlanObj = null;

let curPage = 1;
const pageSize = 25;
let searchDebounce = null;

function getAuthHeaders(extra = {}) {
  const key = sessionStorage.getItem('suite_api_key') || '';
  const token = sessionStorage.getItem('dashboard_token') || '';
  const headers = {...extra};
  if (key) headers['X-API-Key'] = key;
  if (token) headers['X-Dashboard-Token'] = token;
  return headers;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  document.getElementById('toast-msg').innerText = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// Health check
async function checkServerHealth() {
  try {
    const res = await fetch('/api/health');
    const d = await res.json();
    const mins = Math.floor(d.uptime_seconds / 60);
    const badge = document.getElementById('server-health-badge');
    badge.innerText = `● Online (${mins}m)`;
    badge.style.color = 'var(--live)';
  } catch(e) {
    const badge = document.getElementById('server-health-badge');
    badge.innerText = '● Offline';
    badge.style.color = 'var(--dead)';
  }
}
setInterval(checkServerHealth, 30000);
checkServerHealth();

// PIN Security
async function checkPinStatus() {
  const badge = document.getElementById('pin-badge');
  const key = sessionStorage.getItem('suite_api_key');
  if (key) {
    badge.innerText = '🔑 Authenticated';
    badge.style.color = 'var(--live)';
  } else {
    badge.innerText = '🔑 API Key';
    badge.style.color = 'var(--text-muted)';
  }
}

async function verifyPin() {
  const key = document.getElementById('pin-input').value.trim();
  if (!key) return;
  try {
    const res = await fetch('/api/auth/status', { headers: { 'X-API-Key': key } });
    const d = await res.json();
    if (d.authenticated) {
      sessionStorage.setItem('suite_api_key', key);
      document.getElementById('pin-modal').style.display = 'none';
      document.getElementById('pin-err').style.display = 'none';
      showToast('✅ API Key authenticated');
      checkPinStatus();
    } else {
      document.getElementById('pin-err').style.display = 'block';
    }
  } catch(e) {
    document.getElementById('pin-err').style.display = 'block';
  }
}


// ═══ DASHBOARD PIN LOCK ═══
async function checkDashboardPinLock() {
  try {
    const res = await fetch('/api/dashboard-pin/status');
    const data = await res.json();
    if (data.enabled) {
      // Check if already unlocked this session
      if (sessionStorage.getItem('dashboard_unlocked') === '1') return;
      // Show lock screen
      const lockScreen = document.getElementById('dashboard-lock-screen');
      lockScreen.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      setTimeout(() => document.getElementById('dashboard-pin-unlock').focus(), 200);
    }
  } catch(e) {
    // If API fails, don't lock
  }
}

async function unlockDashboard() {
  const pin = document.getElementById('dashboard-pin-unlock').value.trim();
  const errEl = document.getElementById('dashboard-pin-error');
  if (!pin) { errEl.style.display = 'block'; errEl.innerText = 'Masukkan PIN!'; return; }
  try {
    const res = await fetch('/api/dashboard-pin/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: pin })
    });
    const data = await res.json();
    if (data.valid) {
      sessionStorage.setItem('dashboard_unlocked', '1');
      if (data.token) {
        sessionStorage.setItem('dashboard_token', data.token);
      }
      document.getElementById('dashboard-lock-screen').style.display = 'none';
      document.body.style.overflow = '';
      errEl.style.display = 'none';
    } else {
      errEl.style.display = 'block';
      errEl.innerText = 'PIN Salah!';
      document.getElementById('dashboard-pin-unlock').value = '';
      document.getElementById('dashboard-pin-unlock').focus();
    }
  } catch(e) {
    errEl.style.display = 'block';
    errEl.innerText = 'Error: ' + e.message;
  }
}

// Check PIN lock on page load
checkDashboardPinLock();

// managePin removed - API Key management is now in /admin panel

// Audio synthesize
function playAlert(type) {
  if (!document.getElementById('sound-toggle').checked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    if (type === '4k') {
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.15);
    } else if (type === 'hold') {
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(330, ctx.currentTime + 0.18);
    } else {
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
    }
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch(e) {}
}

function notifyBrowser(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    try {
      new Notification(title, { body });
    } catch(e) {}
  }
}
if ("Notification" in window && Notification.permission !== "denied") {
  try {
    const p = Notification.requestPermission();
    if (p && typeof p.catch === 'function') {
      p.catch(() => {});
    }
  } catch(e) {}
}

// Shortcuts
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') {
    const activeTab = document.querySelector('.section-panel.active').id;
    if (activeTab === 'panel-single') runSingle();
    if (activeTab === 'panel-bulk') runBulk();
  } else if (e.key === 'Escape') {
    stopBulk();
  }
});

let historyAutoRefresh = null;


function switchTab(tab) {
  // Auto-close mobile sidebar when switching tabs
  if (window.innerWidth <= 992) {
    toggleMobileSidebar(false);
  }
  const tabs = ['dashboard', 'checkers', 'single', 'disney', 'crunchyroll', 'expressvpn', 'spotify', 'outlook', 'openai', 'primevideo', 'bulk', 'history', 'analytics', 'proxymanager', 'settings'];

  // Toggle active on all matching buttons
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    const dataTab = btn.getAttribute('data-tab');
    const onclickStr = btn.getAttribute('onclick') || '';
    const match = onclickStr.match(/switchTab\('([^']+)'\)/);
    const targetTab = dataTab || (match ? match[1] : null);
    if (targetTab) {
      btn.classList.toggle('active', targetTab === tab);
    }
  });

  // Toggle checker top bar pills — dynamic single source of truth
  const CHECKER_PILLS = [
    { key: 'single',      label: 'Netflix Token' },
    { key: 'bulk',        label: 'Netflix Bulk' },
    { key: 'disney',      label: 'Disney+' },
    { key: 'crunchyroll', label: 'Crunchyroll' },
    { key: 'expressvpn',  label: 'ExpressVPN' },
    { key: 'spotify',     label: 'Spotify' },
    { key: 'outlook',     label: 'Outlook' },
    { key: 'openai',      label: 'OpenAI' },
    { key: 'primevideo',  label: 'PrimeVideo' },
  ];
  document.querySelectorAll('.checker-quick-tabs').forEach(container => {
    container.innerHTML = CHECKER_PILLS.map(p =>
      `<button type="button" class="checker-pill ${p.key === tab ? 'active' : ''}" onclick="switchTab('${p.key}')">${p.label}</button>`
    ).join('');
  });

  // Toggle active on mobile bottom nav buttons
  document.querySelectorAll('.mobile-nav-item').forEach(btn => {
    const dataTab = btn.getAttribute('data-tab');
    if (dataTab) {
      btn.classList.toggle('active', dataTab === tab);
    }
  });

  // Toggle active on panel elements
  tabs.forEach(t => {
    const el = document.getElementById(`panel-${t}`);
    if (el) {
      const isActive = (t === tab);
      el.classList.toggle('active', isActive);
    }
  });

  // Dynamic Page Header & Breadcrumb
  if (typeof updateViewHeader === 'function') {
    updateViewHeader(tab);
  }

  // Refresh dashboard metrics when navigating to dashboard or checkers
  if (tab === 'dashboard' || tab === 'checkers') {
    fetchDashboardData();
  }

  // Theme switching
  const container = document.querySelector('.container');
  if (container) {
    container.classList.remove('disney-theme', 'crunchyroll-theme', 'expressvpn-theme', 'spotify-theme', 'outlook-theme', 'openai-theme', 'primevideo-theme');
  }
  document.body.classList.remove('disney-body', 'crunchyroll-body', 'expressvpn-body', 'spotify-body', 'outlook-body', 'openai-body', 'primevideo-body');
  if (tab === 'disney') {
    if (container) container.classList.add('disney-theme');
    document.body.classList.add('disney-body');
  } else if (tab === 'crunchyroll') {
    if (container) container.classList.add('crunchyroll-theme');
    document.body.classList.add('crunchyroll-body');
  } else if (tab === 'expressvpn') {
    if (container) container.classList.add('expressvpn-theme');
    document.body.classList.add('expressvpn-body');
  } else if (tab === 'spotify') {
    if (container) container.classList.add('spotify-theme');
    document.body.classList.add('spotify-body');
  } else if (tab === 'outlook') {
    if (container) container.classList.add('outlook-theme');
    document.body.classList.add('outlook-body');
  } else if (tab === 'openai') {
    if (container) container.classList.add('openai-theme');
    document.body.classList.add('openai-body');
  } else if (tab === 'primevideo') {
    if (container) container.classList.add('primevideo-theme');
    document.body.classList.add('primevideo-body');
  }

  // Clear history auto-refresh when switching away
  if (historyAutoRefresh) { clearInterval(historyAutoRefresh); historyAutoRefresh = null; }

  if (tab === 'dashboard') {
    fetchDashboardData();
  }
  if (tab === 'checkers') {
    fetchDashboardData();
  }
  if (tab === 'history') {
    loadHistory();
    historyAutoRefresh = setInterval(() => loadHistory(), 30000);
  }
  if (tab === 'analytics') loadAnalytics();
  if (tab === 'proxymanager') pmRefresh();
  if (tab === 'bulk') updateBulkCount();

  // Close mobile sidebar if open
  if (window.innerWidth <= 992) {
    toggleMobileSidebar(false);
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}


function toggleSingleMode() {
  // Mode switch merged into unified single checker
}

async function fetchStats() {
  try {
    const res = await fetch('/api/proxies');
    const d = await res.json();
    const lbl = document.getElementById('proxy-count-label');
    if (lbl) {
      if (d.healthy > 0) {
        lbl.innerHTML = `<span style="color:var(--live); font-weight:bold;">●</span> <b>${Number(d.healthy).toLocaleString('id-ID')}</b> / ${Number(d.total).toLocaleString('id-ID')} Proxy Live`;
        lbl.style.borderColor = 'var(--live-border)';
        lbl.style.background = 'var(--live-bg)';
        lbl.style.color = 'var(--text-main)';
      } else if (d.total > 0) {
        lbl.innerHTML = `<span style="color:#eab308; font-weight:bold;">●</span> <b>${Number(d.total).toLocaleString('id-ID')}</b> Proxy Pool (Ready)`;
        lbl.style.borderColor = 'rgba(234, 179, 8, 0.3)';
        lbl.style.background = 'rgba(234, 179, 8, 0.08)';
        lbl.style.color = 'var(--text-main)';
      } else {
        lbl.innerHTML = `<span style="color:var(--dead); font-weight:bold;">●</span> 0 Proxy Pool`;
        lbl.style.borderColor = 'var(--dead-border)';
        lbl.style.background = 'var(--dead-bg)';
        lbl.style.color = 'var(--text-muted)';
      }
    }
  } catch(e) {}
}

// Extract and build launch links for browser, android, and tv
function buildLaunchLinks(tokOrUrl) {
  if (!tokOrUrl) return { browser: '', android: '', tv: '', token: '' };
  let tok = String(tokOrUrl).trim();
  if (tok.includes('nftoken=')) {
    const m = tok.match(/[?&]nftoken=([^&]+)/);
    if (m) tok = m[1];
  }
  if (!tok || tok === 'undefined' || tok === 'null') {
    return { browser: '', android: '', tv: '', token: '' };
  }
  return {
    browser: `https://netflix.com/?nftoken=${tok}`,
    android: `https://netflix.com/unsupported?nftoken=${tok}`,
    tv: `https://netflix.com/tv2?nftoken=${tok}`,
    token: tok
  };
}

async function runSingle() {
  const cookie = document.getElementById('single-cookie').value.trim();
  const use_proxy = document.getElementById('proxy-toggle').checked;
  const out = document.getElementById('single-out');
  const btn = document.getElementById('single-btn');

  if (!cookie) { showToast('Masukkan cookie terlebih dahulu'); return; }

  btn.disabled = true;
  out.style.display = 'none';

  try {
    const res = await fetch('/api/check', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({cookie, use_proxy})
    });
    const d = await res.json();
    window.currentSingleCheckResult = d;
    window.currentSingleCookieRaw = cookie;

    if (!d.live && d.status !== 'HOLD' && !d.is_hold) throw new Error(d.reason || 'Akun Dead / Tidak Valid');
    const isHold = (d.status === 'HOLD' || d.is_hold);
    if (isHold) playAlert('hold');
    else if (d.plan && d.plan.includes('4K')) playAlert('4k');
    else playAlert('live');

    let tokUrl = '';
    let androidUrl = '';
    let tvUrl = '';
    let expStr = '-';

    let launch = null;
    if (d.token_data) {
      launch = buildLaunchLinks(d.token_data.token || d.token_data.url);
      expStr = d.token_data.expires || '-';
    }

    if (!launch || !launch.browser) {
      // Fallback request to /api/token if token_data wasn't bundled
      try {
        const resTok = await fetch('/api/token', {
          method: 'POST',
          headers: getAuthHeaders({'Content-Type': 'application/json'}),
          body: JSON.stringify({cookie, use_proxy})
        });
        const dTok = await resTok.json();
        if (dTok.url || dTok.token) {
          launch = buildLaunchLinks(dTok.token || dTok.url);
          expStr = dTok.expires || '-';
        }
      } catch(e) {}
    }

    if (launch && launch.browser) {
      tokUrl = launch.browser;
      androidUrl = launch.android;
      tvUrl = launch.tv;
    }

    out.className = isHold ? 'card-out hold' : 'card-out live';
    out.innerHTML = `
      <div class="card-header-status" style="color:${isHold ? 'var(--hold)' : 'var(--live)'};">
        <span style="font-size:20px;">${isHold ? '⏸' : '✅'}</span>
        <span>${isHold ? 'Membership Paused / On Hold' : 'Akun Live — Token Siap'}</span>
      </div>

      ${isHold ? `
      <div style="background:rgba(245, 158, 11, 0.08); border:1px solid rgba(245, 158, 11, 0.2); color:#fcd34d; padding:12px 16px; border-radius:10px; margin-bottom:14px; font-size:12px; display:flex; align-items:flex-start; gap:10px; line-height:1.5;">
        <span style="font-size:16px; flex-shrink:0; margin-top:1px;">⚠️</span>
        <span><strong>Hold:</strong> Membership dijeda. Perlu metode pembayaran baru untuk melanjutkan streaming.</span>
      </div>
      ` : ''}

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong style="color:#e2e8f0">${escapeHtml(d.email || 'Netflix Member')}</strong></div>
        <div class="meta-box"><span>Plan</span><strong style="color:var(--accent-4k)">${escapeHtml(d.plan || 'N/A')}</strong></div>
        <div class="meta-box"><span>Country</span><strong>${escapeHtml(d.country || 'N/A')}</strong></div>
        <div class="meta-box"><span>Billing</span><strong style="${isHold ? 'color:var(--hold)' : 'color:var(--live)'}">${escapeHtml(d.billing || 'N/A')}</strong></div>
        <div class="meta-box"><span>Profiles</span><strong>${escapeHtml((d.profiles && d.profiles.length) ? d.profiles.join(', ') : 'N/A')}</strong></div>
        <div class="meta-box"><span>Route</span><strong>${escapeHtml(d.route || 'Direct')}</strong></div>
      </div>

      ${tokUrl ? `
      <div style="margin-top:16px;">
        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:10px;">🔗 Launcher Links</div>
        <div style="display:flex; flex-direction:column; gap:8px;">
          <div class="launcher-card">
            <div class="launcher-card-header">
              <span class="launcher-card-label" style="color:#38bdf8;">🌐 Browser</span>
              <button class="btn-secondary" style="padding:4px 10px; font-size:10.5px;" onclick="copyText('${tokUrl}', '✓ Browser Link')">📋 Copy</button>
            </div>
            <div class="token-link"><a href="${tokUrl}" target="_blank">${tokUrl}</a></div>
          </div>
          <div class="launcher-card">
            <div class="launcher-card-header">
              <span class="launcher-card-label" style="color:#4ade80;">📱 Android</span>
              <button class="btn-secondary" style="padding:4px 10px; font-size:10.5px;" onclick="copyText('${androidUrl}', '✓ Android Link')">📋 Copy</button>
            </div>
            <div class="token-link"><a href="${androidUrl}" target="_blank">${androidUrl}</a></div>
          </div>
          <div class="launcher-card">
            <div class="launcher-card-header">
              <span class="launcher-card-label" style="color:#a855f7;">📺 Smart TV</span>
              <button class="btn-secondary" style="padding:4px 10px; font-size:10.5px;" onclick="copyText('${tvUrl}', '✓ TV Link')">📋 Copy</button>
            </div>
            <div class="token-link"><a href="${tvUrl}" target="_blank">${tvUrl}</a></div>
          </div>
        </div>
      </div>
      ` : ''}

      <div class="action-btns">
        <button class="btn-secondary" onclick="copySingleCookieJson()">📋 Cookie JSON</button>
        <button class="btn-secondary" onclick="copySingleRawCookie()">📋 Cookie Raw</button>
        ${tokUrl ? `<button class="btn-secondary" onclick="copyText('${tokUrl}', '✓ Disalin')">🌐 Browser URL</button>` : ''}
        ${androidUrl ? `<button class="btn-secondary" onclick="copyText('${androidUrl}', '✓ Disalin')">📱 Android URL</button>` : ''}
        ${tvUrl ? `<button class="btn-secondary" onclick="copyText('${tvUrl}', '✓ Disalin')">📺 TV URL</button>` : ''}
      </div>
    `;
    out.style.display = 'block';
  } catch(e) {
    out.className = 'card-out dead';
    out.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Akun Dead / Tidak Valid</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px; line-height:1.5; padding:8px 0;">${escapeHtml(e.message)}</div>
    `;
    out.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

// ---- Concurrent Bulk File Upload & Smart Cookie Parser ----

function getCookieFingerprintClient(str) {
  if (!str) return '';
  str = String(str).trim();
  const ctMatch = str.match(/ct(?:%3D|=)([^&;"\s]+)/);
  if (ctMatch) return 'ct:' + ctMatch[1];
  const nidMatch = str.match(/NetflixId(?:%3D|=)([^;,\s]+)/);
  if (nidMatch) return 'nid:' + nidMatch[1];
  const jsonNid = str.match(/"name":\s*"NetflixId"[^}]*?"value":\s*"([^"]+)"/);
  if (jsonNid) {
    const val = jsonNid[1];
    const ct = val.match(/ct(?:%3D|=)([^&]+)/);
    return ct ? 'ct:' + ct[1] : 'nid:' + val;
  }
  return str.substring(0, 80);
}

function extractCookiesFromContent(content, fileName = '') {
  if (!content) return [];
  content = content.trim();
  if (!content) return [];

  // 1. JSON Array (Cookie-Editor format or Array of Accounts)
  if (content.startsWith('[') && content.endsWith(']')) {
    try {
      const parsed = JSON.parse(content);
      if (Array.isArray(parsed) && parsed.length > 0) {
        // Nested array: multiple accounts
        if (Array.isArray(parsed[0])) {
          const list = [];
          parsed.forEach(sub => {
            if (Array.isArray(sub) && sub.some(c => c && (c.name === 'NetflixId' || c.key === 'NetflixId'))) {
              list.push(JSON.stringify(sub));
            }
          });
          if (list.length > 0) return list;
        }
        // Single Account cookie array (Cookie-Editor / J2TEAM)
        if (typeof parsed[0] === 'object' && (parsed[0].name || parsed[0].key)) {
          const hasNid = parsed.some(c => c && (c.name === 'NetflixId' || c.key === 'NetflixId'));
          if (hasNid) {
            return [JSON.stringify(parsed)];
          }
        }
      }
    } catch(e) {}
  }

  // 2. Line-delimited JSON arrays (e.g. 65x / 407x lists)
  const rawLines = content.split('\n').map(l => l.trim()).filter(Boolean);
  const jsonLines = rawLines.filter(l => l.startsWith('[') && l.endsWith(']') && l.includes('NetflixId'));
  if (jsonLines.length > 0 && jsonLines.length >= rawLines.length * 0.5) {
    return jsonLines;
  }

  // 3. Multi-account structured blocks (HIT #, Account Details:, etc.)
  if (content.includes('HIT #') || content.includes('Cookie:') || content.includes('NETFLIX ACCOUNT DETAILS') || content.includes('COOKIE (browser import') || content.includes('═════') || content.includes('█████')) {
    const blocks = content.split(/(?:={10,}|█{5,}|═{5,}|-{10,})/g);
    const blockResults = [];
    for (const b of blocks) {
      const s = b.trim();
      if (!s) continue;
      const jm = s.match(/\[\s*\{[\s\S]*?\}\s*\]/);
      if (jm && jm[0].includes('NetflixId')) {
        blockResults.push(jm[0].replace(/\s+/g, ' '));
        continue;
      }
      const cm = s.match(/(?:Cookie:\s*)?(NetflixId=[^\s;,\r\n]+)/);
      if (cm) {
        blockResults.push(cm[1].trim());
        continue;
      }
    }
    if (blockResults.length > 0) return blockResults;
  }

  // 4. Netscape HTTP Cookie format (.netflix.com\tTRUE\t...)
  const isNetscape = rawLines.some(l => l.includes('.netflix.com') && l.split('\t').length >= 7);
  if (isNetscape) {
    const nidLines = rawLines.filter(l => l.includes('\tNetflixId\t'));
    if (nidLines.length <= 1) {
      // Entire file represents 1 account
      const cks = {};
      rawLines.forEach(l => {
        const parts = l.split('\t');
        if (parts.length >= 7) {
          cks[parts[5]] = parts[6];
        }
      });
      if (cks['NetflixId']) {
        const partsStr = Object.keys(cks)
          .filter(k => ['NetflixId', 'SecureNetflixId', 'nfvdid', 'OptanonConsent'].includes(k))
          .map(k => k + '=' + cks[k]);
        return [partsStr.join('; ')];
      }
    } else {
      // Multiple accounts in one Netscape file
      const blocks = content.split(/(?=# =|# Netscape|\n\s*\n)/);
      const multi = [];
      blocks.forEach(b => {
        const bLines = b.trim().split('\n');
        const cks = {};
        bLines.forEach(l => {
          const parts = l.trim().split('\t');
          if (parts.length >= 7) cks[parts[5]] = parts[6];
        });
        if (cks['NetflixId']) {
          const partsStr = Object.keys(cks)
            .filter(k => ['NetflixId', 'SecureNetflixId', 'nfvdid'].includes(k))
            .map(k => k + '=' + cks[k]);
          multi.push(partsStr.join('; '));
        }
      });
      if (multi.length > 0) return multi;
    }
  }

  // 5. Line-by-line fallback
  return rawLines.filter(l => {
    if (l.startsWith('#') || l.startsWith('[{CHECK') || l.startsWith('TIME:')) return false;
    return l.includes('NetflixId') || (l.startsWith('[') && l.endsWith(']'));
  });
}

function parseCookieInputs(text) {
  return extractCookiesFromContent(text);
}

function updateBulkCount() {
  const textarea = document.getElementById('bulk-input');
  const countBadge = document.getElementById('bulk-input-count');
  if (!textarea || !countBadge) return;
  const raw = textarea.value.trim();
  if (!raw) {
    countBadge.textContent = '0 akun';
    countBadge.style.color = 'var(--text-muted)';
    return;
  }
  const lines = parseCookieInputs(raw);
  countBadge.textContent = `${lines.length} akun`;
  countBadge.style.color = lines.length > 0 ? '#4ade80' : 'var(--text-muted)';
}

function clearBulkInput() {
  const textarea = document.getElementById('bulk-input');
  if (textarea) textarea.value = '';
  const fileInfo = document.getElementById('bulk-file-info');
  if (fileInfo) {
    fileInfo.style.display = 'none';
    fileInfo.textContent = '';
  }
  const clearBtn = document.getElementById('bulk-clear-files-btn');
  if (clearBtn) clearBtn.style.display = 'none';
  const finp = document.getElementById('bulk-file-input');
  if (finp) finp.value = '';
  const dirinp = document.getElementById('bulk-folder-input');
  if (dirinp) dirinp.value = '';
  updateBulkCount();
  showToast('Input bulk dibersihkan');
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.onerror = (e) => reject(e);
    reader.readAsText(file, 'utf-8');
  });
}

function traverseFileTree(item) {
  return new Promise((resolve) => {
    if (item.isFile) {
      item.file(file => resolve([file]), () => resolve([]));
    } else if (item.isDirectory) {
      const dirReader = item.createReader();
      const entries = [];
      const readEntries = () => {
        dirReader.readEntries(results => {
          if (!results.length) {
            Promise.all(entries.map(traverseFileTree)).then(sub => {
              resolve(sub.flat());
            });
          } else {
            entries.push(...results);
            readEntries();
          }
        }, () => resolve([]));
      };
      readEntries();
    } else {
      resolve([]);
    }
  });
}

async function getAllFilesFromDataTransfer(dt) {
  const files = [];
  if (dt.items && dt.items.length > 0) {
    const queue = [];
    for (let i = 0; i < dt.items.length; i++) {
      const item = dt.items[i];
      if (item.kind === 'file') {
        const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        if (entry) {
          queue.push(traverseFileTree(entry));
        } else {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
    }
    if (queue.length > 0) {
      const nested = await Promise.all(queue);
      nested.flat().forEach(f => {
        if (f) files.push(f);
      });
      return files;
    }
  }
  return Array.from(dt.files || []);
}

async function handleBulkDrop(e) {
  e.preventDefault();
  e.stopPropagation();
  const dropZone = document.getElementById('bulk-drop-zone');
  if (dropZone) {
    dropZone.style.borderColor = 'var(--border)';
    dropZone.style.background = 'var(--bg-subtle)';
  }
  const dt = e.dataTransfer;
  if (!dt) return;
  const files = await getAllFilesFromDataTransfer(dt);
  if (files && files.length > 0) {
    handleBulkFiles(files);
  }
}

async function handleBulkFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('bulk-file-info');
  const textarea = document.getElementById('bulk-input');
  const clearBtn = document.getElementById('bulk-clear-files-btn');

  // Filter allowed files (.txt, .json, .cookie, .cookies or extensionless)
  const validFiles = Array.from(files).filter(f => {
    const name = f.name.toLowerCase();
    return name.endsWith('.txt') || name.endsWith('.json') || name.endsWith('.cookie') || name.endsWith('.cookies') || !name.includes('.');
  });

  if (!validFiles.length) {
    showToast('Tidak ada file .txt / .json / .cookie yang valid');
    return;
  }

  if (fileInfo) {
    fileInfo.style.display = 'block';
    fileInfo.style.color = 'var(--primary)';
    fileInfo.textContent = `⏳ Membaca ${validFiles.length} file...`;
  }

  const seenFingerprints = new Set();
  const currentText = textarea.value.trim();
  if (currentText) {
    const existing = parseCookieInputs(currentText);
    existing.forEach(c => {
      const fp = getCookieFingerprintClient(c);
      if (fp) seenFingerprints.add(fp);
    });
  }

  const newCookies = [];
  let duplicates = 0;

  for (let i = 0; i < validFiles.length; i++) {
    const file = validFiles[i];
    try {
      const content = await readFileAsText(file);
      if (!content || !content.trim()) continue;

      const extracted = extractCookiesFromContent(content, file.name);
      for (const item of extracted) {
        const fp = getCookieFingerprintClient(item);
        if (fp && seenFingerprints.has(fp)) {
          duplicates++;
        } else {
          if (fp) seenFingerprints.add(fp);
          newCookies.push(item);
        }
      }
    } catch (err) {
      console.error(`Error reading ${file.name}:`, err);
    }
  }

  if (newCookies.length > 0) {
    if (textarea.value.trim()) {
      textarea.value = textarea.value.trim() + '\n' + newCookies.join('\n');
    } else {
      textarea.value = newCookies.join('\n');
    }
  }

  updateBulkCount();

  const totalInTextarea = parseCookieInputs(textarea.value).length;

  if (fileInfo) {
    fileInfo.style.display = 'block';
    let msg = `✅ ${validFiles.length} file dimuat → +${newCookies.length} akun baru ditambahkan (Total: ${totalInTextarea} akun)`;
    if (duplicates > 0) msg += ` • ${duplicates} duplikat dilewati`;
    fileInfo.textContent = msg;
    fileInfo.style.color = '#10b981';
  }
  if (clearBtn) clearBtn.style.display = 'inline-block';

  showToast(`${newCookies.length} akun dari ${validFiles.length} file siap dicheck`);

  const finp = document.getElementById('bulk-file-input');
  if (finp) finp.value = '';
  const dirinp = document.getElementById('bulk-folder-input');
  if (dirinp) dirinp.value = '';
}

async function runBulk() {
  const text = document.getElementById('bulk-input').value.trim();
  if (!text) { showToast('Isi baris cookie terlebih dahulu'); return; }
  const rawLines = parseCookieInputs(text);
  if (rawLines.length === 0) { showToast('Tidak ditemukan format cookie Netflix yang valid'); return; }

  // Deduplication check
  const seen = new Set();
  const lines = [];
  let duplicates = 0;
  for (const l of rawLines) {
    // extract key or fingerprint
    const key = getCookieFingerprintClient(l);
    if (key && seen.has(key)) {
      duplicates++;
    } else {
      if (key) seen.add(key);
      lines.push(l);
    }
  }

  if (duplicates > 0) {
    showToast(`Ditemukan ${duplicates} cookie duplikat, dilewati otomatis`);
  }

  const use_proxy = document.getElementById('proxy-toggle').checked;
  const concurrency = parseInt(document.getElementById('bulk-threads').value, 10) || 5;

  bulkRunning = true;
  bulkResults = [];
  document.getElementById('bulk-btn').disabled = true;
  document.getElementById('bulk-progress').style.display = 'block';
  document.getElementById('bulk-tbody').innerHTML = '';

  let live = 0, fourk = 0, hold = 0, dead = 0, completed = 0;
  document.getElementById('stat-total').innerText = lines.length;
  document.getElementById('stat-live').innerText = '0';
  document.getElementById('stat-hold').innerText = '0';
  document.getElementById('stat-4k').innerText = '0';
  document.getElementById('stat-dead').innerText = '0';

  let currentIndex = 0;

  async function worker() {
    while (currentIndex < lines.length && bulkRunning) {
      const idx = currentIndex++;
      const line = lines[idx];

      try {
        const res = await fetch('/api/check', {
          method: 'POST',
          headers: getAuthHeaders({'Content-Type': 'application/json'}),
          body: JSON.stringify({cookie: line, use_proxy})
        });
        const d = await res.json();
        const item = { index: idx + 1, raw: line, ...d };
        bulkResults.push(item);

        if (d.status === 'HOLD' || d.is_hold) {
          hold++;
          item.status = 'HOLD';
          item.is_hold = true;
          playAlert('hold');
        } else if (d.live) {
          live++;
          item.status = 'LIVE';
          const isUltra = (d.plan && (d.plan.includes('4K') || d.plan.includes('ULTRA')));
          if (isUltra) {
            fourk++;
            playAlert('4k');
          } else {
            playAlert('live');
          }
        } else {
          dead++;
          item.status = 'DEAD';
        }
        appendBulkRow(item);
      } catch(e) {
        dead++;
        appendBulkRow({ index: idx + 1, status: 'DEAD', live: false, plan: e.message || 'Error', billing: '-', country: '-', route: '-' });
      }

      completed++;
      const pct = Math.round((completed / lines.length) * 100);
      document.getElementById('progress-status').innerText = `⏳ Memeriksa ${completed}/${lines.length}...`;
      document.getElementById('progress-percent').innerText = `${pct}%`;
      document.getElementById('progress-fill').style.width = `${pct}%`;

      document.getElementById('stat-live').innerText = live;
      document.getElementById('stat-hold').innerText = hold;
      document.getElementById('stat-4k').innerText = fourk;
      document.getElementById('stat-dead').innerText = dead;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);

  flushBulkRowBuffer();
  renderBulkFilteredRows();

  bulkRunning = false;
  document.getElementById('bulk-btn').disabled = false;
  notifyBrowser('Bulk Check Selesai', `Total: ${lines.length} | Live: ${live} | Hold: ${hold} | 4K: ${fourk}`);
  showToast(`Bulk Check Selesai: ${live} Live, ${hold} Hold, ${dead} Dead`);

  // Dispatch webhook summary to Telegram / Discord
  try {
    fetch('/api/notifications/bulk-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(typeof getAuthHeaders === 'function' ? getAuthHeaders() : {}) },
      body: JSON.stringify({
        total: lines.length,
        live: live,
        four_k: fourk,
        hold: hold,
        dead: dead
      })
    }).catch(() => {});
  } catch (e) {}
}

function stopBulk() {
  if (bulkRunning) {
    bulkRunning = false;
    flushBulkRowBuffer();
    renderBulkFilteredRows();
    showToast('Proses bulk dihentikan');
  }
}

// Detect single cookie format in realtime
function detectSingleCookieFormat() {
  const text = document.getElementById('single-cookie').value.trim();
  const badge = document.getElementById('single-format-badge');
  if (!text) {
    badge.innerHTML = '<span>Format: Belum ada input</span>';
    badge.style.color = 'var(--text-muted)';
    return;
  }
  if (text.startsWith('[') && text.endsWith(']')) {
    try {
      const arr = JSON.parse(text);
      if (Array.isArray(arr)) {
        const hasNid = arr.some(c => (c.name === 'NetflixId' || c.key === 'NetflixId'));
        badge.innerHTML = hasNid ? '<span>✓ Format: JSON Cookie-Editor (Valid NetflixId)</span>' : '<span>⚠ Format: JSON Array (NetflixId Tidak Ditemukan)</span>';
        badge.style.color = hasNid ? '#4ade80' : '#f59e0b';
        return;
      }
    } catch(e) {}
  }
  if (text.includes('\t.netflix.com\t') || text.includes('.netflix.com\tTRUE\t') || text.includes('# Netscape HTTP Cookie File')) {
    badge.innerHTML = '<span>✓ Format: Netscape Cookie File</span>';
    badge.style.color = '#38bdf8';
    return;
  }
  if (text.includes('NetflixId=')) {
    badge.innerHTML = '<span>✓ Format: Raw Cookie Header (NetflixId Ada)</span>';
    badge.style.color = '#4ade80';
    return;
  }
  if (text.includes('NETFLIX ACCOUNT DETAILS') || text.includes('███')) {
    badge.innerHTML = '<span>✓ Format: Structured Account Combo Block</span>';
    badge.style.color = '#a855f7';
    return;
  }
  badge.innerHTML = '<span>⚠ Format: Teks Bebas (Mungkin tidak valid)</span>';
  badge.style.color = '#f59e0b';
}

// Bulk check virtual windowing & throttled rendering state
let bulkWindowLimit = 100;
let bulkPendingQueue = [];
let bulkRenderTimer = null;
let bulkEventSource = null;

function setBulkFilter(filter) {
  bulkFilter = filter;
  bulkWindowLimit = 100; // Reset window limit when changing filter
  ['all', 'live', 'hold', '4k', 'dead'].forEach(f => {
    const el = document.getElementById(`btn-filter-${f}`);
    if (el) el.style.background = (filter.toLowerCase() === f) ? 'var(--bg-subtle)' : 'transparent';
  });
  renderBulkFilteredRows();
}

function getFilteredBulkResults() {
  return bulkResults.filter(item => {
    const isHold = (item.status === 'HOLD' || item.is_hold);
    const isLive = (item.status === 'LIVE' || (item.live && !isHold));
    if (bulkFilter === 'ALL') return true;
    if (bulkFilter === 'LIVE') return isLive;
    if (bulkFilter === 'HOLD') return isHold;
    if (bulkFilter === 'DEAD') return (!isLive && !isHold);
    if (bulkFilter === '4K') return isLive && (item.plan && (item.plan.includes('4K') || item.plan.includes('ULTRA')));
    return true;
  });
}

function renderBulkFilteredRows() {
  const tbody = document.getElementById('bulk-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const filtered = getFilteredBulkResults();
  const total = filtered.length;

  const slice = filtered.slice(0, bulkWindowLimit);
  const frag = document.createDocumentFragment();
  slice.forEach(item => {
    const tr = createBulkRowElement(item);
    frag.appendChild(tr);
  });
  tbody.appendChild(frag);

  if (total > bulkWindowLimit) {
    const moreTr = document.createElement('tr');
    moreTr.id = 'bulk-load-more-row';
    moreTr.innerHTML = `
      <td colspan="7" style="text-align:center; padding:12px; background:rgba(255,255,255,0.03);">
        <span style="font-size:12px; color:var(--text-muted); margin-right:8px;">Menampilkan ${bulkWindowLimit} dari ${total} hasil</span>
        <button class="btn-secondary" style="padding:4px 12px; font-size:11px; border-radius:6px;" onclick="loadMoreBulkRows()">Tampilkan 100 Lagi</button>
        <button class="btn-secondary" style="padding:4px 12px; font-size:11px; border-radius:6px; margin-left:4px;" onclick="loadAllBulkRows()">Tampilkan Semua (${total})</button>
      </td>
    `;
    tbody.appendChild(moreTr);
  }
}

function loadMoreBulkRows() {
  bulkWindowLimit += 100;
  renderBulkFilteredRows();
}

function loadAllBulkRows() {
  bulkWindowLimit = bulkResults.length + 10;
  renderBulkFilteredRows();
}

function appendBulkRow(item) {
  bulkPendingQueue.push(item);
  if (!bulkRenderTimer) {
    bulkRenderTimer = requestAnimationFrame(() => {
      flushBulkRowBuffer();
      bulkRenderTimer = null;
    });
  }
}

function flushBulkRowBuffer() {
  if (bulkPendingQueue.length === 0) return;
  const items = bulkPendingQueue.splice(0, bulkPendingQueue.length);
  const tbody = document.getElementById('bulk-tbody');
  if (!tbody) return;

  const frag = document.createDocumentFragment();
  items.forEach(item => {
    const isHold = (item.status === 'HOLD' || item.is_hold);
    const isLive = (item.status === 'LIVE' || (item.live && !isHold));
    let visible = true;
    if (bulkFilter === 'LIVE') visible = isLive;
    else if (bulkFilter === 'HOLD') visible = isHold;
    else if (bulkFilter === 'DEAD') visible = (!isLive && !isHold);
    else if (bulkFilter === '4K') visible = isLive && (item.plan && (item.plan.includes('4K') || item.plan.includes('ULTRA')));

    if (visible) {
      const tr = createBulkRowElement(item);
      frag.insertBefore(tr, frag.firstChild);
    }
  });

  if (frag.childNodes.length > 0) {
    tbody.insertBefore(frag, tbody.firstChild);

    // Keep DOM bounded to bulkWindowLimit to maintain 60 FPS
    const currentRows = tbody.querySelectorAll('tr:not(#bulk-load-more-row)');
    if (currentRows.length > bulkWindowLimit) {
      for (let i = bulkWindowLimit; i < currentRows.length; i++) {
        currentRows[i].remove();
      }
      if (!document.getElementById('bulk-load-more-row')) {
        const total = getFilteredBulkResults().length;
        const moreTr = document.createElement('tr');
        moreTr.id = 'bulk-load-more-row';
        moreTr.innerHTML = `
          <td colspan="7" style="text-align:center; padding:12px; background:rgba(255,255,255,0.03);">
            <span style="font-size:12px; color:var(--text-muted); margin-right:8px;">Menampilkan ${bulkWindowLimit} dari ${total} hasil</span>
            <button class="btn-secondary" style="padding:4px 12px; font-size:11px; border-radius:6px;" onclick="loadMoreBulkRows()">Tampilkan 100 Lagi</button>
            <button class="btn-secondary" style="padding:4px 12px; font-size:11px; border-radius:6px; margin-left:4px;" onclick="loadAllBulkRows()">Tampilkan Semua (${total})</button>
          </td>
        `;
        tbody.appendChild(moreTr);
      }
    }
  }
}

function connectBulkSSE(sessionId) {
  if (!window.EventSource) return;
  if (bulkEventSource) {
    try { bulkEventSource.close(); } catch(e) {}
  }
  try {
    bulkEventSource = new EventSource('/api/stream/bulk?session_id=' + encodeURIComponent(sessionId));
    bulkEventSource.addEventListener('proxy_progress', e => {
      try {
        const state = JSON.parse(e.data);
        if (typeof updateProxyTestUI === 'function') updateProxyTestUI(state);
      } catch(err) {}
    });
    bulkEventSource.onerror = () => {
      // Reconnect handled automatically by browser EventSource
    };
  } catch(e) {
    console.debug('SSE connection info:', e);
  }
}

function disconnectBulkSSE() {
  if (bulkEventSource) {
    try { bulkEventSource.close(); } catch(e) {}
    bulkEventSource = null;
  }
}

function createBulkRowElement(item) {
  const tr = document.createElement('tr');
  const tok = item.token_data || {};
  const launch = buildLaunchLinks(tok.token || tok.url || tok.browser_url);
  const browserUrl = launch.browser;
  const androidUrl = launch.android;
  const tvUrl = launch.tv;

  const isHold = (item.status === 'HOLD' || item.is_hold);
  const isLive = (item.status === 'LIVE' || (item.live && !isHold));

  let badge = '<span class="tag-dead">✕ DEAD</span>';
  if (isHold) badge = '<span class="tag-hold">⏸ HOLD</span>';
  else if (isLive) badge = '<span class="tag-live">● LIVE</span>';

  tr.innerHTML = `
    <td>${item.index}</td>
    <td>${badge}</td>
    <td style="${item.plan && (item.plan.includes('4K') || item.plan.includes('ULTRA')) ? 'color:var(--accent-4k); font-weight:700;' : ''}">${item.plan || '-'}</td>
    <td style="${isHold ? 'color:var(--hold);' : ''}">${item.billing || '-'}</td>
    <td>${item.country || '-'}</td>
    <td>
      ${(isLive || isHold) ? `
        <div style="display:flex; gap:4px; align-items:center;">
          ${browserUrl ? `<a href="${browserUrl}" target="_blank" class="btn-outline-sm" style="color:#38bdf8; text-decoration:none; padding:2px 6px; font-size:11px;">Browser</a>` : ''}
          ${androidUrl ? `<a href="${androidUrl}" target="_blank" class="btn-outline-sm" style="color:#4ade80; text-decoration:none; padding:2px 6px; font-size:11px;">Android</a>` : ''}
          ${tvUrl ? `<a href="${tvUrl}" target="_blank" class="btn-outline-sm" style="color:#a855f7; text-decoration:none; padding:2px 6px; font-size:11px;">TV</a>` : ''}
          ${item.raw ? `<button class="btn-outline-sm" style="color:#f1f5f9; padding:2px 6px; font-size:11px;" onclick="copyBulkCookie(${item.index})">Cookie</button>` : ''}
        </div>
      ` : '-'}
    </td>
    <td style="color:var(--text-muted)">${item.route || 'Direct'}</td>
  `;
  return tr;
}



function parseCookieEditorFormat(rawStr, defaultDomain = '.netflix.com') {
  if (!rawStr) return [];
  // 1. JSON format
  if (rawStr.trim().startsWith('[') && rawStr.trim().endsWith(']')) {
    try {
      const j = JSON.parse(rawStr);
      if (Array.isArray(j) && j[0] && j[0].name) return j;
    } catch(e) {}
  }
  // 2. Netscape tab-separated lines
  if (rawStr.includes('\t')) {
    const cookies = [];
    const lines = rawStr.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const parts = trimmed.split('\t');
      if (parts.length >= 7) {
        cookies.push({
          domain: parts[0],
          expirationDate: parseInt(parts[4]) || 1893456000,
          hostOnly: !parts[0].startsWith('.'),
          httpOnly: parts[1].toUpperCase() === 'TRUE',
          name: parts[5],
          path: parts[2] || '/',
          sameSite: 'no_restriction',
          secure: parts[3].toUpperCase() === 'TRUE',
          session: false,
          storeId: null,
          value: parts[6]
        });
      }
    }
    if (cookies.length > 0) return cookies;
  }
  // 3. Header string Name=Value;
  const cookies = [];
  const pairs = rawStr.split(';');
  for (const pair of pairs) {
    const trimmed = pair.trim();
    if (!trimmed || !trimmed.includes('=')) continue;
    const eqIdx = trimmed.indexOf('=');
    const name = trimmed.substring(0, eqIdx).trim();
    const val = trimmed.substring(eqIdx + 1).trim();
    if (name) {
      cookies.push({
        domain: defaultDomain,
        expirationDate: 1893456000,
        hostOnly: false,
        httpOnly: name.toLowerCase().includes('secure') || name.toLowerCase().includes('netflixid'),
        name: name,
        path: '/',
        sameSite: 'no_restriction',
        secure: true,
        session: false,
        storeId: null,
        value: val
      });
    }
  }
  return cookies;
}

function convertToNetscapeLines(rawStr, defaultDomain = '.netflix.com') {
  const cookies = parseCookieEditorFormat(rawStr, defaultDomain);
  return cookies.map(c => {
    const dom = c.domain || defaultDomain;
    const tailmatch = dom.startsWith('.') ? 'TRUE' : 'FALSE';
    const path = c.path || '/';
    const secure = c.secure ? 'TRUE' : 'FALSE';
    const exp = c.expirationDate || 1893456000;
    return `${dom}\t${tailmatch}\t${path}\t${secure}\t${exp}\t${c.name}\t${c.value}`;
  });
}

function exportBulk(type, targetStatus = 'LIVE') {
  let list = [];
  if (targetStatus === 'HOLD') {
    list = bulkResults.filter(r => r.status === 'HOLD' || r.is_hold);
  } else if (targetStatus === '4K') {
    list = bulkResults.filter(r => (r.status === 'LIVE' || r.live) && (r.plan && r.plan.includes('4K')));
  } else if (targetStatus === 'DEAD') {
    list = bulkResults.filter(r => r.status === 'DEAD' || !r.live);
  } else {
    list = bulkResults.filter(r => r.status === 'LIVE' || (r.live && r.status !== 'HOLD' && !r.is_hold));
  }

  if (list.length === 0) {
    showToast(`Belum ada akun ${targetStatus} untuk diexport`);
    return;
  }

  let blob, filename;
  const prefix = targetStatus.toLowerCase();

  if (type === 'txt') {
    const lines = list.map((r, i) => {
      const tok = r.token_data || {};
      const launch = buildLaunchLinks(tok.token || tok.url || tok.browser_url);
      let block = `[${i+1}] [${r.status || targetStatus}] Plan: ${r.plan || '-'} | Billing: ${r.billing || '-'} | Country: ${r.country || '-'}\n`;
      if (r.email && r.email !== 'Account Valid') block += `Email  : ${r.email}\n`;
      if (r.profiles && r.profiles.length) block += `Profile: ${r.profiles.join(', ')}\n`;
      if (launch.browser) block += `Browser: ${launch.browser}\n`;
      if (launch.android) block += `Android: ${launch.android}\n`;
      if (launch.tv)      block += `SmartTV: ${launch.tv}\n`;
      block += `Cookie : ${r.raw}\n----------------------------------`;
      return block;
    });
    blob = new Blob([lines.join('\n')], {type: 'text/plain;charset=utf-8'});
    filename = `netflix_${prefix}_${Date.now()}.txt`;
  } else if (type === 'cookie_editor') {
    // Cookie-Editor format (directly importable in Cookie-Editor browser extension)
    const exportEntries = list.map((r, i) => {
      const raw = r.raw || r.cookie || '';
      return {
        account_id: i + 1,
        email: r.email || `Account #${i+1}`,
        plan: r.plan || 'Active',
        country: r.country || '-',
        cookies: parseCookieEditorFormat(raw, '.netflix.com')
      };
    });
    const finalPayload = (exportEntries.length === 1) ? exportEntries[0].cookies : exportEntries;
    blob = new Blob([JSON.stringify(finalPayload, null, 2)], {type: 'application/json;charset=utf-8'});
    filename = `netflix_cookie_editor_${prefix}_${Date.now()}.json`;
  } else if (type === 'netscape') {
    // Netscape HTTP Cookie file format
    let outLines = [
      '# Netscape HTTP Cookie File',
      '# https://curl.se/docs/http-cookies.html',
      '# Generated by NF-Sawava Suite Ultra',
      ''
    ];
    list.forEach((r, i) => {
      const raw = r.raw || r.cookie || '';
      outLines.push(`# --- Account #${i+1} [${r.plan || 'Plan'}] [${r.country || '-'}] ---`);
      outLines.push(...convertToNetscapeLines(raw, '.netflix.com'));
      outLines.push('');
    });
    blob = new Blob([outLines.join('\n')], {type: 'text/plain;charset=utf-8'});
    filename = `netflix_netscape_${prefix}_${Date.now()}.txt`;
  } else if (type === 'combo') {
    // Standard combo list format
    const outLines = list.map(r => {
      const email = r.email && r.email !== 'Account Valid' ? r.email : 'user@netflix.com';
      const pass = r.password || '******';
      return `${email}:${pass} | Plan: ${r.plan || '-'} | Country: ${r.country || '-'} | Billing: ${r.billing || '-'}`;
    });
    blob = new Blob([outLines.join('\n')], {type: 'text/plain;charset=utf-8'});
    filename = `netflix_combo_${prefix}_${Date.now()}.txt`;
  } else {
    // Full JSON enriched
    const enriched = list.map(r => {
      const tok = r.token_data || {};
      const launch = buildLaunchLinks(tok.token || tok.url || tok.browser_url);
      return {
        ...r,
        launch_links: launch
      };
    });
    blob = new Blob([JSON.stringify(enriched, null, 2)], {type: 'application/json;charset=utf-8'});
    filename = `netflix_${prefix}_${Date.now()}.json`;
  }

  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  showToast(`File ${filename} didownload`);
}

// History DB Pagination & Search
function onSearchInput() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    resetPageAndLoad();
  }, 350);
}

function resetPageAndLoad() {
  curPage = 1;
  loadHistory();
}

function prevPage() {
  if (curPage > 1) {
    curPage--;
    loadHistory();
  }
}

function nextPage() {
  curPage++;
  loadHistory();
}

async function loadHistory() {
  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:20px;">Memuat data riwayat...</td></tr>';

  const q = document.getElementById('hist-search').value.trim();
  const st = document.getElementById('hist-filter-status').value;
  const pl = document.getElementById('hist-filter-plan').value;
  const tp = document.getElementById('hist-filter-type').value;
  const offset = (curPage - 1) * pageSize;

  try {
    const params = new URLSearchParams({
      limit: pageSize,
      offset: offset,
      search: q,
      status: st,
      plan: pl,
      type: tp
    });
    const res = await fetch(`/api/history?${params.toString()}`, {
      headers: getAuthHeaders()
    });
    const data = await res.json();
    renderHistoryTable(data);
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--dead); padding:20px;">Gagal memuat riwayat.</td></tr>';
  }
}

function renderHistoryTable(data) {
  const tbody = document.getElementById('history-tbody');
  const rows = data.items || [];
  const total = data.total || 0;
  window.currentHistoryRows = rows;

  if (rows.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="padding:48px 20px; text-align:center;">
          <div class="empty-state-box">
            <div class="empty-state-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="m14.83 14.83 4.24 4.24"/><path d="m9.17 14.83-4.24 4.24"/></svg>
            </div>
            <div class="empty-state-title">No History Records Found</div>
            <div class="empty-state-sub">Belum ada akun yang diperiksa atau hasil tidak cocok dengan filter pencarian.</div>
            <button type="button" class="btn-secondary btn-sm" onclick="resetPageAndLoad()" style="margin-top:14px;">Reset Filter & Pencarian</button>
          </div>
        </td>
      </tr>
    `;
    document.getElementById('pag-start').innerText = '0';
    document.getElementById('pag-end').innerText = '0';
    document.getElementById('pag-total').innerText = total;
    document.getElementById('btn-prev').disabled = true;
    document.getElementById('btn-next').disabled = true;
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const svcBadge = r.type === 'disney' ? '<span class="service-tag teal">Disney+</span>'
      : r.type === 'crunchyroll' ? '<span class="service-tag orange">Crunchyroll</span>'
      : r.type === 'expressvpn' ? '<span class="service-tag crimson">ExpressVPN</span>'
      : r.type === 'spotify' ? '<span class="service-tag green">Spotify</span>'
      : r.type === 'outlook' ? '<span class="service-tag blue">Outlook</span>'
      : r.type === 'hotmail' ? '<span class="service-tag blue">Hotmail</span>'
      : '<span class="service-tag red">Netflix</span>';

    const statusTag = r.status === 'LIVE' ? '<span class="badge-status live"><span class="dot"></span>LIVE</span>'
      : r.status === 'HOLD' ? '<span class="badge-status hold"><span class="dot"></span>HOLD</span>'
      : r.status === 'FREE' ? '<span class="badge-status free"><span class="dot"></span>FREE</span>'
      : r.status === 'PREMIUM' ? '<span class="badge-status premium"><span class="dot"></span>PREMIUM</span>'
      : r.status === 'TRIAL' ? '<span class="badge-status twofa"><span class="dot"></span>TRIAL</span>'
      : r.status === 'BAD' ? '<span class="badge-status bad"><span class="dot"></span>BAD</span>'
      : r.status === 'DEAD' ? '<span class="badge-status dead"><span class="dot"></span>DEAD</span>'
      : r.status === '2FA' ? '<span class="badge-status twofa"><span class="dot"></span>2FA</span>'
      : r.status === 'LOCKED' ? '<span class="badge-status locked"><span class="dot"></span>LOCKED</span>'
      : r.status === 'PHONE_LOCKED' ? '<span class="badge-status locked"><span class="dot"></span>PHONE LOCK</span>'
      : `<span class="badge-status bad"><span class="dot"></span>${r.status}</span>`;

    let identifier = r.email ? maskEmail(r.email) : '-';
    if (!r.email && r.raw_cookie) {
      if (r.type === 'spotify') {
        const spPart = r.raw_cookie.split('sp_dc');
        identifier = (spPart.length > 1) ? 'sp_dc:' + spPart[1].replace(/^[=\s	]+/, '').substring(0, 16) + '…' : r.raw_cookie.substring(0, 24) + '…';
      } else if (r.type === 'checker') {
        identifier = r.raw_cookie.substring(0, 24) + (r.raw_cookie.length > 24 ? '…' : '');
      } else {
        const rawPart = r.raw_cookie.split(':')[0];
        identifier = maskEmail(rawPart);
      }
    }
    if (identifier.length > 36) identifier = identifier.substring(0, 34) + '…';

    const copyLabel = (r.type === 'checker' || r.type === 'spotify') ? 'Salin Cookie' : 'Salin Combo';
    return `
    <tr>
      <td style="color:var(--text-muted); font-family:'JetBrains Mono', monospace; font-size:11px;">${r.created_at}</td>
      <td style="font-weight:600; font-size:12px;">${svcBadge}</td>
      <td>${statusTag}</td>
      <td style="font-size:12px; font-family:'JetBrains Mono', monospace; color:var(--text-secondary); max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${(r.email || r.raw_cookie || '').replace(/"/g, '&quot;')}">${identifier}</td>
      <td style="${r.plan && r.plan.includes('4K') ? 'color:var(--accent-4k); font-weight:700;' : ''}">${r.plan || '-'}</td>
      <td style="font-size:12px; color:var(--text-muted);">${r.billing || '-'}</td>
      <td>${r.country || '-'}</td>
      <td>
        <div style="display:flex; gap:6px; align-items:center;">
          ${r.raw_cookie ? `<button class="btn-outline-sm" onclick="copyHistoryCookie(${r.id})">${copyLabel}</button>` : '-'}
          <button class="btn-outline-sm" style="color:#f43f5e; border-color:rgba(244,63,94,0.3);" onclick="deleteHistoryItem(${r.id})" title="Hapus record ini">🗑</button>
        </div>
      </td>
    </tr>
  `;
  }).join('');

  const start = (curPage - 1) * pageSize + 1;
  const end = Math.min(curPage * pageSize, total);
  document.getElementById('pag-start').innerText = start;
  document.getElementById('pag-end').innerText = end;
  document.getElementById('pag-total').innerText = total;
  document.getElementById('page-num').innerText = `Halaman ${curPage}`;

  document.getElementById('btn-prev').disabled = (curPage <= 1);
  document.getElementById('btn-next').disabled = (end >= total);
}

function escapeAttr(str) {
  return (str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, ' ');
}

async function exportCsvWithAuth() {
  try {
    const q = document.getElementById('hist-search').value.trim();
    const st = document.getElementById('hist-filter-status').value;
    const pl = document.getElementById('hist-filter-plan').value;
    const params = new URLSearchParams({ search: q, status: st, plan: pl });

    const res = await fetch(`/api/history/export_csv?${params.toString()}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw new Error('Gagal mengunduh CSV');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `suite_history_${Date.now()}.csv`;
    a.click();
    showToast('File CSV berhasil diunduh (sesuai filter)');
  } catch(e) {
    showToast('Gagal export CSV: ' + e.message);
  }
}

async function clearDbHistory(onlyDead = false) {
  const msg = onlyDead ? 'Hapus semua entri DEAD / ERROR di database?' : 'Hapus SELURUH riwayat di database?';
  if (!confirm(msg)) return;
  await fetch('/api/history/clear', {
    method: 'POST',
    headers: getAuthHeaders({'Content-Type': 'application/json'}),
    body: JSON.stringify({ only_dead: onlyDead })
  });
  showToast(onlyDead ? 'Riwayat DEAD berhasil dibersihkan' : 'Seluruh database dibersihkan');
  curPage = 1;
  loadHistory();
}

async function deleteHistoryItem(id) {
  if (!confirm('Hapus record #' + id + ' dari history?')) return;
  try {
    var res = await fetch('/api/history/delete', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ id: id })
    });
    var data = await res.json();
    if (data.status === 'ok') {
      showToast('Record #' + id + ' berhasil dihapus');
      loadHistory();
    } else {
      showToast('Gagal menghapus: ' + (data.reason || 'Unknown error'));
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

async function recheckHistoryItem(id) {
  try {
    const res = await fetch('/api/history/recheck', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ id: id })
    });
    return await res.json();
  } catch(e) {
    return { error: e.message };
  }
}

async function recheckBatch(ids) {
  try {
    const res = await fetch('/api/history/recheck', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ ids: ids })
    });
    const data = await res.json();
    return data.results || [];
  } catch(e) {
    return ids.map(id => ({ id, error: e.message }));
  }
}

async function recheckAllHistory() {
  const btn = document.getElementById('btn-recheck-all');
  const progress = document.getElementById('recheck-progress');
  const bar = document.getElementById('recheck-bar');
  const statusText = document.getElementById('recheck-status-text');
  const statsText = document.getElementById('recheck-stats');
  const filterStatus = document.getElementById('recheck-filter').value;
  const filterType = document.getElementById('recheck-type').value;

  // Pastikan API key ada
  let apiKey = sessionStorage.getItem('suite_api_key') || '';
  if (!apiKey) {
    apiKey = prompt('Masukkan API Key untuk melanjutkan:');
    if (!apiKey) { showToast('API Key diperlukan untuk recheck'); return; }
    sessionStorage.setItem('suite_api_key', apiKey.trim());
  }

  btn.disabled = true;
  btn.textContent = '⏳ Memproses...';
  progress.style.display = 'block';
  bar.style.width = '0%';
  statusText.textContent = 'Menjalankan bulk recheck di server...';
  statsText.textContent = '';

  try {
    const res = await fetch('/api/history/recheck', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ bulk: true, status: filterStatus, type: filterType })
    });
    const data = await res.json();

    if (data.error) {
      showToast('Error: ' + data.error);
      statusText.textContent = 'Error: ' + data.error;
    } else {
      const r = data;
      bar.style.width = '100%';
      statusText.textContent = `Selesai! ${r.total} record di-recheck.`;
      statsText.textContent = `✅ ${r.ok} OK | 🔄 ${r.changed} berubah (${r.to_live} → LIVE, ${r.to_dead} → DEAD) | ❌ ${r.errors} error`;
      showToast(`Recheck selesai: ${r.changed} berubah dari ${r.total} record`);
      loadHistory();
    }
  } catch(e) {
    showToast('Recheck error: ' + e.message);
    statusText.textContent = 'Error: ' + e.message;
  }

  btn.disabled = false;
  btn.textContent = '🔄 Recheck Semua';
}

// Analytics Charts
async function loadAnalytics() {
  let d = {};
  try {
    const res = await fetch('/api/analytics', {
      headers: getAuthHeaders()
    });
    if (res.ok) d = await res.json();
  } catch(e) {
    console.error('Failed to load analytics:', e);
  }

  const sc = d.status_counts || {};
  const planCounts = d.plan_counts || {};
  const countryCounts = d.country_counts || {};

  if (chartStatusObj) { chartStatusObj.destroy(); chartStatusObj = null; }
  if (chartCountryObj) { chartCountryObj.destroy(); chartCountryObj = null; }
  if (chartPlanObj) { chartPlanObj.destroy(); chartPlanObj = null; }

  const statusCanvas = document.getElementById('chart-status');
  if (statusCanvas) {
    const ctxStatus = statusCanvas.getContext('2d');
    chartStatusObj = new Chart(ctxStatus, {
      type: 'doughnut',
      data: {
        labels: ['LIVE', 'HOLD', 'DEAD'],
        datasets: [{
          data: [sc.LIVE || 0, sc.HOLD || 0, sc.DEAD || 0],
          backgroundColor: ['#10b981', '#f59e0b', '#f43f5e'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: { color: '#848b9f', font: { family: 'Plus Jakarta Sans', weight: 600 } }
          }
        }
      }
    });
  }

  const planLabels = Object.keys(planCounts);
  const planData = Object.values(planCounts);
  const planCanvas = document.getElementById('chart-plan');
  if (planCanvas) {
    const ctxPlan = planCanvas.getContext('2d');
    chartPlanObj = new Chart(ctxPlan, {
      type: 'doughnut',
      data: {
        labels: planLabels.length ? planLabels : ['Belum ada data'],
        datasets: [{
          data: planData.length ? planData : [0],
          backgroundColor: ['#a855f7', '#38bdf8', '#f59e0b', '#ec4899', '#10b981', '#64748b'],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: { color: '#848b9f', font: { family: 'Plus Jakarta Sans', weight: 600 } }
          }
        }
      }
    });
  }

  const countryLabels = Object.keys(countryCounts);
  const countryData = Object.values(countryCounts);
  const countryCanvas = document.getElementById('chart-country');
  if (countryCanvas) {
    const ctxCountry = countryCanvas.getContext('2d');
    chartCountryObj = new Chart(ctxCountry, {
      type: 'bar',
      data: {
        labels: countryLabels.length ? countryLabels : ['Belum ada data'],
        datasets: [{
          label: 'Jumlah Akun',
          data: countryData.length ? countryData : [0],
          backgroundColor: '#e50914',
          borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#848b9f', font: { family: 'Plus Jakarta Sans' } }, grid: { display: false } },
        y: { ticks: { color: '#848b9f', font: { family: 'JetBrains Mono' } }, grid: { color: '#222634' } }
      }
    }
  });
  }
}

function copyText(str, msg = 'Teks disalin ke clipboard') {
  if (!str) {
    showToast('Tidak ada teks untuk disalin');
    return;
  }

  // 1. Coba Clipboard API modern jika Secure Context (HTTPS / localhost)
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(str).then(() => {
      showToast(msg);
    }).catch(() => {
      fallbackCopyText(str, msg);
    });
    return;
  }

  // 2. Fallback untuk HTTP / LAN IP (misal http://192.168.x.x) / mobile browser
  fallbackCopyText(str, msg);
}

function fallbackCopyText(str, msg) {
  let success = false;
  try {
    const ta = document.createElement('textarea');
    ta.value = str;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '-9999px';
    ta.style.opacity = '0';
    ta.setAttribute('readonly', '');
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    success = document.execCommand('copy');
    document.body.removeChild(ta);
  } catch(e) {
    success = false;
  }

  if (success) {
    showToast(msg);
  } else {
    window.prompt('Salin manual dengan Ctrl+C / Cmd+C:', str);
  }
}

function copyJson(obj, msg = 'Cookie JSON disalin') {
  if (!obj) {
    showToast('Data JSON tidak tersedia');
    return;
  }
  const jsonStr = (typeof obj === 'string') ? obj : JSON.stringify(obj, null, 2);
  copyText(jsonStr, msg);
}

function copyHistoryCookie(id) {
  const item = (window.currentHistoryRows || []).find(x => x.id === id);
  if (item && item.raw_cookie) {
    copyText(item.raw_cookie, 'Cookie disalin ke clipboard');
  } else {
    showToast('Cookie tidak tersedia');
  }
}

function copyBulkCookie(idx) {
  const item = (bulkResults || []).find(x => x.index === idx);
  if (item && item.raw) {
    copyText(item.raw, 'Cookie disalin ke clipboard');
  } else {
    showToast('Cookie tidak tersedia');
  }
}

function copySingleCookieJson() {
  if (window.currentSingleCheckResult && window.currentSingleCheckResult.cookies) {
    copyJson(window.currentSingleCheckResult.cookies, 'Cookie JSON disalin');
  } else {
    showToast('Data cookie JSON tidak tersedia');
  }
}

function copySingleRawCookie() {
  const cookie = window.currentSingleCookieRaw || document.getElementById('single-cookie')?.value?.trim();
  if (cookie) {
    copyText(cookie, 'Cookie asli disalin');
  } else {
    showToast('Cookie tidak tersedia');
  }
}

fetchStats();
checkPinStatus();

// ═══════════════════════════════════════════════════════════════════
// Country code helper (JS mirror of Python normalize_country)
// ═══════════════════════════════════════════════════════════════════
const COUNTRY_NAMES_JS = {
  'AR':'Argentina','AU':'Australia','BR':'Brazil','CA':'Canada','DE':'Germany',
  'ES':'Spain','FR':'France','GB':'United Kingdom','ID':'Indonesia','IN':'India',
  'IT':'Italy','JP':'Japan','KR':'South Korea','MY':'Malaysia','MX':'Mexico',
  'NL':'Netherlands','PH':'Philippines','SG':'Singapore','TH':'Thailand',
  'TR':'Turkey','US':'United States','VN':'Vietnam','CL':'Chile','CO':'Colombia',
  'PE':'Peru','SE':'Sweden','NO':'Norway','DK':'Denmark','FI':'Finland',
  'PL':'Poland','PT':'Portugal','RO':'Romania','CZ':'Czech Republic',
  'HU':'Hungary','IE':'Ireland','NZ':'New Zealand','ZA':'South Africa',
  'AE':'UAE','SA':'Saudi Arabia','EG':'Egypt','TW':'Taiwan','HK':'Hong Kong'
};
function normalize_country_js(code) {
  if (!code) return 'Unknown';
  const c = String(code).trim().toUpperCase();
  if (c.length === 2 && /^[A-Z]{2}$/.test(c)) {
    return `${COUNTRY_NAMES_JS[c] || c} (${c})`;
  }
  return c;
}

// ═══════════════════════════════════════════════════════════════════
// Disney+ Account Checker Functions
// ═══════════════════════════════════════════════════════════════════

let disneyBulkRunning = false;
let disneyBulkAbort = false;
let disneyBulkResults = [];
let disneyComboFileQueue = [];
let disneyCookieFileQueue = [];

// ═══════ Disney+ Combo File Handler ═══════
function handleDisneyComboFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('disney-combo-file-info');
  const textarea = document.getElementById('disney-bulk-input');
  disneyComboFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }
      const lines = content.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.includes(':'));
      lines.forEach(l => disneyComboFileQueue.push(l));
      processed++;
      if (processed === total) {
        fileInfo.textContent = `✅ ${total} file dimuat → ${disneyComboFileQueue.length} combo ditemukan`;
        fileInfo.style.color = '#1ce783';
        textarea.value = disneyComboFileQueue.join('\n');
        showToast(`${disneyComboFileQueue.length} combos dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });
}

// ═══════ Disney+ Cookie File Handler ═══════
function handleDisneyCookieFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('disney-cookie-file-info');
  const textarea = document.getElementById('disney-bulk-cookie-input');
  disneyCookieFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  const dsnKey = /refresh_token|id_token|swid/i;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }

      if (file.name.endsWith('.json')) {
        try {
          const arr = JSON.parse(content);
          if (Array.isArray(arr) && arr.length > 0) {
            if (arr[0] && arr[0].name) {
              disneyCookieFileQueue.push(JSON.stringify(arr));
            } else {
              arr.forEach(item => {
                const val = typeof item === 'string' ? item.trim() : JSON.stringify(item);
                if (val) disneyCookieFileQueue.push(val);
              });
            }
          }
        } catch(ex) {
          disneyCookieFileQueue.push(content);
        }
      } else {
        const allLines = content.split('\n');
        const hasNetscape = allLines.some(l => l.trim().split('\t').length >= 7);

        if (hasNetscape) {
          const blocks = [];
          let currentBlock = [];
          for (const rawLine of allLines) {
            const line = rawLine.trim();
            if ((line.toLowerCase().startsWith('# netscape http cookie file') || /^={5,}$/.test(line)) && currentBlock.length > 0) {
              const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && !l.startsWith('=') && l.split('\t').length >= 7);
              if (cookieLines.length > 0) blocks.push(currentBlock.join('\n'));
              currentBlock = [];
            }
            currentBlock.push(line);
          }
          if (currentBlock.length > 0) {
            const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && !l.startsWith('=') && l.split('\t').length >= 7);
            if (cookieLines.length > 0) blocks.push(currentBlock.join('\n'));
          }
          if (blocks.length === 0) {
            disneyCookieFileQueue.push(content);
          } else {
            blocks.forEach(b => disneyCookieFileQueue.push(b));
          }
        } else {
          if (dsnKey.test(content)) {
            disneyCookieFileQueue.push(content);
          } else {
            const cleanLines = allLines.map(l => l.trim()).filter(l => l && !l.startsWith('#'));
            cleanLines.forEach(l => disneyCookieFileQueue.push(l));
          }
        }
      }

      processed++;
      if (processed === total) {
        const totalCookies = disneyCookieFileQueue.length;
        fileInfo.textContent = `✅ ${total} file dimuat → ${totalCookies} akun ditemukan`;
        fileInfo.style.color = '#1ce783';
        textarea.value = disneyCookieFileQueue.join('\n\n---\n\n');
        showToast(`${totalCookies} cookies dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });
}

function disneyStatusColor(status) {
  const m = { LIVE: '#10b981', BAD: '#f43f5e', DEAD: '#f43f5e', HOLD: '#f59e0b', ERROR: '#f59e0b' };
  return m[status] || 'var(--text-muted)';
}

function disneyStatusBg(status) {
  const m = { LIVE: 'rgba(16,185,129,0.1)', BAD: 'rgba(244,63,94,0.1)', DEAD: 'rgba(244,63,94,0.1)', HOLD: 'rgba(245,158,11,0.1)', ERROR: 'rgba(245,158,11,0.1)' };
  return m[status] || 'rgba(132,139,159,0.1)';
}

function renderDisneyResult(data, mode = 'single') {
  const color = disneyStatusColor(data.status);
  const statusIcon = { LIVE: '✅', BAD: '❌', DEAD: '💀', HOLD: '⏸', ERROR: '⚠️' }[data.status] || '❓';
  const comboText = data.combo || `${data.email || ''}:${data._password || '***'}`;

  if (data.status === 'LIVE' || data.status === 'HOLD') {
    const isHold = data.status === 'HOLD';
    const cardClass = isHold ? 'card-out hold' : 'card-out live';
    const statusLabel = isHold ? 'Account On Hold' : 'Account Live';

    return `<div class="${mode === 'bulk' ? '' : cardClass}" style="${mode === 'bulk' ? `padding:16px; border-left:4px solid ${color}; background:${disneyStatusBg(data.status)}; margin-bottom:10px; border-radius:var(--radius-lg);` : ''}">
      <div class="card-header-status" style="color:${color};">
        <span>${statusIcon}</span> <span>${statusLabel}</span>
        <span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ${data.route || 'Direct'}</span>
      </div>

      ${isHold ? `
      <div style="background:rgba(245, 158, 11, 0.12); border:1px solid rgba(245, 158, 11, 0.3); color:#fcd34d; padding:10px 14px; border-radius:var(--radius-sm); margin-bottom:12px; font-size:12px; display:flex; align-items:center; gap:8px;">
        <span>⚠️</span> <span><strong>Subscription Inactive:</strong> Akun ini dalam status hold / lapsed. Perlu renewal untuk melanjutkan streaming.</span>
      </div>
      ` : ''}

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong>${escapeHtml(data.email || 'N/A')}</strong></div>
        <div class="meta-box"><span>Plan</span><strong style="color:var(--disney, #1ce783);">${escapeHtml(data.plan || 'N/A')}</strong></div>
        <div class="meta-box"><span>Country</span><strong>${escapeHtml(data.country || 'N/A')}</strong></div>
        <div class="meta-box"><span>Renewal Date</span><strong style="${isHold ? 'color:var(--hold)' : ''}">${escapeHtml(data.renewal_date || 'N/A')}</strong></div>
        <div class="meta-box"><span>Subscriber Status</span><strong>${escapeHtml(data.subscriber_status || 'N/A')}</strong></div>
        <div class="meta-box"><span>Email Verified</span><strong>${data.email_verified === 'true' || data.email_verified === true ? '✅ Yes' : '❌ No'}</strong></div>
        <div class="meta-box"><span>Free Trial</span><strong>${data.free_trial ? '🎁 Yes' : 'No'}</strong></div>
        <div class="meta-box"><span>Has Active Plan</span><strong style="color:${data.has_plan ? 'var(--live)' : 'var(--dead)'};">${data.has_plan ? '✓ Active' : '✕ Inactive'}</strong></div>
      </div>

      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="btn-secondary" onclick="copyText('${escapeAttr(comboText)}', 'Combo disalin!')">📋 Copy Combo</button>
        <button class="btn-secondary" onclick="copyText('${escapeAttr(data.email || '')}', 'Email disalin!')">📧 Copy Email</button>
      </div>
    </div>`;
  }

  // BAD / DEAD / ERROR
  return `<div class="${mode === 'bulk' ? '' : 'card-out dead'}" style="${mode === 'bulk' ? `padding:10px; border-left:3px solid ${color}; background:${disneyStatusBg(data.status)}; margin-bottom:6px; border-radius:var(--radius-sm);` : ''}">
    <div class="card-header-status" style="color:${color};">
      <span style="font-size:18px;">${statusIcon}</span> <span>${data.status === 'BAD' ? 'Wrong Credentials' : data.status}</span>
    </div>
    <div style="color:var(--text-muted); font-size:12px;">${escapeHtml(data.reason || data.email || 'Akun tidak valid')}</div>
  </div>`;
}

// Disney+ mode switching (Login / Cookie)
function switchDisneyMode(mode) {
  document.getElementById('disney-login-form').style.display = mode === 'login' ? 'block' : 'none';
  document.getElementById('disney-cookie-form').style.display = mode === 'cookie' ? 'block' : 'none';
  document.getElementById('disney-mode-login').className = 'check-mode-tab' + (mode === 'login' ? ' active' : '');
  document.getElementById('disney-mode-cookie').className = 'check-mode-tab' + (mode === 'cookie' ? ' active' : '');
}

// Crunchyroll mode switching (Login / Cookie)
function switchCrMode(mode) {
  document.getElementById('cr-login-form').style.display = mode === 'login' ? 'block' : 'none';
  document.getElementById('cr-cookie-form').style.display = mode === 'cookie' ? 'block' : 'none';
  document.getElementById('cr-mode-login').className = 'check-mode-tab' + (mode === 'login' ? ' active' : '');
  document.getElementById('cr-mode-cookie').className = 'check-mode-tab' + (mode === 'cookie' ? ' active' : '');
}

// Disney+ Cookie Check
async function runDisneyCookieCheck() {
  const cookie = document.getElementById('disney-cookie-input').value.trim();
  if (!cookie) return showToast('Paste cookie dulu');
  const btn = document.getElementById('disney-cookie-btn');
  const btnText = document.getElementById('disney-cookie-btn-text');
  const outEl = document.getElementById('disney-single-out');
  const useProxy = document.getElementById('disney-cookie-proxy')?.checked ?? false;
  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';
  try {
    const res = await fetch('/api/disney/cookie-check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cookie, use_proxy: useProxy})
    });
    const data = await res.json();
    outEl.innerHTML = renderDisneyResult(data, 'single');
    outEl.style.display = 'block';
    updateDisneyStats(data.status);
    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'HOLD') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Cookie Check Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = '🍪 CHECK COOKIE';
}

// Crunchyroll Cookie Check
async function runCrCookieCheck() {
  const cookie = document.getElementById('cr-cookie-input').value.trim();
  if (!cookie) return showToast('Paste cookie dulu');
  const btn = document.getElementById('cr-cookie-btn');
  const btnText = document.getElementById('cr-cookie-btn-text');
  const outEl = document.getElementById('cr-single-out');
  const useProxy = document.getElementById('cr-cookie-proxy')?.checked ?? false;
  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';
  try {
    const res = await fetch('/api/crunchyroll/cookie-check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cookie, use_proxy: useProxy})
    });
    const data = await res.json();
    outEl.innerHTML = renderCrResult(data, 'single');
    outEl.style.display = 'block';
    updateCrStats(data.status);
    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'HOLD') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Cookie Check Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = '🍪 CHECK COOKIE';
}

// ═══════ Bulk Mode Switchers ═══════
function switchDisneyBulkMode(mode) {
  document.getElementById('disney-bulk-combo-form').style.display = mode === 'combo' ? 'block' : 'none';
  document.getElementById('disney-bulk-cookie-form').style.display = mode === 'cookie' ? 'block' : 'none';
  document.getElementById('disney-bulk-mode-combo').className = 'check-mode-tab' + (mode === 'combo' ? ' active' : '');
  document.getElementById('disney-bulk-mode-cookie').className = 'check-mode-tab' + (mode === 'cookie' ? ' active' : '');
}
function switchCrBulkMode(mode) {
  document.getElementById('cr-bulk-combo-form').style.display = mode === 'combo' ? 'block' : 'none';
  document.getElementById('cr-bulk-cookie-form').style.display = mode === 'cookie' ? 'block' : 'none';
  document.getElementById('cr-bulk-mode-combo').className = 'check-mode-tab' + (mode === 'combo' ? ' active' : '');
  document.getElementById('cr-bulk-mode-cookie').className = 'check-mode-tab' + (mode === 'cookie' ? ' active' : '');
}

// ═══════ Disney+ Bulk Cookie Check ═══════
async function runDisneyBulkCookie() {
  const raw = document.getElementById('disney-bulk-cookie-input').value.trim();
  if (!raw && disneyCookieFileQueue.length === 0) return showToast('Paste cookies atau upload file dulu');
  if (disneyBulkRunning) return;

  let cookies;
  // Prioritize file queue if files were loaded
  if (disneyCookieFileQueue.length > 0) {
    cookies = [...disneyCookieFileQueue];
  } else {
    // Detect the cookie-key that identifies each Disney account block
    const dsnKey = /id_token|refresh_token|swid/i;
    if (raw.includes('\n\n') && raw.split(/\n\n+/).filter(c => dsnKey.test(c)).length > 1) {
      cookies = raw.split(/\n\n+/).map(c => c.trim()).filter(c => c);
    } else if (/^-{3,}$/m.test(raw) && raw.split(/^-{3,}$/m).filter(c => dsnKey.test(c)).length > 1) {
      cookies = raw.split(/^-{3,}$/m).map(c => c.trim()).filter(c => c);
    } else if (/^={3,}$/m.test(raw) && raw.split(/^={3,}$/m).filter(c => dsnKey.test(c)).length > 1) {
      cookies = raw.split(/^={3,}$/m).map(c => c.trim()).filter(c => c);
    } else {
      // Treat entire text as ONE cookie block (multi-line Netscape format = 1 account)
      cookies = [raw];
    }
  }
  if (!cookies.length) return showToast('Tidak ada cookie valid');

  disneyBulkRunning = true;
  disneyBulkAbort = false;
  disneyBulkResults = [];

  const outEl = document.getElementById('disney-bulk-out');
  const statsEl = document.getElementById('disney-bulk-stats');
  const progressEl = document.getElementById('disney-bulk-progress');
  const barEl = document.getElementById('disney-progress-bar');
  const useProxy = document.getElementById('disney-bulk-cookie-proxy')?.checked ?? false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  let done = 0, live = 0, bad = 0, errors = 0;
  const total = cookies.length;
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < cookies.length && !disneyBulkAbort) {
      const idx = currentIndex++;
      const cookie = cookies[idx];
      try {
        const res = await fetch('/api/disney/cookie-check', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({cookie, use_proxy: useProxy})
        });
        const data = await res.json();
        data.combo = `Cookie #${idx + 1}`;
        disneyBulkResults.push(data);
        updateDisneyStats(data.status);

        if (data.status === 'LIVE' || data.status === 'HOLD') live++;
        else if (data.status === 'BAD' || data.status === 'DEAD') bad++;
        else errors++;

        const html = renderDisneyResult(data, 'bulk');
        outEl.insertAdjacentHTML('beforeend', html);
      } catch(e) {
        errors++;
        outEl.insertAdjacentHTML('beforeend', `<div style="padding:8px; border-left:3px solid var(--dead); background:rgba(244,63,94,0.1); margin-bottom:6px; border-radius:6px; font-size:12px; color:var(--dead);">Cookie #${idx+1}: ${e.message}</div>`);
      }
      done++;
      const pct = Math.round((done / total) * 100);
      statsEl.innerText = `⏳ ${done}/${total} — ✅ ${live} Live | 💀 ${bad} Bad | ⚠️ ${errors} Error`;
      barEl.style.width = pct + '%';
    }
  }

  await Promise.all(Array.from({length: concurrency}, () => worker()));
  statsEl.innerText = `✅ Selesai: ${done}/${total} — ${live} Live | ${bad} Bad | ${errors} Error`;
  disneyBulkRunning = false;
  disneyCookieFileQueue = [];
}
async function runCrBulkCookie() {
  const raw = document.getElementById('cr-bulk-cookie-input').value.trim();
  if (!raw && crCookieFileQueue.length === 0) return showToast('Paste cookies atau upload file dulu');
  if (crBulkRunning) return;

  let cookies;
  // Prioritize file queue if files were loaded
  if (crCookieFileQueue.length > 0) {
    cookies = [...crCookieFileQueue];
  } else {
    // Multi-cookie separators: double newline, --- divider, or ======= divider
    if (raw.includes('\n\n') && raw.split(/\n\n+/).filter(c => c.trim()).length > 1 && /etp_rt.*\n\n.*etp_rt/is.test(raw)) {
      cookies = raw.split(/\n\n+/).map(c => c.trim()).filter(c => c);
    } else if (/^-{3,}$/m.test(raw) && raw.split(/^-{3,}$/m).filter(c => /etp_rt/i.test(c)).length > 1) {
      cookies = raw.split(/^-{3,}$/m).map(c => c.trim()).filter(c => c);
    } else if (/^={3,}$/m.test(raw) && raw.split(/^={3,}$/m).filter(c => /etp_rt/i.test(c)).length > 1) {
      cookies = raw.split(/^={3,}$/m).map(c => c.trim()).filter(c => c);
    } else {
      // Treat entire text as ONE cookie block (multi-line Netscape format = 1 account)
      cookies = [raw];
    }
  }
  if (!cookies.length) return showToast('Tidak ada cookie valid');

  crBulkRunning = true;
  crBulkAbort = false;
  crBulkResults = [];

  const outEl = document.getElementById('cr-bulk-out');
  const statsEl = document.getElementById('cr-bulk-stats');
  const progressEl = document.getElementById('cr-bulk-progress');
  const barEl = document.getElementById('cr-progress-bar');
  const useProxy = document.getElementById('cr-bulk-cookie-proxy')?.checked ?? false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  let done = 0, live = 0, bad = 0, errors = 0;
  const total = cookies.length;
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < cookies.length && !crBulkAbort) {
      const idx = currentIndex++;
      const cookie = cookies[idx];
      try {
        const res = await fetch('/api/crunchyroll/cookie-check', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({cookie, use_proxy: useProxy})
        });
        const data = await res.json();
        data.combo = `Cookie #${idx + 1}`;
        crBulkResults.push(data);
        updateCrStats(data.status);

        if (data.status === 'LIVE' || data.status === 'PREMIUM' || data.status === 'FREE') live++;
        else if (data.status === 'BAD' || data.status === 'DEAD') bad++;
        else errors++;

        const html = renderCrResult(data, 'bulk');
        outEl.insertAdjacentHTML('beforeend', html);
      } catch(e) {
        errors++;
        outEl.insertAdjacentHTML('beforeend', `<div style="padding:8px; border-left:3px solid var(--dead); background:rgba(244,63,94,0.1); margin-bottom:6px; border-radius:6px; font-size:12px; color:var(--dead);">Cookie #${idx+1}: ${e.message}</div>`);
      }
      done++;
      const pct = Math.round((done / total) * 100);
      statsEl.innerText = `⏳ ${done}/${total} — ✅ ${live} Live | 💀 ${bad} Bad | ⚠️ ${errors} Error`;
      barEl.style.width = pct + '%';
    }
  }

  await Promise.all(Array.from({length: concurrency}, () => worker()));
  statsEl.innerText = `✅ Selesai: ${done}/${total} — ${live} Live | ${bad} Bad | ${errors} Error`;
  crBulkRunning = false;
  crCookieFileQueue = [];
}

async function runDisneySingle() {
  const email = document.getElementById('disney-email').value.trim();
  const password = document.getElementById('disney-password').value.trim();
  if (!email || !password) return showToast('Email dan password wajib diisi');

  const btn = document.getElementById('disney-single-btn');
  const btnText = document.getElementById('disney-single-btn-text');
  const outEl = document.getElementById('disney-single-out');
  const useProxy = document.getElementById('disney-proxy-toggle')?.checked ?? false;

  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    const res = await fetch('/api/disney/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ email, password, use_proxy: useProxy })
    });
    const data = await res.json();
    const mergedData = { ...data, _password: password, combo: `${email}:${password}` };

    outEl.innerHTML = renderDisneyResult(mergedData, 'single');
    outEl.style.display = 'block';
    updateDisneyStats(data.status);

    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'HOLD') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Request Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }

  btn.disabled = false;
  btnText.textContent = 'Check Disney+ Account';
}

async function runDisneyBulk() {
  const raw = document.getElementById('disney-bulk-input').value.trim();
  if (!raw && disneyComboFileQueue.length === 0) return showToast('Paste combo list atau upload file dulu');
  if (disneyBulkRunning) return;

  let lines = [];
  if (disneyComboFileQueue.length > 0) {
    lines = [...disneyComboFileQueue];
  }
  if (raw && disneyComboFileQueue.length === 0) {
    lines = raw.split('\n').map(l => l.trim()).filter(l => l && l.includes(':'));
  }
  if (!lines.length) return showToast('Tidak ada combo valid');

  disneyBulkRunning = true;
  disneyBulkAbort = false;
  disneyBulkResults = [];

  const outEl = document.getElementById('disney-bulk-out');
  const statsEl = document.getElementById('disney-bulk-stats');
  const progressEl = document.getElementById('disney-bulk-progress');
  const barEl = document.getElementById('disney-progress-bar');
  const useProxy = document.getElementById('disney-proxy-toggle')?.checked ?? false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  let done = 0, live = 0, bad = 0, errors = 0;
  const total = lines.length;
  const startTime = Date.now();
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < lines.length && !disneyBulkAbort) {
      const idx = currentIndex++;
      const combo = lines[idx];

      const [email, ...pwParts] = combo.split(' | ')[0].trim().split(':');
      const password = pwParts.join(':');

      let retries = 0;
      let success = false;
      while (retries < 3 && !success) {
        try {
          const res = await fetch('/api/disney/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ email: email.trim(), password: password.trim(), use_proxy: useProxy })
          });

          if (res.status === 401) {
            outEl.innerHTML += `<div style="padding:10px; color:#f43f5e; font-weight:600;">🔒 PIN tidak valid</div>`;
            disneyBulkAbort = true;
            break;
          }

          if (res.status === 429) {
            retries++;
            await new Promise(r => setTimeout(r, 3000 * retries));
            continue;
          }

          const data = await res.json();
          data.combo = combo;
          disneyBulkResults.push(data);
          success = true;

          if (data.status === 'LIVE') live++;
          else if (data.status === 'BAD' || data.status === 'DEAD') bad++;
          else errors++;

          outEl.innerHTML += renderDisneyResult({ ...data, email: email.trim(), _password: password.trim(), combo: combo.split(' | ')[0].trim() }, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateDisneyStats(data.status);
          if (data.status === 'LIVE') playAlert('live');
          else if (data.status === 'HOLD') playAlert('hold');
        } catch(e) {
          retries++;
          if (retries >= 3) {
            errors++;
            outEl.innerHTML += `<div style="padding:6px; font-size:11px; color:#f59e0b;">⚠️ ${email}: ${e.message}</div>`;
            success = true;
          } else {
            await new Promise(r => setTimeout(r, 2000));
          }
        }
      }

      done++;
      barEl.style.width = `${(done / total * 100).toFixed(1)}%`;
      const elapsed = (Date.now() - startTime) / 1000;
      const speed = done / elapsed;
      const eta = Math.ceil((total - done) / speed);
      statsEl.innerHTML = `<span style="color:#10b981;">${live} LIVE</span> · <span style="color:#f43f5e;">${bad} BAD</span> · <span style="color:#f59e0b;">${errors} ERR</span> · ${done}/${total} · ${speed.toFixed(1)}/s · ETA: ${eta}s`;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);

  disneyBulkRunning = false;
  disneyComboFileQueue = [];
  if (disneyBulkAbort) statsEl.innerHTML += ' · <span style="color:#f59e0b;">STOPPED</span>';
  else statsEl.innerHTML += ' · <span style="color:#10b981;">DONE</span>';
}

function stopDisneyBulk() {
  disneyBulkAbort = true;
}

function exportDisneyHits() {
  const hits = disneyBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  const text = hits.map(h => `${h.combo} | Plan: ${h.plan || 'N/A'} | Country: ${h.country || 'N/A'} | Renewal: ${h.renewal_date || 'N/A'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `disney_hits_${new Date().toISOString().slice(0,10)}.txt`;
  a.click();
  showToast(`${hits.length} hits exported`);
}

function copyDisneyHits() {
  const hits = disneyBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk dicopy');
  const text = hits.map(h => `${h.combo} | Plan: ${h.plan || 'N/A'} | Country: ${h.country || 'N/A'} | Renewal: ${h.renewal_date || 'N/A'}`).join('\n');
  navigator.clipboard.writeText(text).then(() => showToast(`${hits.length} hits copied to clipboard`));
}

// Disney+ keyboard shortcut (Enter to check)
document.getElementById('disney-password')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') runDisneySingle();
});

// ═══════════════════════════════════════════════════════════════════
// Crunchyroll Account Checker Functions
// ═══════════════════════════════════════════════════════════════════

let crBulkRunning = false;
let crBulkAbort = false;
let crBulkResults = [];
let crComboFileQueue = [];
let crCookieFileQueue = [];

// ═══════ Crunchyroll Combo File Handler ═══════
function handleCrComboFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('cr-combo-file-info');
  const textarea = document.getElementById('cr-bulk-input');
  crComboFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }
      // Each non-empty, non-comment line containing : is a combo
      const lines = content.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.includes(':'));
      lines.forEach(l => crComboFileQueue.push(l));
      processed++;
      if (processed === total) {
        fileInfo.textContent = `✅ ${total} file dimuat → ${crComboFileQueue.length} combo ditemukan`;
        fileInfo.style.color = '#f47521';
        textarea.value = crComboFileQueue.join('\n');
        showToast(`${crComboFileQueue.length} combos dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });
}

// ═══════ Crunchyroll Cookie File Handler ═══════
function handleCrCookieFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('cr-cookie-file-info');
  const textarea = document.getElementById('cr-bulk-cookie-input');
  crCookieFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }

      if (file.name.endsWith('.json')) {
        try {
          const arr = JSON.parse(content);
          if (Array.isArray(arr) && arr.length > 0) {
            if (arr[0] && arr[0].name) {
              // JSON cookie array = 1 account
              crCookieFileQueue.push(JSON.stringify(arr));
            } else {
              arr.forEach(item => {
                const val = typeof item === 'string' ? item.trim() : JSON.stringify(item);
                if (val) crCookieFileQueue.push(val);
              });
            }
          }
        } catch(ex) {
          crCookieFileQueue.push(content);
        }
      } else {
        // .txt / .cookie — detect Netscape format
        const allLines = content.split('\n');
        const hasNetscape = allLines.some(l => l.trim().split('\t').length >= 7);

        if (hasNetscape) {
          // Split multi-account Netscape files by "# Netscape HTTP Cookie File" header or ======= divider
          const blocks = [];
          let currentBlock = [];
          for (const rawLine of allLines) {
            const line = rawLine.trim();
            if ((line.toLowerCase().startsWith('# netscape http cookie file') || /^={5,}$/.test(line)) && currentBlock.length > 0) {
              const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && !l.startsWith('=') && l.split('\t').length >= 7);
              if (cookieLines.length > 0) blocks.push(currentBlock.join('\n'));
              currentBlock = [];
            }
            currentBlock.push(line);
          }
          if (currentBlock.length > 0) {
            const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && !l.startsWith('=') && l.split('\t').length >= 7);
            if (cookieLines.length > 0) blocks.push(currentBlock.join('\n'));
          }
          // If only 1 block or no explicit separators, treat entire file as 1 account
          if (blocks.length === 0) {
            crCookieFileQueue.push(content);
          } else {
            blocks.forEach(b => crCookieFileQueue.push(b));
          }
        } else {
          // Plain text: if contains etp_rt=, treat as single cookie block
          if (/etp_rt/i.test(content)) {
            crCookieFileQueue.push(content);
          } else {
            // Each line is a separate etp_rt token
            const cleanLines = allLines.map(l => l.trim()).filter(l => l && !l.startsWith('#'));
            cleanLines.forEach(l => crCookieFileQueue.push(l));
          }
        }
      }

      processed++;
      if (processed === total) {
        const totalCookies = crCookieFileQueue.length;
        fileInfo.textContent = `✅ ${total} file dimuat → ${totalCookies} akun ditemukan`;
        fileInfo.style.color = '#f47521';
        textarea.value = crCookieFileQueue.join('\n\n---\n\n');
        showToast(`${totalCookies} cookies dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });
}

function renderCrResult(data, mode = 'single') {
  const statusMap = { LIVE: ['✅','#10b981','rgba(16,185,129,0.1)'], BAD: ['❌','#f43f5e','rgba(244,63,94,0.1)'], FREE: ['🆓','#38bdf8','rgba(56,189,248,0.1)'], ERROR: ['⚠️','#f59e0b','rgba(245,158,11,0.1)'] };
  const [icon, color, bg] = statusMap[data.status] || ['❓','var(--text-muted)','rgba(132,139,159,0.1)'];
  const comboText = data.combo || `${data.email || ''}:${data._password || '***'}`;

  if (data.status === 'LIVE' || data.status === 'FREE') {
    const cardClass = data.status === 'LIVE' ? 'card-out live' : 'card-out live';
    const label = data.status === 'LIVE' ? 'Premium Account' : 'Free Account';

    return `<div class="${mode === 'bulk' ? '' : cardClass}" style="${mode === 'bulk' ? `padding:16px; border-left:4px solid ${color}; background:${bg}; margin-bottom:10px; border-radius:var(--radius-lg);` : ''}">
      <div class="card-header-status" style="color:${color};">
        <span>${icon}</span> <span>${label}</span>
        <span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ${escapeHtml(data.route || 'Direct')}</span>
      </div>

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong>${escapeHtml(data.email || 'N/A')}</strong></div>
        <div class="meta-box"><span>Subscription</span><strong style="color:${color};">${escapeHtml(data.subscription || 'Free')}${data.is_cancelled ? ' <span style=\"color:var(--dead); font-size:10px;\">⛔ Cancelled</span>' : ''}${data.active_free_trial ? ' <span style=\"color:#38bdf8; font-size:10px;\">🎁 Trial</span>' : ''}</strong></div>
        <div class="meta-box"><span>Username</span><strong>${escapeHtml(data.username || 'N/A')}</strong></div>
        <div class="meta-box"><span>Country</span><strong>${(() => { const c = data.sub_country || data.country; return c ? escapeHtml(normalize_country_js(c)) : 'N/A'; })()}</strong></div>
        <div class="meta-box"><span>Billing Cycle</span><strong>${escapeHtml(data.sub_cycle || 'N/A')}</strong></div>
        <div class="meta-box"><span>Source</span><strong>${data.sub_source ? escapeHtml(data.sub_source.replace(/-/g,' ').replace(/\b\w/g,l=>l.toUpperCase())) : 'N/A'}</strong></div>
        <div class="meta-box"><span>Streams</span><strong>${data.concurrent_streams || 1} concurrent</strong></div>
        <div class="meta-box"><span>Ads</span><strong style="color:${data.has_ads ? 'var(--dead)' : 'var(--live)'};">${data.has_ads ? '⛔ Has Ads' : '✅ No Ads'}</strong></div>
        <div class="meta-box"><span>Offline</span><strong style="color:${data.offline_viewing ? 'var(--live)' : 'var(--text-muted)'};">${data.offline_viewing ? '✅ Yes' : '❌ No'}</strong></div>
        <div class="meta-box"><span>Profiles</span><strong>${escapeHtml(data.profiles || 'N/A')}</strong></div>
        <div class="meta-box"><span>Email Verified</span><strong>${data.email_verified ? '✅ Yes' : '❌ No'}</strong></div>
        <div class="meta-box"><span>Active Since</span><strong>${data.sub_effective_date ? new Date(data.sub_effective_date).toLocaleDateString('id-ID', {day:'numeric',month:'short',year:'numeric'}) : 'N/A'}</strong></div>
        <div class="meta-box"><span>Account Created</span><strong>${data.created ? new Date(data.created).toLocaleDateString('id-ID', {day:'numeric',month:'short',year:'numeric'}) : 'N/A'}</strong></div>
        <div class="meta-box"><span>External ID</span><strong style="font-size:11px; font-family:'JetBrains Mono', monospace;">${escapeHtml(data.external_id || 'N/A')}</strong></div>
      </div>

      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="btn-secondary" onclick="copyText('${escapeAttr(comboText)}', 'Combo disalin!')">📋 Copy Combo</button>
        <button class="btn-secondary" onclick="copyText('${escapeAttr(data.email || '')}', 'Email disalin!')">📧 Copy Email</button>
      </div>
    </div>`;
  }

  // BAD / ERROR
  return `<div class="${mode === 'bulk' ? '' : 'card-out dead'}" style="${mode === 'bulk' ? `padding:10px; border-left:3px solid ${color}; background:${bg}; margin-bottom:6px; border-radius:var(--radius-sm);` : ''}">
    <div class="card-header-status" style="color:${color};">
      <span>${icon}</span> <span>${data.status === 'BAD' ? 'Wrong Credentials' : data.status}</span>
    </div>
    <div style="color:var(--text-muted); font-size:12px;">${escapeHtml(data.reason || data.email || 'Akun tidak valid')}</div>
  </div>`;
}

async function runCrSingle() {
  const email = document.getElementById('cr-email').value.trim();
  const password = document.getElementById('cr-password').value.trim();
  if (!email || !password) return showToast('Email dan password wajib diisi');
  const btn = document.getElementById('cr-single-btn');
  const btnText = document.getElementById('cr-single-btn-text');
  const outEl = document.getElementById('cr-single-out');
  const useProxy = document.getElementById('cr-proxy-toggle')?.checked ?? false;
  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    const res = await fetch('/api/crunchyroll/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ email, password, use_proxy: useProxy })
    });
    const data = await res.json();
    const mergedData = { ...data, _password: password, combo: `${email}:${password}` };

    outEl.innerHTML = renderCrResult(mergedData, 'single');
    outEl.style.display = 'block';
    updateCrStats(data.status);

    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'FREE') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Request Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = 'Check Crunchyroll Account';
}

async function runCrBulk() {
  const raw = document.getElementById('cr-bulk-input').value.trim();
  if (!raw && crComboFileQueue.length === 0) return showToast('Paste combo list atau upload file dulu');
  if (crBulkRunning) return;
  let lines = [];
  if (crComboFileQueue.length > 0) {
    lines = [...crComboFileQueue];
  }
  // Also include textarea content
  if (raw) {
    const textLines = raw.split('\n').map(l => l.trim()).filter(l => l && l.includes(':'));
    // Merge but avoid duplicates from file queue already filling textarea
    if (crComboFileQueue.length === 0) lines = textLines;
  }
  if (!lines.length) return showToast('Tidak ada combo valid');
  crBulkRunning = true; crBulkAbort = false; crBulkResults = [];
  const outEl = document.getElementById('cr-bulk-out');
  const statsEl = document.getElementById('cr-bulk-stats');
  const progressEl = document.getElementById('cr-bulk-progress');
  const barEl = document.getElementById('cr-progress-bar');
  const useProxy = document.getElementById('cr-proxy-toggle')?.checked ?? false;
  outEl.innerHTML = ''; progressEl.style.display = 'block'; barEl.style.width = '0%';
  let done = 0, live = 0, bad = 0, free = 0, errors = 0;
  const total = lines.length;
  const startTime = Date.now();
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < lines.length && !crBulkAbort) {
      const idx = currentIndex++;
      const combo = lines[idx];
      const [email, ...pwParts] = combo.split(' | ')[0].trim().split(':');
      const password = pwParts.join(':');
      let retries = 0, success = false;
      while (retries < 3 && !success) {
        try {
          const res = await fetch('/api/crunchyroll/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ email: email.trim(), password: password.trim(), use_proxy: useProxy })
          });
          if (res.status === 401) { outEl.innerHTML += `<div style="padding:10px; color:#f43f5e; font-weight:600;">🔒 PIN tidak valid</div>`; crBulkAbort = true; break; }
          if (res.status === 429) { retries++; await new Promise(r => setTimeout(r, 3000 * retries)); continue; }
          const data = await res.json(); data.combo = combo; crBulkResults.push(data);
          success = true;
          if (data.status === 'LIVE') live++;
          else if (data.status === 'BAD' || data.status === 'DEAD') bad++;
          else if (data.status === 'FREE') free++;
          else errors++;
          outEl.innerHTML += renderCrResult({ ...data, email: email.trim(), _password: password.trim(), combo: combo.split(' | ')[0].trim() }, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateCrStats(data.status);
          if (data.status === 'LIVE') playAlert('live');
          else if (data.status === 'FREE') playAlert('hold');
        } catch(e) {
          retries++;
          if (retries >= 3) { errors++; outEl.innerHTML += `<div style="padding:6px; font-size:11px; color:#f59e0b;">⚠️ ${email}: ${e.message}</div>`; success = true; }
          else { await new Promise(r => setTimeout(r, 2000)); }
        }
      }
      done++;
      barEl.style.width = `${(done / total * 100).toFixed(1)}%`;
      const elapsed = (Date.now() - startTime) / 1000;
      const speed = done / elapsed;
      const eta = Math.ceil((total - done) / speed);
      statsEl.innerHTML = `<span style="color:#10b981;">${live} LIVE</span> · <span style="color:#38bdf8;">${free} FREE</span> · <span style="color:#f43f5e;">${bad} BAD</span> · <span style="color:#f59e0b;">${errors} ERR</span> · ${done}/${total} · ${speed.toFixed(1)}/s · ETA: ${eta}s`;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);
  crBulkRunning = false;
  crComboFileQueue = [];
  if (crBulkAbort) statsEl.innerHTML += ' · <span style="color:#f59e0b;">STOPPED</span>';
  else statsEl.innerHTML += ' · <span style="color:#10b981;">DONE</span>';
}

function stopCrBulk() { crBulkAbort = true; }

function exportCrHits() {
  const hits = crBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  const text = hits.map(h => `${h.combo} | Sub: ${h.subscription || 'N/A'} | Country: ${h.country || 'N/A'} | Profiles: ${h.profiles || 'N/A'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `crunchyroll_hits_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); showToast(`${hits.length} hits exported`);
}

function copyCrHits() {
  const hits = crBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk dicopy');
  const text = hits.map(h => `${h.combo} | Sub: ${h.subscription || 'N/A'} | Country: ${h.country || 'N/A'} | Profiles: ${h.profiles || 'N/A'}`).join('\n');
  navigator.clipboard.writeText(text).then(() => showToast(`${hits.length} hits copied to clipboard`));
}

document.getElementById('cr-password')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') runCrSingle();
});

// ═══════════════════════════════════════════════════════════════════
// Crunchyroll Session Stats & Donut Chart
// ═══════════════════════════════════════════════════════════════════
const crStats = { live: 0, free: 0, bad: 0, error: 0 };

function updateCrStats(status) {
  if (status === 'LIVE') crStats.live++;
  else if (status === 'FREE') crStats.free++;
  else if (status === 'BAD' || status === 'DEAD') crStats.bad++;
  else crStats.error++;

  const dashboard = document.getElementById('cr-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('cr-stat-live').textContent = crStats.live;
  document.getElementById('cr-stat-free').textContent = crStats.free;
  document.getElementById('cr-stat-bad').textContent = crStats.bad;
  document.getElementById('cr-stat-error').textContent = crStats.error;

  const total = crStats.live + crStats.free + crStats.bad + crStats.error;
  document.getElementById('cr-donut-total').textContent = total;

  const hitRate = total > 0 ? ((crStats.live + crStats.free) / total * 100) : 0;
  document.getElementById('cr-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('cr-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('cr-donut-chart', [
    { val: crStats.live,  color: '#10b981' },
    { val: crStats.free,  color: '#38bdf8' },
    { val: crStats.bad,   color: '#f43f5e' },
    { val: crStats.error, color: '#f59e0b' },
  ]);
  scheduleDashboardRefresh();
}

function resetCrStats() {
  crStats.live = 0; crStats.free = 0; crStats.bad = 0; crStats.error = 0;
  ['cr-stat-live','cr-stat-free','cr-stat-bad','cr-stat-error'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('cr-donut-total').textContent = '0';
  document.getElementById('cr-hit-rate').textContent = '0%';
  document.getElementById('cr-hit-rate-bar').style.width = '0%';
  drawDonutChart('cr-donut-chart', []);
  showToast('Stats direset');
}

// ═══════════════════════════════════════════════════════════════════
// Disney+ Session Stats & Donut Chart
// ═══════════════════════════════════════════════════════════════════
const disneyStats = { live: 0, hold: 0, bad: 0, error: 0 };

function updateDisneyStats(status) {
  if (status === 'LIVE') disneyStats.live++;
  else if (status === 'HOLD') disneyStats.hold++;
  else if (status === 'BAD' || status === 'DEAD') disneyStats.bad++;
  else disneyStats.error++;

  const dashboard = document.getElementById('disney-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('disney-stat-live').textContent = disneyStats.live;
  document.getElementById('disney-stat-hold').textContent = disneyStats.hold;
  document.getElementById('disney-stat-bad').textContent = disneyStats.bad;
  document.getElementById('disney-stat-error').textContent = disneyStats.error;

  const total = disneyStats.live + disneyStats.hold + disneyStats.bad + disneyStats.error;
  document.getElementById('disney-donut-total').textContent = total;

  const hitRate = total > 0 ? ((disneyStats.live + disneyStats.hold) / total * 100) : 0;
  document.getElementById('disney-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('disney-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('disney-donut-chart', [
    { val: disneyStats.live,  color: '#10b981' },
    { val: disneyStats.hold,  color: '#f59e0b' },
    { val: disneyStats.bad,   color: '#f43f5e' },
    { val: disneyStats.error, color: '#94a3b8' },
  ]);
  scheduleDashboardRefresh();
}

function resetDisneyStats() {
  disneyStats.live = 0; disneyStats.hold = 0; disneyStats.bad = 0; disneyStats.error = 0;
  ['disney-stat-live','disney-stat-hold','disney-stat-bad','disney-stat-error'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('disney-donut-total').textContent = '0';
  document.getElementById('disney-hit-rate').textContent = '0%';
  document.getElementById('disney-hit-rate-bar').style.width = '0%';
  drawDonutChart('disney-donut-chart', []);
  showToast('Stats direset');
}

// ═══════════════════════════════════════════════════════════════════
// Shared Donut Chart Renderer (Canvas 2D)
// ═══════════════════════════════════════════════════════════════════
function drawDonutChart(canvasId, segments) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2, r = 42, lineW = 10;

  ctx.clearRect(0, 0, w, h);

  const total = segments.reduce((s, seg) => s + seg.val, 0);
  if (total === 0) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(132,139,159,0.2)';
    ctx.lineWidth = lineW;
    ctx.stroke();
    return;
  }

  let angle = -Math.PI / 2;
  segments.forEach(seg => {
    if (seg.val === 0) return;
    const slice = (seg.val / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, angle, angle + slice);
    ctx.strokeStyle = seg.color;
    ctx.lineWidth = lineW;
    ctx.lineCap = 'butt';
    ctx.stroke();
    angle += slice;
  });
}

// ═══════════════════════════════════════════════════════════════════
// ExpressVPN Account Checker
// ═══════════════════════════════════════════════════════════════════
let evpnBulkRunning = false;
let evpnBulkAbort = false;
let evpnBulkResults = [];

const evpnStats = { premium: 0, trial: 0, free: 0, bad: 0 };

function renderEvpnResult(data, mode = 'single') {
  const statusMap = {
    PREMIUM: ['✅','#10b981','rgba(16,185,129,0.1)'],
    TRIAL: ['🎁','#a855f7','rgba(168,85,247,0.1)'],
    FREE: ['🆓','#38bdf8','rgba(56,189,248,0.1)'],
    BAD: ['❌','#f43f5e','rgba(244,63,94,0.1)'],
    ERROR: ['⚠️','#f59e0b','rgba(245,158,11,0.1)']
  };
  const [icon, color, bg] = statusMap[data.status] || ['❓','var(--text-muted)','rgba(132,139,159,0.1)'];
  const comboText = data.combo || `${data.email || ''}:${data._password || '***'}`;

  if (data.status === 'PREMIUM' || data.status === 'TRIAL' || data.status === 'FREE') {
    const label = data.status === 'PREMIUM' ? 'Premium Account' : data.status === 'TRIAL' ? 'Trial Account' : 'Free Account';
    const cardClass = 'card-out live';

    return `<div class="${mode === 'bulk' ? '' : cardClass}" style="${mode === 'bulk' ? `padding:16px; border-left:4px solid ${color}; background:${bg}; margin-bottom:10px; border-radius:var(--radius-lg);` : ''}">
      <div class="card-header-status" style="color:${color};">
        <span>${icon}</span> <span>${label}</span>
        <span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ${escapeHtml(data.route || 'Direct')}</span>
      </div>

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong>${escapeHtml(data.email || 'N/A')}</strong></div>
        <div class="meta-box"><span>Status</span><strong style="color:${color};">${escapeHtml(data.status)}</strong></div>
        <div class="meta-box"><span>Plan</span><strong>${escapeHtml(data.plan || 'N/A')}</strong></div>
        <div class="meta-box"><span>Expire Date</span><strong>${escapeHtml(data.expire_date || 'N/A')}</strong></div>
        <div class="meta-box"><span>Days Left</span><strong style="color:${(data.days_left||0) > 30 ? '#10b981' : (data.days_left||0) > 7 ? '#f59e0b' : '#f43f5e'};">${data.days_left != null ? escapeHtml(data.days_left + ' days') : 'N/A'}</strong></div>
        <div class="meta-box"><span>Auto Renew</span><strong style="color:${data.auto_renew ? 'var(--live)' : 'var(--dead)'};">${data.auto_renew ? '✅ Yes' : '❌ No'}</strong></div>
        <div class="meta-box"><span>Payment</span><strong>${escapeHtml(data.payment_method || 'N/A')}</strong></div>
        ${data.ovpn_username ? `<div class="meta-box"><span>OVPN User</span><strong style="font-family:'JetBrains Mono',monospace; font-size:11px;">${escapeHtml(data.ovpn_username)}</strong></div>` : ''}
        ${data.ovpn_password ? `<div class="meta-box"><span>OVPN Pass</span><strong style="font-family:'JetBrains Mono',monospace; font-size:11px;">${escapeHtml(data.ovpn_password)}</strong></div>` : ''}
      </div>

      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="btn-secondary" onclick="copyText('${escapeAttr(comboText)}', 'Combo disalin!')">📋 Copy Combo</button>
        <button class="btn-secondary" onclick="copyText('${escapeAttr(data.email || '')}', 'Email disalin!')">📧 Copy Email</button>
        ${data.ovpn_username ? `<button class="btn-secondary" onclick="copyText('${escapeAttr(data.ovpn_username + ':' + (data.ovpn_password||''))}', 'OVPN creds disalin!')">🔑 Copy OVPN</button>` : ''}
      </div>
    </div>`;
  }

  // BAD / ERROR
  return `<div class="${mode === 'bulk' ? '' : 'card-out dead'}" style="${mode === 'bulk' ? `padding:10px; border-left:3px solid ${color}; background:${bg}; margin-bottom:6px; border-radius:var(--radius-sm);` : ''}">
    <div class="card-header-status" style="color:${color};">
      <span>${icon}</span> <span>${data.status === 'BAD' ? 'Wrong Credentials' : data.status}</span>
    </div>
    <div style="color:var(--text-muted); font-size:12px;">${escapeHtml(data.reason || data.email || 'Akun tidak valid')}</div>
  </div>`;
}

function updateEvpnStats(status) {
  if (status === 'PREMIUM') evpnStats.premium++;
  else if (status === 'TRIAL') evpnStats.trial++;
  else if (status === 'FREE') evpnStats.free++;
  else evpnStats.bad++;

  const dashboard = document.getElementById('evpn-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('evpn-stat-premium').textContent = evpnStats.premium;
  document.getElementById('evpn-stat-trial').textContent = evpnStats.trial;
  document.getElementById('evpn-stat-free').textContent = evpnStats.free;
  document.getElementById('evpn-stat-bad').textContent = evpnStats.bad;

  const total = evpnStats.premium + evpnStats.trial + evpnStats.free + evpnStats.bad;
  document.getElementById('evpn-donut-total').textContent = total;

  const hitRate = total > 0 ? ((evpnStats.premium + evpnStats.trial) / total * 100) : 0;
  document.getElementById('evpn-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('evpn-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('evpn-donut-chart', [
    { val: evpnStats.premium, color: '#10b981' },
    { val: evpnStats.trial,   color: '#a855f7' },
    { val: evpnStats.free,    color: '#38bdf8' },
    { val: evpnStats.bad,     color: '#f43f5e' },
  ]);
  scheduleDashboardRefresh();
}

function resetEvpnStats() {
  evpnStats.premium = 0; evpnStats.trial = 0; evpnStats.free = 0; evpnStats.bad = 0;
  ['evpn-stat-premium','evpn-stat-trial','evpn-stat-free','evpn-stat-bad'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('evpn-donut-total').textContent = '0';
  document.getElementById('evpn-hit-rate').textContent = '0%';
  document.getElementById('evpn-hit-rate-bar').style.width = '0%';
  drawDonutChart('evpn-donut-chart', []);
  showToast('Stats direset');
}

// ═══════ ExpressVPN Combo File Handler ═══════
let evpnComboFileQueue = [];

function handleEvpnComboFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('evpn-combo-file-info');
  const textarea = document.getElementById('evpn-bulk-input');
  evpnComboFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }
      const lines = content.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.includes(':'));
      lines.forEach(l => evpnComboFileQueue.push(l));
      processed++;
      if (processed === total) {
        fileInfo.textContent = `✅ ${total} file dimuat → ${evpnComboFileQueue.length} combo ditemukan`;
        fileInfo.style.color = '#10b981';
        textarea.value = evpnComboFileQueue.join('\n');
        showToast(`${evpnComboFileQueue.length} combos dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });

  // Reset file input supaya file yang sama bisa diupload lagi
  document.getElementById('evpn-combo-file-input').value = '';
}

async function runEvpnSingle() {
  const email = document.getElementById('evpn-email').value.trim();
  const password = document.getElementById('evpn-password').value.trim();
  if (!email || !password) return showToast('Email dan password wajib diisi');
  const btn = document.getElementById('evpn-single-btn');
  const btnText = document.getElementById('evpn-single-btn-text');
  const outEl = document.getElementById('evpn-single-out');
  const useProxy = document.getElementById('evpn-proxy-toggle')?.checked ?? false;
  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    const res = await fetch('/api/expressvpn/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ email, password, use_proxy: useProxy })
    });
    const data = await res.json();
    const mergedData = { ...data, _password: password, combo: `${email}:${password}` };

    outEl.innerHTML = renderEvpnResult(mergedData, 'single');
    outEl.style.display = 'block';
    updateEvpnStats(data.status);

    if (data.status === 'PREMIUM') playAlert('4k');
    else if (data.status === 'TRIAL') playAlert('live');
    else if (data.status === 'FREE') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Request Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = 'Check ExpressVPN Account';
}

async function runEvpnBulk() {
  const raw = document.getElementById('evpn-bulk-input').value.trim();
  if (!raw) return showToast('Paste combo list dulu');
  if (evpnBulkRunning) return;
  const lines = raw.split('\n').map(l => l.trim()).filter(l => l && l.includes(':'));
  if (!lines.length) return showToast('Tidak ada combo valid');
  evpnBulkRunning = true; evpnBulkAbort = false; evpnBulkResults = [];
  const outEl = document.getElementById('evpn-bulk-out');
  const statsEl = document.getElementById('evpn-bulk-stats');
  const progressEl = document.getElementById('evpn-bulk-progress');
  const barEl = document.getElementById('evpn-progress-bar');
  const useProxy = document.getElementById('evpn-proxy-toggle')?.checked ?? false;
  outEl.innerHTML = ''; progressEl.style.display = 'block'; barEl.style.width = '0%';
  let done = 0, premium = 0, trial = 0, free = 0, bad = 0, errors = 0;
  const total = lines.length;
  const startTime = Date.now();
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < lines.length && !evpnBulkAbort) {
      const idx = currentIndex++;
      const combo = lines[idx];
      const [email, ...pwParts] = combo.split(' | ')[0].trim().split(':');
      const password = pwParts.join(':');
      let retries = 0, success = false;
      while (retries < 3 && !success) {
        try {
          const res = await fetch('/api/expressvpn/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ email: email.trim(), password: password.trim(), use_proxy: useProxy })
          });
          if (res.status === 401) { outEl.innerHTML += `<div style="padding:10px; color:#f43f5e; font-weight:600;">🔒 PIN tidak valid</div>`; evpnBulkAbort = true; break; }
          if (res.status === 429) { retries++; await new Promise(r => setTimeout(r, 3000 * retries)); continue; }
          const data = await res.json(); data.combo = combo; evpnBulkResults.push(data);
          success = true;
          if (data.status === 'PREMIUM') premium++;
          else if (data.status === 'TRIAL') trial++;
          else if (data.status === 'FREE') free++;
          else if (data.status === 'BAD' || data.status === 'DEAD') bad++;
          else errors++;
          outEl.innerHTML += renderEvpnResult({ ...data, email: email.trim(), _password: password.trim(), combo: combo.split(' | ')[0].trim() }, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateEvpnStats(data.status);
          if (data.status === 'PREMIUM') playAlert('4k');
          else if (data.status === 'TRIAL') playAlert('live');
          else if (data.status === 'FREE') playAlert('hold');
        } catch(e) {
          retries++;
          if (retries >= 3) { errors++; outEl.innerHTML += `<div style="padding:6px; font-size:11px; color:#f59e0b;">⚠️ ${email}: ${e.message}</div>`; success = true; }
          else { await new Promise(r => setTimeout(r, 2000)); }
        }
      }
      done++;
      barEl.style.width = `${(done / total * 100).toFixed(1)}%`;
      const elapsed = (Date.now() - startTime) / 1000;
      const speed = done / elapsed;
      const eta = Math.ceil((total - done) / speed);
      statsEl.innerHTML = `<span style="color:#10b981;">${premium} PREMIUM</span> · <span style="color:#a855f7;">${trial} TRIAL</span> · <span style="color:#38bdf8;">${free} FREE</span> · <span style="color:#f43f5e;">${bad} BAD</span> · <span style="color:#f59e0b;">${errors} ERR</span> · ${done}/${total} · ${speed.toFixed(1)}/s · ETA: ${eta}s`;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);
  evpnBulkRunning = false;
  if (evpnBulkAbort) statsEl.innerHTML += ' · <span style="color:#f59e0b;">STOPPED</span>';
  else statsEl.innerHTML += ' · <span style="color:#10b981;">DONE</span>';
}

function stopEvpnBulk() { evpnBulkAbort = true; }

function exportEvpnHits() {
  const hits = evpnBulkResults.filter(r => r.status === 'PREMIUM' || r.status === 'TRIAL');
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  const text = hits.map(h => `${h.combo || h.email+':***'} | Status: ${h.status} | Plan: ${h.plan || 'N/A'} | Expire: ${h.expire_date || 'N/A'} | Days: ${h.days_left ?? 'N/A'} | OVPN: ${h.ovpn_username || 'N/A'}/${h.ovpn_password || 'N/A'} | Payment: ${h.payment_method || 'N/A'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `expressvpn_hits_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); showToast(`${hits.length} hits exported`);
}

function copyEvpnHits() {
  const hits = evpnBulkResults.filter(r => r.status === 'PREMIUM' || r.status === 'TRIAL');
  if (!hits.length) return showToast('Belum ada hits untuk dicopy');
  const text = hits.map(h => `${h.combo || h.email+':***'} | Status: ${h.status} | Plan: ${h.plan || 'N/A'} | Expire: ${h.expire_date || 'N/A'} | Days: ${h.days_left ?? 'N/A'}`).join('\n');
  navigator.clipboard.writeText(text).then(() => showToast(`${hits.length} hits copied to clipboard`));
}

document.getElementById('evpn-password')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') runEvpnSingle();
});

// ═══════════════════════════════════════════════════════════════════
// Spotify Cookie Checker Functions
// ═══════════════════════════════════════════════════════════════════

let spotifyBulkRunning = false;
let spotifyBulkAbort = false;
let spotifyBulkResults = [];

const spotifyStats = { live: 0, free: 0, dead: 0, error: 0 };

function renderSpotifyResult(data, mode = 'single') {
  const statusMap = {
    LIVE: ['✅','#1DB954','rgba(29,185,84,0.1)'],
    FREE: ['🆓','#38bdf8','rgba(56,189,248,0.1)'],
    DEAD: ['❌','#f43f5e','rgba(244,63,94,0.1)'],
    ERROR: ['⚠️','#f59e0b','rgba(245,158,11,0.1)']
  };
  const [icon, color, bg] = statusMap[data.status] || ['❓','var(--text-muted)','rgba(132,139,159,0.1)'];

  if (data.status === 'LIVE' || data.status === 'FREE') {
    const label = data.status === 'LIVE' ? `${data.plan || 'Premium'} Account` : 'Free Account';
    const cardClass = 'card-out live';

    let familyInfo = '';
    if (data.family_members > 0 || data.free_slots != null) {
      familyInfo = `
        <div class="meta-box"><span>Family Members</span><strong>${data.family_members || 0}${data.family_max_capacity ? '/' + data.family_max_capacity : ''}</strong></div>
        <div class="meta-box"><span>Free Slots</span><strong style="color:${(data.free_slots || 0) > 0 ? '#1DB954' : 'var(--dead)'};">${data.free_slots != null ? data.free_slots : 'N/A'}</strong></div>
      `;
    }
    if (data.invite_link) {
      familyInfo += `<div class="meta-box" style="grid-column:1/-1;"><span>Invite Link</span><strong style="font-size:11px; word-break:break-all;"><a href="${data.invite_link}" target="_blank" style="color:#1DB954; text-decoration:none;">${data.invite_link}</a></strong></div>`;
    }
    if (data.address) {
      familyInfo += `<div class="meta-box"><span>Address</span><strong style="font-size:11px;">${escapeHtml(data.address)}</strong></div>`;
    }

    return `<div class="${mode === 'bulk' ? '' : cardClass}" style="${mode === 'bulk' ? `padding:16px; border-left:4px solid ${color}; background:${bg}; margin-bottom:10px; border-radius:var(--radius-lg);` : ''}">
      <div class="card-header-status" style="color:${color};">
        <span>${icon}</span> <span>${label}</span>
        <span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ${escapeHtml(data.route || 'Direct')}</span>
      </div>

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong>${escapeHtml(data.email || 'N/A')}</strong></div>
        <div class="meta-box"><span>Plan</span><strong style="#1DB954;">${escapeHtml(data.plan || 'N/A')}</strong></div>
        <div class="meta-box"><span>Country</span><strong>${escapeHtml(data.country || 'N/A')}</strong></div>
        <div class="meta-box"><span>Next Payment</span><strong>${escapeHtml(data.next_payment_date || 'N/A')}</strong></div>
        <div class="meta-box"><span>Auto-Renew</span><strong style="color:${data.is_recurring ? 'var(--live)' : 'var(--text-muted)'};">${data.is_recurring === true ? '✅ Yes' : data.is_recurring === false ? '❌ No' : 'N/A'}</strong></div>
        <div class="meta-box"><span>Role</span><strong>${data.is_owner === true ? '👑 Owner' : data.is_child_account ? '👤 Sub Account' : data.is_owner === false ? '👤 Member' : 'N/A'}</strong></div>
        ${familyInfo}
      </div>

      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="btn-secondary" onclick="copyText('${escapeAttr(data.email || '')}', 'Email disalin!')">📧 Copy Email</button>
        ${data.invite_link ? `<button class="btn-secondary" onclick="copyText('${escapeAttr(data.invite_link)}', 'Invite link disalin!')">🔗 Copy Invite</button>` : ''}
      </div>
    </div>`;
  }

  // DEAD / ERROR
  return `<div class="${mode === 'bulk' ? '' : 'card-out dead'}" style="${mode === 'bulk' ? `padding:10px; border-left:3px solid ${color}; background:${bg}; margin-bottom:6px; border-radius:var(--radius-sm);` : ''}">
    <div class="card-header-status" style="color:${color};">
      <span>${icon}</span> <span>${data.status === 'DEAD' ? 'Dead / Expired Cookie' : data.status}</span>
    </div>
    <div style="color:var(--text-muted); font-size:12px;">${escapeHtml(data.reason || 'Cookie invalid or expired')}</div>
  </div>`;
}

function updateSpotifyStats(status) {
  if (status === 'LIVE') spotifyStats.live++;
  else if (status === 'FREE') spotifyStats.free++;
  else if (status === 'DEAD') spotifyStats.dead++;
  else spotifyStats.error++;

  const dashboard = document.getElementById('spotify-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('spotify-stat-live').textContent = spotifyStats.live;
  document.getElementById('spotify-stat-free').textContent = spotifyStats.free;
  document.getElementById('spotify-stat-dead').textContent = spotifyStats.dead;
  document.getElementById('spotify-stat-error').textContent = spotifyStats.error;

  const total = spotifyStats.live + spotifyStats.free + spotifyStats.dead + spotifyStats.error;
  document.getElementById('spotify-donut-total').textContent = total;

  const hitRate = total > 0 ? ((spotifyStats.live) / total * 100) : 0;
  document.getElementById('spotify-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('spotify-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('spotify-donut-chart', [
    { val: spotifyStats.live,  color: '#1DB954' },
    { val: spotifyStats.free,  color: '#38bdf8' },
    { val: spotifyStats.dead,  color: '#f43f5e' },
    { val: spotifyStats.error, color: '#f59e0b' },
  ]);
  scheduleDashboardRefresh();
}

function resetSpotifyStats() {
  spotifyStats.live = 0; spotifyStats.free = 0; spotifyStats.dead = 0; spotifyStats.error = 0;
  ['spotify-stat-live','spotify-stat-free','spotify-stat-dead','spotify-stat-error'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('spotify-donut-total').textContent = '0';
  document.getElementById('spotify-hit-rate').textContent = '0%';
  document.getElementById('spotify-hit-rate-bar').style.width = '0%';
  drawDonutChart('spotify-donut-chart', []);
  showToast('Stats direset');
}

async function runSpotifySingle() {
  const cookie = document.getElementById('spotify-cookie').value.trim();
  if (!cookie) return showToast('Paste sp_dc cookie terlebih dahulu');
  const btn = document.getElementById('spotify-single-btn');
  const btnText = document.getElementById('spotify-single-btn-text');
  const outEl = document.getElementById('spotify-single-out');
  const useProxy = document.getElementById('spotify-proxy-toggle')?.checked ?? false;
  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    const res = await fetch('/api/spotify/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ cookie, use_proxy: useProxy })
    });
    const data = await res.json();

    outEl.innerHTML = renderSpotifyResult(data, 'single');
    outEl.style.display = 'block';
    updateSpotifyStats(data.status);

    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'FREE') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Request Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = 'Check Spotify Account';
}

// ---- Spotify File Upload Handler ----
let spotifyFileQueue = [];

function handleSpotifyFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('spotify-file-info');
  const textarea = document.getElementById('spotify-bulk-input');
  spotifyFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }

      // JSON array: extract each cookie object as a separate entry
      if (file.name.endsWith('.json')) {
        try {
          const arr = JSON.parse(content);
          if (Array.isArray(arr) && arr.length > 0) {
            // If it's an array of cookie objects (has 'name'/'domain'), treat whole file as one cookie set
            if (arr[0] && arr[0].name) {
              spotifyFileQueue.push(JSON.stringify(arr));
            } else {
              // Array of strings or sp_dc values
              arr.forEach(item => {
                const val = typeof item === 'string' ? item.trim() : JSON.stringify(item);
                if (val) spotifyFileQueue.push(val);
              });
            }
          }
        } catch(ex) {
          // Not valid JSON, treat as plain text
          spotifyFileQueue.push(content);
        }
      } else {
        // .txt / .cookie — could be:
        // 1. Multi-account Netscape file (separated by "# Netscape HTTP Cookie File" headers)
        // 2. A single Netscape cookie file → one cookie set
        // 3. A list of sp_dc values (one per line)
        const allLines = content.split('\n');
        const hasNetscape = allLines.some(l => l.trim().split('\t').length >= 7);

        if (hasNetscape) {
          // Split multi-account Netscape files by "# Netscape HTTP Cookie File" header
          const blocks = [];
          let currentBlock = [];
          for (const rawLine of allLines) {
            const line = rawLine.trim();
            // New block starts at "# Netscape HTTP Cookie File" (case-insensitive)
            if (line.toLowerCase().startsWith('# netscape http cookie file') && currentBlock.length > 0) {
              // Save previous block if it has actual cookie lines
              const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
              if (cookieLines.length > 0) blocks.push(cookieLines.join('\n'));
              currentBlock = [];
            }
            currentBlock.push(line);
          }
          // Push last block
          if (currentBlock.length > 0) {
            const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
            if (cookieLines.length > 0) blocks.push(cookieLines.join('\n'));
          }
          // If no blocks found (single file without header), treat all cookie lines as one set
          if (blocks.length === 0) {
            const cookieLines = allLines.map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
            if (cookieLines.length > 0) blocks.push(cookieLines.join('\n'));
          }
          blocks.forEach(b => spotifyFileQueue.push(b));
        } else {
          // Each non-comment line is a separate sp_dc cookie
          const cleanLines = allLines.map(l => l.trim()).filter(l => l && !l.startsWith('#'));
          cleanLines.forEach(l => spotifyFileQueue.push(l));
        }
      }

      processed++;
      if (processed === total) {
        const totalCookies = spotifyFileQueue.length;
        fileInfo.textContent = `✅ ${total} file dimuat → ${totalCookies} cookie ditemukan`;
        fileInfo.style.color = 'var(--primary)';
        // Also fill textarea with preview
        textarea.value = spotifyFileQueue.join('\n\n');
        showToast(`${totalCookies} cookies dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) {
        fileInfo.textContent = `⚠️ Beberapa file gagal dimuat`;
        fileInfo.style.color = 'var(--dead)';
      }
    };
    reader.readAsText(file);
  });
}

async function runSpotifyBulk() {
  // Combine file queue + textarea
  let lines = [];
  if (spotifyFileQueue.length > 0) {
    lines = [...spotifyFileQueue];
  }
  const raw = document.getElementById('spotify-bulk-input').value.trim();
  const existing = new Set(lines);
  if (raw) {
    // Parse textarea: detect multi-account Netscape format
    const allRawLines = raw.split('\n');
    const hasNetscapeHeader = allRawLines.some(l => l.trim().toLowerCase().startsWith('# netscape http cookie file'));
    const hasTabCookies = allRawLines.some(l => l.trim().split('\t').length >= 7);

    if (hasNetscapeHeader && hasTabCookies) {
      // Multi-account Netscape: split by "# Netscape HTTP Cookie File" headers
      let currentBlock = [];
      for (const rawLine of allRawLines) {
        const line = rawLine.trim();
        if (line.toLowerCase().startsWith('# netscape http cookie file') && currentBlock.length > 0) {
          const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
          if (cookieLines.length > 0) {
            const block = cookieLines.join('\n');
            if (!existing.has(block)) lines.push(block);
          }
          currentBlock = [];
        }
        currentBlock.push(line);
      }
      if (currentBlock.length > 0) {
        const cookieLines = currentBlock.filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
        if (cookieLines.length > 0) {
          const block = cookieLines.join('\n');
          if (!existing.has(block)) lines.push(block);
        }
      }
    } else if (hasTabCookies) {
      // Single Netscape cookie set in textarea
      const cookieLines = allRawLines.map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.split('\t').length >= 7);
      if (cookieLines.length > 0) {
        const block = cookieLines.join('\n');
        if (!existing.has(block)) lines.push(block);
      }
    } else {
      // Plain sp_dc values or key=value pairs
      let textLines;
      if (raw.includes('\n\n')) {
        textLines = raw.split(/\n\s*\n/).map(b => b.trim()).filter(b => b);
      } else {
        textLines = raw.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
      }
      textLines.forEach(l => { if (!existing.has(l)) lines.push(l); });
    }
  }
  if (!lines.length) return showToast('Upload file atau paste cookies terlebih dahulu');
  if (spotifyBulkRunning) return;

  spotifyBulkRunning = true; spotifyBulkAbort = false; spotifyBulkResults = [];
  const outEl = document.getElementById('spotify-bulk-out');
  const statsEl = document.getElementById('spotify-bulk-stats');
  const progressEl = document.getElementById('spotify-bulk-progress');
  const barEl = document.getElementById('spotify-progress-bar');
  const useProxy = document.getElementById('spotify-proxy-toggle')?.checked ?? false;
  outEl.innerHTML = ''; progressEl.style.display = 'block'; barEl.style.width = '0%';
  let done = 0, live = 0, free = 0, dead = 0, errors = 0;
  const total = lines.length;
  const startTime = Date.now();
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < lines.length && !spotifyBulkAbort) {
      const idx = currentIndex++;
      const cookie = lines[idx];
      let retries = 0, success = false;
      while (retries < 3 && !success) {
        try {
          const res = await fetch('/api/spotify/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ cookie, use_proxy: useProxy })
          });
          if (res.status === 401) { outEl.innerHTML += `<div style="padding:10px; color:#f43f5e; font-weight:600;">🔒 PIN tidak valid</div>`; spotifyBulkAbort = true; break; }
          if (res.status === 429) { retries++; await new Promise(r => setTimeout(r, 3000 * retries)); continue; }
          const data = await res.json(); data.cookie = cookie; spotifyBulkResults.push(data);
          success = true;
          if (data.status === 'LIVE') live++;
          else if (data.status === 'FREE') free++;
          else if (data.status === 'DEAD') dead++;
          else errors++;
          outEl.innerHTML += renderSpotifyResult(data, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateSpotifyStats(data.status);
          if (data.status === 'LIVE') playAlert('live');
        } catch(e) {
          retries++;
          if (retries >= 3) { errors++; outEl.innerHTML += `<div style="padding:6px; font-size:11px; color:#f59e0b;">⚠️ Error: ${e.message}</div>`; success = true; }
          else { await new Promise(r => setTimeout(r, 2000)); }
        }
      }
      done++;
      barEl.style.width = `${(done / total * 100).toFixed(1)}%`;
      const elapsed = (Date.now() - startTime) / 1000;
      const speed = done / elapsed;
      const eta = Math.ceil((total - done) / speed);
      statsEl.innerHTML = `<span style="color:#1DB954;">${live} LIVE</span> · <span style="color:#38bdf8;">${free} FREE</span> · <span style="color:#f43f5e;">${dead} DEAD</span> · <span style="color:#f59e0b;">${errors} ERR</span> · ${done}/${total} · ${speed.toFixed(1)}/s · ETA: ${eta}s`;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);
  spotifyBulkRunning = false;
  if (spotifyBulkAbort) statsEl.innerHTML += ' · <span style="color:#f59e0b;">STOPPED</span>';
  else statsEl.innerHTML += ' · <span style="color:#1DB954;">DONE</span>';
}

function stopSpotifyBulk() { spotifyBulkAbort = true; }

function clearSpotifyFileUpload() {
  spotifyFileQueue = [];
  const fileInfo = document.getElementById('spotify-file-info');
  if (fileInfo) { fileInfo.style.display = 'none'; fileInfo.textContent = ''; }
  const input = document.getElementById('spotify-file-input');
  if (input) input.value = '';
}

function exportSpotifyHits() {
  const hits = spotifyBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  const text = hits.map(h => `${h.email || 'N/A'} | Plan: ${h.plan || 'N/A'} | Country: ${h.country || 'N/A'} | Next: ${h.next_payment_date || 'N/A'} | Owner: ${h.is_owner ? 'Yes' : 'No'} | Slots: ${h.free_slots ?? 'N/A'} | Cookie: ${h.cookie || 'N/A'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `spotify_hits_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); showToast(`${hits.length} hits exported`);
}

function copySpotifyHits() {
  const hits = spotifyBulkResults.filter(r => r.status === 'LIVE');
  if (!hits.length) return showToast('Belum ada hits untuk dicopy');
  const text = hits.map(h => `${h.email || 'N/A'} | Plan: ${h.plan || 'N/A'} | Country: ${h.country || 'N/A'} | Next: ${h.next_payment_date || 'N/A'} | Cookie: ${h.cookie || 'N/A'}`).join('\n');
  navigator.clipboard.writeText(text).then(() => showToast(`${hits.length} hits copied to clipboard`));
}

// ═══════════════════════════════════════════════════════════════════
// Outlook / Hotmail Account Checker
// ═══════════════════════════════════════════════════════════════════
let outlookBulkRunning = false;
let outlookBulkAbort = false;
let outlookBulkResults = [];
const outlookStats = { live: 0, twofa: 0, bad: 0, locked: 0 };

function outlookStatusColor(status) {
  const m = { LIVE: '#10b981', '2FA': '#38bdf8', BAD: '#f43f5e', LOCKED: '#f59e0b', PHONE_LOCKED: '#f59e0b', ERROR: '#94a3b8' };
  return m[status] || 'var(--text-muted)';
}

function outlookStatusBg(status) {
  const m = { LIVE: 'rgba(16,185,129,0.1)', '2FA': 'rgba(56,189,248,0.1)', BAD: 'rgba(244,63,94,0.1)', LOCKED: 'rgba(245,158,11,0.1)', PHONE_LOCKED: 'rgba(245,158,11,0.1)', ERROR: 'rgba(148,163,184,0.1)' };
  return m[status] || 'rgba(132,139,159,0.1)';
}

function renderOutlookResult(data, mode = 'single') {
  const color = outlookStatusColor(data.status);
  const statusIcon = { LIVE: '✅', '2FA': '🔐', BAD: '❌', LOCKED: '🔒', PHONE_LOCKED: '📱', ERROR: '⚠️' }[data.status] || '❓';
  const comboText = data.combo || `${data.email || ''}:${data._password || '***'}`;
  const statusLabel = {
    LIVE: 'Account Valid',
    '2FA': '2FA Protected',
    BAD: 'Invalid Credentials',
    LOCKED: 'Account Locked',
    PHONE_LOCKED: 'Phone Locked',
    ERROR: 'Check Failed'
  }[data.status] || data.status;

  if (data.status === 'LIVE' || data.status === '2FA') {
    const is2FA = data.status === '2FA';
    const cardClass = is2FA ? 'card-out hold' : 'card-out live';

    return `<div class="${mode === 'bulk' ? '' : cardClass}" style="${mode === 'bulk' ? `padding:16px; border-left:4px solid ${color}; background:${outlookStatusBg(data.status)}; margin-bottom:10px; border-radius:var(--radius-lg);` : ''}">
      <div class="card-header-status" style="color:${color};">
        <span>${statusIcon}</span> <span>${statusLabel}</span>
        <span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ${escapeHtml(data.route || 'Direct')}</span>
      </div>

      ${is2FA ? `
      <div style="background:rgba(56, 189, 248, 0.12); border:1px solid rgba(56, 189, 248, 0.3); color:#7dd3fc; padding:10px 14px; border-radius:var(--radius-sm); margin-bottom:12px; font-size:12px; display:flex; align-items:center; gap:8px;">
        <span>🔐</span> <span><strong>2FA Active:</strong> Akun valid tapi dilindungi Two-Factor Authentication. Password benar, butuh kode verifikasi.</span>
      </div>
      ` : ''}

      <div class="grid-meta">
        <div class="meta-box"><span>Email</span><strong>${escapeHtml(data.email || 'N/A')}</strong></div>
        <div class="meta-box"><span>Status</span><strong style="color:${color};">${escapeHtml(data.status)}</strong></div>
        <div class="meta-box"><span>Detail</span><strong>${escapeHtml(data.reason || 'N/A')}</strong></div>
        <div class="meta-box"><span>Route</span><strong>${escapeHtml(data.route || 'Direct')}</strong></div>
      </div>

      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="btn-secondary" onclick="copyText('${escapeAttr(comboText)}', 'Combo disalin!')">📋 Copy Combo</button>
        <button class="btn-secondary" onclick="copyText('${escapeAttr(data.email || '')}', 'Email disalin!')">📧 Copy Email</button>
      </div>
    </div>`;
  }

  // BAD / LOCKED / ERROR
  return `<div class="${mode === 'bulk' ? '' : 'card-out dead'}" style="${mode === 'bulk' ? `padding:10px; border-left:3px solid ${color}; background:${outlookStatusBg(data.status)}; margin-bottom:6px; border-radius:var(--radius-sm);` : ''}">
    <div class="card-header-status" style="color:${color};">
      <span>${statusIcon}</span> <span>${statusLabel}</span>
    </div>
    <div style="color:var(--text-muted); font-size:12px;">${escapeHtml(data.reason || data.email || 'Akun tidak valid')}</div>
  </div>`;
}

function updateOutlookStats(status) {
  if (status === 'LIVE') outlookStats.live++;
  else if (status === '2FA') outlookStats.twofa++;
  else if (status === 'BAD') outlookStats.bad++;
  else if (status === 'LOCKED' || status === 'PHONE_LOCKED') outlookStats.locked++;

  const dashboard = document.getElementById('outlook-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('outlook-stat-live').textContent = outlookStats.live;
  document.getElementById('outlook-stat-2fa').textContent = outlookStats.twofa;
  document.getElementById('outlook-stat-bad').textContent = outlookStats.bad;
  document.getElementById('outlook-stat-locked').textContent = outlookStats.locked;

  const total = outlookStats.live + outlookStats.twofa + outlookStats.bad + outlookStats.locked;
  document.getElementById('outlook-donut-total').textContent = total;

  const hitRate = total > 0 ? ((outlookStats.live + outlookStats.twofa) / total * 100) : 0;
  document.getElementById('outlook-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('outlook-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('outlook-donut-chart', [
    { val: outlookStats.live,   color: '#10b981' },
    { val: outlookStats.twofa,  color: '#38bdf8' },
    { val: outlookStats.bad,    color: '#f43f5e' },
    { val: outlookStats.locked, color: '#f59e0b' },
  ]);
  scheduleDashboardRefresh();
}

function resetOutlookStats() {
  outlookStats.live = 0; outlookStats.twofa = 0; outlookStats.bad = 0; outlookStats.locked = 0;
  ['outlook-stat-live','outlook-stat-2fa','outlook-stat-bad','outlook-stat-locked'].forEach(id => document.getElementById(id).textContent = '0');
  document.getElementById('outlook-donut-total').textContent = '0';
  document.getElementById('outlook-hit-rate').textContent = '0%';
  document.getElementById('outlook-hit-rate-bar').style.width = '0%';
  drawDonutChart('outlook-donut-chart', []);
  showToast('Stats direset');
}

// ═══════ Outlook Combo File Handler ═══════
let outlookComboFileQueue = [];

function handleOutlookComboFiles(files) {
  if (!files || !files.length) return;
  const fileInfo = document.getElementById('outlook-combo-file-info');
  const textarea = document.getElementById('outlook-bulk-input');
  outlookComboFileQueue = [];
  let processed = 0;
  const total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = `⏳ Memuat ${total} file...`;

  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const content = e.target.result.trim();
      if (!content) { processed++; return; }
      const lines = content.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#') && l.includes(':'));
      lines.forEach(l => outlookComboFileQueue.push(l));
      processed++;
      if (processed === total) {
        fileInfo.textContent = `✅ ${total} file dimuat → ${outlookComboFileQueue.length} combo ditemukan`;
        fileInfo.style.color = '#10b981';
        textarea.value = outlookComboFileQueue.join('\n');
        showToast(`${outlookComboFileQueue.length} combos dari ${total} file siap dicheck`);
      }
    };
    reader.onerror = () => {
      processed++;
      if (processed === total) { fileInfo.textContent = '⚠️ Beberapa file gagal dimuat'; fileInfo.style.color = 'var(--dead)'; }
    };
    reader.readAsText(file, 'utf-8');
  });

  document.getElementById('outlook-combo-file-input').value = '';
}

async function runOutlookSingle() {
  const email = document.getElementById('outlook-email').value.trim();
  const password = document.getElementById('outlook-password').value.trim();
  if (!email || !password) return showToast('Email dan password wajib diisi');

  const btn = document.getElementById('outlook-single-btn');
  const btnText = document.getElementById('outlook-single-btn-text');
  const outEl = document.getElementById('outlook-single-out');
  const useProxy = document.getElementById('outlook-proxy-toggle')?.checked ?? false;

  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    const res = await fetch('/api/outlook/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ email, password, use_proxy: useProxy })
    });
    const data = await res.json();
    const mergedData = { ...data, _password: password, combo: `${email}:${password}` };

    outEl.innerHTML = renderOutlookResult(mergedData, 'single');
    outEl.style.display = 'block';
    updateOutlookStats(data.status);

    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === '2FA') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = `
      <div class="card-header-status" style="color:var(--dead);">
        <span style="font-size:20px;">❌</span> <span>Request Gagal</span>
      </div>
      <div style="color:var(--text-muted); font-size:12.5px;">${e.message}</div>
    `;
    outEl.style.display = 'block';
  }

  btn.disabled = false;
  btnText.textContent = 'Check Outlook Account';
}

async function runOutlookBulk() {
  const raw = document.getElementById('outlook-bulk-input').value.trim();
  if (!raw) return showToast('Paste combo list dulu');
  if (outlookBulkRunning) return;

  const lines = raw.split('\n').map(l => l.trim()).filter(l => l && l.includes(':'));
  if (!lines.length) return showToast('Tidak ada combo valid');

  outlookBulkRunning = true;
  outlookBulkAbort = false;
  outlookBulkResults = [];

  const outEl = document.getElementById('outlook-bulk-out');
  const statsEl = document.getElementById('outlook-bulk-stats');
  const progressEl = document.getElementById('outlook-bulk-progress');
  const barEl = document.getElementById('outlook-progress-bar');
  const useProxy = document.getElementById('outlook-proxy-toggle')?.checked ?? false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  let done = 0, live = 0, bad = 0, errors = 0;
  const total = lines.length;
  const startTime = Date.now();
  let currentIndex = 0;
  const concurrency = 3;

  async function worker() {
    while (currentIndex < lines.length && !outlookBulkAbort) {
      const idx = currentIndex++;
      const combo = lines[idx];

      const [email, ...pwParts] = combo.split(' | ')[0].trim().split(':');
      const password = pwParts.join(':');

      let retries = 0;
      let success = false;
      while (retries < 3 && !success) {
        try {
          const res = await fetch('/api/outlook/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ email: email.trim(), password: password.trim(), use_proxy: useProxy })
          });
          if (res.status === 429) {
            outlookBulkAbort = true;
            showToast('Rate limit exceeded — stopping bulk');
            break;
          }
          const data = await res.json();
          success = true;

          outlookBulkResults.push(data);
          done++;
          if (data.status === 'LIVE' || data.status === '2FA') live++;
          else if (data.status === 'BAD') bad++;
          else errors++;

          outEl.innerHTML += renderOutlookResult({ ...data, email: email.trim(), _password: password.trim(), combo: combo.split(' | ')[0].trim() }, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateOutlookStats(data.status);

          if (data.status === 'LIVE') playAlert('live');
          else if (data.status === '2FA') playAlert('hold');

        } catch(e) {
          retries++;
          if (retries >= 3) { done++; errors++; }
          await new Promise(r => setTimeout(r, 1000));
        }
      }

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      const pct = ((done / total) * 100).toFixed(1);
      barEl.style.width = pct + '%';
      statsEl.innerHTML = `${done}/${total} · <span style="color:#10b981;">${live} hits</span> · <span style="color:#f43f5e;">${bad} bad</span> · <span style="color:#94a3b8;">${errors} err</span> · ${elapsed}s`;
    }
  }

  const workers = [];
  for (let i = 0; i < concurrency; i++) workers.push(worker());
  await Promise.all(workers);

  outlookBulkRunning = false;
  if (outlookBulkAbort) statsEl.innerHTML += ' · <span style="color:#f59e0b;">STOPPED</span>';
}

function stopOutlookBulk() { outlookBulkAbort = true; }

function exportOutlookHits() {
  const hits = outlookBulkResults.filter(r => r.status === 'LIVE' || r.status === '2FA');
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  const text = hits.map(h => `${h.email || 'N/A'}:${h._password || '***'} | Status: ${h.status} | Route: ${h.route || 'Direct'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `outlook_hits_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); showToast(`${hits.length} hits exported`);
}

function exportOutlookAll() {
  if (!outlookBulkResults.length) return showToast('Belum ada hasil');
  const text = outlookBulkResults.map(h => `${h.email || 'N/A'} | Status: ${h.status} | Reason: ${h.reason || 'N/A'} | Route: ${h.route || 'Direct'}`).join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `outlook_all_${new Date().toISOString().slice(0,10)}.txt`;
  a.click(); showToast(`${outlookBulkResults.length} results exported`);
}



// ── OpenAI / ChatGPT Cookie Checker ──────────────────────────────
let openAIBulkRunning = false;
let openAIBulkAbort = false;
let openAIBulkResults = [];
let openAIFileQueue = [];
const openAIStats = { live: 0, free: 0, dead: 0, error: 0 };

function openAIStatusColor(status) {
  const m = { LIVE: '#10b981', FREE: '#38bdf8', DEAD: '#f43f5e', ERROR: '#f59e0b' };
  return m[status] || 'var(--text-muted)';
}

function openAIStatusBg(status) {
  const m = { LIVE: 'rgba(16,185,129,0.1)', FREE: 'rgba(56,189,248,0.1)', DEAD: 'rgba(244,63,94,0.1)', ERROR: 'rgba(245,158,11,0.1)' };
  return m[status] || 'rgba(132,139,159,0.1)';
}

function renderOpenAIResult(data, mode) {
  mode = mode || 'single';
  var color = openAIStatusColor(data.status);
  var si = { LIVE: '\u2705', FREE: '\ud83c\udd93', DEAD: '\u274c', ERROR: '\u26a0\ufe0f' };
  var statusIcon = si[data.status] || '\u2753';
  var sl = { LIVE: 'Premium Account', FREE: 'Free Account', DEAD: 'Cookie Expired / Invalid', ERROR: 'Check Failed' };
  var statusLabel = sl[data.status] || data.status;

  if (data.status === 'LIVE' || data.status === 'FREE') {
    var cardClass = data.status === 'FREE' ? 'card-out hold' : 'card-out live';
    var divClass = mode === 'bulk' ? '' : cardClass;
    var divStyle = mode === 'bulk' ? 'padding:16px; border-left:4px solid ' + color + '; background:' + openAIStatusBg(data.status) + '; margin-bottom:10px; border-radius:var(--radius-lg);' : '';
    var emailSafe = escapeAttr(data.email || '');
    var planSafe = escapeAttr(data.plan || '');
    return '<div class="' + divClass + '" style="' + divStyle + '">' +
      '<div class="card-header-status" style="color:' + color + ';">' +
        '<span>' + statusIcon + '</span> <span>' + statusLabel + '</span>' +
        '<span style="margin-left:auto; font-size:11px; color:var(--text-muted); font-weight:500;">via ' + escapeHtml(data.route || 'Direct') + '</span>' +
      '</div>' +
      '<div class="grid-meta">' +
        '<div class="meta-box"><span>Email</span><strong>' + escapeHtml(data.email || 'N/A') + '</strong></div>' +
        '<div class="meta-box"><span>Plan</span><strong style="color:' + color + ';">' + escapeHtml(data.plan || 'N/A') + '</strong></div>' +
        '<div class="meta-box"><span>Subscription</span><strong>' + escapeHtml(data.subscription_plan || 'N/A') + '</strong></div>' +
        '<div class="meta-box"><span>Paid</span><strong>' + (data.is_paid ? '\u2705 Yes' : '\u274c No') + '</strong></div>' +
        '<div class="meta-box"><span>Route</span><strong>' + escapeHtml(data.route || 'Direct') + '</strong></div>' +
        '<div class="meta-box"><span>Status</span><strong style="color:' + color + ';">' + escapeHtml(data.status) + '</strong></div>' +
      '</div>' +
      '<div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">' +
        "<button class=\"btn-secondary\" onclick=\"copyText('" + emailSafe + "', 'Email disalin!')\">📧 Copy Email</button>" +
        "<button class=\"btn-secondary\" onclick=\"copyText('" + planSafe + "', 'Plan disalin!')\">📋 Copy Plan</button>" +
      '</div>' +
    '</div>';
  }

  var divClass2 = mode === 'bulk' ? '' : 'card-out dead';
  var divStyle2 = mode === 'bulk' ? 'padding:10px; border-left:3px solid ' + color + '; background:' + openAIStatusBg(data.status) + '; margin-bottom:6px; border-radius:var(--radius-sm);' : '';
  return '<div class="' + divClass2 + '" style="' + divStyle2 + '">' +
    '<div class="card-header-status" style="color:' + color + ';">' +
      '<span>' + statusIcon + '</span> <span>' + statusLabel + '</span>' +
    '</div>' +
    '<div style="color:var(--text-muted); font-size:12px;">' + escapeHtml(data.reason || data.email || 'Cookie tidak valid') + '</div>' +
  '</div>';
}

function updateOpenAIStats(status) {
  if (status === 'LIVE') openAIStats.live++;
  else if (status === 'FREE') openAIStats.free++;
  else if (status === 'DEAD') openAIStats.dead++;
  else openAIStats.error++;

  var dashboard = document.getElementById('openai-stats-dashboard');
  if (dashboard) dashboard.style.display = 'block';

  document.getElementById('openai-stat-live').textContent = openAIStats.live;
  document.getElementById('openai-stat-free').textContent = openAIStats.free;
  document.getElementById('openai-stat-dead').textContent = openAIStats.dead;
  document.getElementById('openai-stat-error').textContent = openAIStats.error;

  var total = openAIStats.live + openAIStats.free + openAIStats.dead + openAIStats.error;
  document.getElementById('openai-donut-total').textContent = total;

  var hitRate = total > 0 ? ((openAIStats.live + openAIStats.free) / total * 100) : 0;
  document.getElementById('openai-hit-rate').textContent = hitRate.toFixed(1) + '%';
  document.getElementById('openai-hit-rate-bar').style.width = hitRate + '%';

  drawDonutChart('openai-donut-chart', [
    { val: openAIStats.live,  color: '#10b981' },
    { val: openAIStats.free,  color: '#38bdf8' },
    { val: openAIStats.dead,  color: '#f43f5e' },
    { val: openAIStats.error, color: '#f59e0b' }
  ]);
  scheduleDashboardRefresh();
}

function resetOpenAIStats() {
  openAIStats.live = 0; openAIStats.free = 0; openAIStats.dead = 0; openAIStats.error = 0;
  ['openai-stat-live','openai-stat-free','openai-stat-dead','openai-stat-error'].forEach(function(id) { document.getElementById(id).textContent = '0'; });
  document.getElementById('openai-donut-total').textContent = '0';
  document.getElementById('openai-hit-rate').textContent = '0%';
  document.getElementById('openai-hit-rate-bar').style.width = '0%';
  drawDonutChart('openai-donut-chart', []);
  showToast('Stats direset');
}

async function runOpenAISingle() {
  var cookie = document.getElementById('openai-cookie-input').value.trim();
  if (!cookie) return showToast('Cookie wajib diisi');

  var btn = document.getElementById('openai-single-btn');
  var btnText = document.getElementById('openai-single-btn-text');
  var outEl = document.getElementById('openai-single-out');
  var useProxy = document.getElementById('openai-proxy-toggle') ? document.getElementById('openai-proxy-toggle').checked : false;

  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    var res = await fetch('/api/openai/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ cookie: cookie, use_proxy: useProxy })
    });
    var data = await res.json();
    outEl.innerHTML = renderOpenAIResult(data, 'single');
    outEl.style.display = 'block';
    updateOpenAIStats(data.status);
    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'FREE') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = '<div class="card-header-status" style="color:var(--dead);"><span style="font-size:20px;">\u274c</span> <span>Request Gagal</span></div><div style="color:var(--text-muted); font-size:12.5px;">' + e.message + '</div>';
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = 'CHECK COOKIE';
}

function handleOpenAIFiles(files) {
  if (!files || !files.length) return;
  var fileInfo = document.getElementById('openai-file-info');
  var textarea = document.getElementById('openai-bulk-input');
  openAIFileQueue = [];
  var processed = 0;
  var total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = '\u23f3 Memuat ' + total + ' file...';

  Array.from(files).forEach(function(file) {
    var reader = new FileReader();
    reader.onload = function(e) {
      var content = e.target.result.trim();
      if (!content) { processed++; return; }

      if (file.name.endsWith('.json')) {
        try {
          var arr = JSON.parse(content);
          if (Array.isArray(arr) && arr.length > 0) {
            if (arr[0] && arr[0].name) {
              openAIFileQueue.push(JSON.stringify(arr));
            } else {
              arr.forEach(function(item) {
                var val = typeof item === 'string' ? item.trim() : JSON.stringify(item);
                if (val) openAIFileQueue.push(val);
              });
            }
          }
        } catch(ex) {
          openAIFileQueue.push(content);
        }
      } else {
        // Use the smart splitter for text files (supports ========, metadata, Netscape)
        var smartCookies = _splitOpenAICookies(content);
        smartCookies.forEach(function(c) { openAIFileQueue.push(c); });
      }

      processed++;
      if (processed === total) {
        var totalCookies = openAIFileQueue.length;
        fileInfo.textContent = '\u2705 ' + total + ' file dimuat \u2192 ' + totalCookies + ' cookie ditemukan';
        fileInfo.style.color = 'var(--primary)';
        textarea.value = openAIFileQueue.join('\n\n');
        showToast(totalCookies + ' cookies dari ' + total + ' file siap dicheck');
      }
    };
    reader.onerror = function() {
      processed++;
      if (processed === total) {
        fileInfo.textContent = '\u26a0\ufe0f Beberapa file gagal dimuat';
        fileInfo.style.color = 'var(--dead)';
      }
    };
    reader.readAsText(file);
  });
}

/**
 * Smart cookie splitter: supports ========-separated blocks, double-newline blocks,
 * metadata lines (- Email:, - Name:, etc.), and raw token-per-line.
 * Returns an array of Netscape cookie blocks (one per account).
 */
function _splitOpenAICookies(raw) {
  if (!raw || !raw.trim()) return [];
  raw = raw.trim();
  var cookies = [];

  // 1. Try ========-separated format (metadata + Netscape lines mixed)
  if (raw.indexOf('========') >= 0) {
    var sections = raw.split(/={3,}/).filter(function(s) { return s.trim(); });
    sections.forEach(function(section) {
      var lines = section.split('\n');
      var cookieLines = [];
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        // Skip metadata lines (- Email:, - Name:, etc.) and empty lines
        if (!line || line.match(/^-\s*(Email|Name|Created|Plan|Renew|2FA|Cookies)\s*:/i)) continue;
        // Keep Netscape tab-separated lines (7+ fields)
        if (line.split('\t').length >= 7) {
          cookieLines.push(line);
        }
      }
      if (cookieLines.length > 0) {
        cookies.push(cookieLines.join('\n'));
      }
    });
    if (cookies.length > 0) return cookies;
  }

  // 2. Double-newline separated blocks
  var blocks = raw.split(/\n\s*\n/).filter(function(b) { return b.trim(); });
  if (blocks.length > 1) {
    // Check if blocks contain Netscape lines — if so, merge consecutive cookie blocks per account
    var hasNetscape = blocks.some(function(b) {
      return b.split('\n').some(function(l) { return l.trim().split('\t').length >= 7; });
    });
    if (hasNetscape) {
      // Merge blocks that are all Netscape lines (belong to same account)
      var currentGroup = [];
      blocks.forEach(function(block) {
        var bLines = block.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
        var allNetscape = bLines.every(function(l) { return l.split('\t').length >= 7 || l.match(/^-\s*(Email|Name|Created|Plan|Renew|2FA|Cookies)\s*:/i) || !l; });
        var cookieOnly = bLines.filter(function(l) { return l.split('\t').length >= 7; });
        if (cookieOnly.length > 0) {
          currentGroup = currentGroup.concat(cookieOnly);
        } else if (currentGroup.length > 0 && bLines.some(function(l) { return l.match(/^-\s*Email\s*:/i); })) {
          // New account starts — flush previous
          cookies.push(currentGroup.join('\n'));
          currentGroup = [];
        }
      });
      if (currentGroup.length > 0) cookies.push(currentGroup.join('\n'));
      if (cookies.length > 0) return cookies;
    }
    return blocks.map(function(b) { return b.trim(); });
  }

  // 3. Single block — each line is a raw token
  return raw.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
}

async function runOpenAIBulk() {
  var raw = document.getElementById('openai-bulk-input').value.trim();
  if (!raw && openAIFileQueue.length === 0) return showToast('Paste cookies atau upload file dulu');
  if (openAIBulkRunning) return;

  var cookies = [];
  if (openAIFileQueue.length > 0) {
    cookies = openAIFileQueue.slice();
  } else {
    cookies = _splitOpenAICookies(raw);
  }
  if (!cookies.length) return showToast('Tidak ada cookie valid');

  openAIBulkRunning = true;
  openAIBulkAbort = false;
  openAIBulkResults = [];

  var outEl = document.getElementById('openai-bulk-out');
  var statsEl = document.getElementById('openai-bulk-stats');
  var progressEl = document.getElementById('openai-bulk-progress');
  var barEl = document.getElementById('openai-progress-bar');
  var useProxy = document.getElementById('openai-proxy-toggle') ? document.getElementById('openai-proxy-toggle').checked : false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  var done = 0, live = 0, dead = 0, errors = 0;
  var total = cookies.length;
  var startTime = Date.now();
  var currentIndex = 0;
  var concurrency = 2;

  async function worker() {
    while (currentIndex < cookies.length && !openAIBulkAbort) {
      var idx = currentIndex++;
      var cookie = cookies[idx];
      var retries = 0;
      var success = false;
      while (retries < 3 && !success) {
        try {
          var res = await fetch('/api/openai/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ cookie: cookie, use_proxy: useProxy })
          });
          if (res.status === 429) {
            openAIBulkAbort = true;
            showToast('Rate limit exceeded \u2014 stopping bulk');
            break;
          }
          var data = await res.json();
          success = true;
          openAIBulkResults.push(data);
          done++;
          if (data.status === 'LIVE' || data.status === 'FREE') live++;
          else if (data.status === 'DEAD') dead++;
          else errors++;
          outEl.innerHTML += renderOpenAIResult(data, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updateOpenAIStats(data.status);
          if (data.status === 'LIVE') playAlert('live');
          else if (data.status === 'FREE') playAlert('hold');
        } catch(e) {
          retries++;
          if (retries >= 3) { done++; errors++; }
          await new Promise(function(r) { setTimeout(r, 1000); });
        }
      }
      var elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      var pct = ((done / total) * 100).toFixed(1);
      barEl.style.width = pct + '%';
      statsEl.innerHTML = done + '/' + total + ' \u00b7 <span style="color:#10b981;">' + live + ' hits</span> \u00b7 <span style="color:#f43f5e;">' + dead + ' dead</span> \u00b7 <span style="color:#94a3b8;">' + errors + ' err</span> \u00b7 ' + elapsed + 's';
    }
  }

  var workers = [];
  for (var i = 0; i < concurrency; i++) workers.push(worker());
  await Promise.all(workers);
  openAIBulkRunning = false;
  if (openAIBulkAbort) statsEl.innerHTML += ' \u00b7 <span style="color:#f59e0b;">STOPPED</span>';
}

function stopOpenAIBulk() { openAIBulkAbort = true; }

function exportOpenAIHits() {
  var hits = openAIBulkResults.filter(function(r) { return r.status === 'LIVE' || r.status === 'FREE'; });
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  var text = hits.map(function(h) { return (h.email || 'N/A') + ' | Plan: ' + (h.plan || 'N/A') + ' | Status: ' + h.status + ' | Route: ' + (h.route || 'Direct'); }).join('\n');
  var blob = new Blob([text], { type: 'text/plain' });
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'openai_hits_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click(); showToast(hits.length + ' hits exported');
}

function exportOpenAIAll() {
  if (!openAIBulkResults.length) return showToast('Belum ada hasil');
  var text = openAIBulkResults.map(function(h) { return (h.email || 'N/A') + ' | Plan: ' + (h.plan || 'N/A') + ' | Status: ' + h.status + ' | Reason: ' + (h.reason || 'N/A') + ' | Route: ' + (h.route || 'Direct'); }).join('\n');
  var blob = new Blob([text], { type: 'text/plain' });
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'openai_all_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click(); showToast(openAIBulkResults.length + ' results exported');
}

// ── Prime Video Checker JS ──────────────────────────────────────────
let pvBulkRunning = false;
let pvBulkAbort = false;
let pvBulkResults = [];
let pvFileQueue = [];
const pvStats = { live: 0, free: 0, dead: 0, error: 0 };

function pvStatusColor(status) {
  const m = { LIVE: '#10b981', FREE: '#38bdf8', DEAD: '#f43f5e', ERROR: '#f59e0b' };
  return m[status] || 'var(--text-muted)';
}

function pvStatusBg(status) {
  const m = { LIVE: 'rgba(16,185,129,0.1)', FREE: 'rgba(56,189,248,0.1)', DEAD: 'rgba(244,63,94,0.1)', ERROR: 'rgba(245,158,11,0.1)' };
  return m[status] || 'rgba(132,139,159,0.1)';
}

function renderPVResult(data, mode) {
  mode = mode || 'single';
  var color = pvStatusColor(data.status);
  var si = { LIVE: '\u2705', FREE: '\ud83c\udd93', DEAD: '\u274c', ERROR: '\u26a0\ufe0f' };
  var statusIcon = si[data.status] || '\u2753';
  var sl = { LIVE: 'Prime Account', FREE: 'Free Account', DEAD: 'Cookie Expired / Invalid', ERROR: 'Check Failed' };
  var statusLabel = sl[data.status] || data.status;

  if (data.status === 'LIVE' || data.status === 'FREE') {
    var cardClass = data.status === 'FREE' ? 'card-out hold' : 'card-out live';
    var divClass = mode === 'bulk' ? '' : cardClass;
    var divStyle = mode === 'bulk' ? 'padding:16px; border-left:4px solid ' + color + '; background:' + pvStatusBg(data.status) + '; margin-bottom:10px; border-radius:var(--radius-lg);' : '';
    return '<div class="' + divClass + '" style="' + divStyle + '">' +
      '<div class="card-header-status" style="color:' + color + ';">' +
      '<span style="font-size:20px;">' + statusIcon + '</span> <span>' + statusLabel + '</span></div>' +
      '<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; font-size:12.5px;">' +
      '<div class="meta-box"><div class="label">Plan</div><div class="val" style="color:' + color + ';">' + escapeHtml(data.plan || 'Unknown') + '</div></div>' +
      '<div class="meta-box"><div class="label">Profile</div><div class="val">' + escapeHtml(data.profile || 'N/A') + '</div></div>' +
      '<div class="meta-box"><div class="label">Region</div><div class="val">' + escapeHtml(data.region || 'N/A') + '</div></div>' +
      '<div class="meta-box"><div class="label">Customer ID</div><div class="val" style="font-family:monospace; font-size:10px;">' + escapeHtml(data.customer_id || 'N/A') + '</div></div>' +
      '</div>' +
      '<div style="margin-top:10px; font-size:11px; color:var(--text-muted);">' +
      '<span>\ud83c\udf10 Route: ' + escapeHtml(data.route || 'Direct') + '</span>' +
      (data.reason ? ' · <span>' + escapeHtml(data.reason) + '</span>' : '') +
      '</div></div>';
  } else {
    var deadClass = mode === 'bulk' ? '' : 'card-out dead';
    var deadStyle = mode === 'bulk' ? 'padding:14px; border-left:4px solid ' + color + '; background:' + pvStatusBg(data.status) + '; margin-bottom:10px; border-radius:var(--radius-lg);' : '';
    return '<div class="' + deadClass + '" style="' + deadStyle + '">' +
      '<div class="card-header-status" style="color:' + color + ';">' +
      '<span style="font-size:20px;">' + statusIcon + '</span> <span>' + statusLabel + '</span></div>' +
      '<div style="color:var(--text-muted); font-size:12.5px; margin-top:8px;">' + escapeHtml(data.reason || 'Unknown error') + '</div>' +
      (data.route ? '<div style="font-size:11px; color:var(--text-dim); margin-top:6px;">\ud83c\udf10 Route: ' + escapeHtml(data.route) + '</div>' : '') +
      '</div>';
  }
}

function updatePVStats(status) {
  if (status === 'LIVE') pvStats.live++;
  else if (status === 'FREE') pvStats.free++;
  else if (status === 'DEAD') pvStats.dead++;
  else pvStats.error++;

  var total = pvStats.live + pvStats.free + pvStats.dead + pvStats.error;
  document.getElementById('pv-stat-live').textContent = pvStats.live;
  document.getElementById('pv-stat-free').textContent = pvStats.free;
  document.getElementById('pv-stat-dead').textContent = pvStats.dead;
  document.getElementById('pv-stat-error').textContent = pvStats.error;
  document.getElementById('pv-donut-total').textContent = total;

  var hitRate = total > 0 ? (((pvStats.live + pvStats.free) / total) * 100).toFixed(1) : '0';
  document.getElementById('pv-hit-rate').textContent = hitRate + '%';
  document.getElementById('pv-hit-rate-bar').style.width = hitRate + '%';

  document.getElementById('pv-stats-dashboard').style.display = total > 0 ? 'block' : 'none';
  drawDonutChart('pv-donut-chart', [
    { val: pvStats.live,  color: '#10b981' },
    { val: pvStats.free,  color: '#38bdf8' },
    { val: pvStats.dead,  color: '#f43f5e' },
    { val: pvStats.error, color: '#f59e0b' }
  ]);
  scheduleDashboardRefresh();
}

function resetPVStats() {
  pvStats.live = 0; pvStats.free = 0; pvStats.dead = 0; pvStats.error = 0;
  ['pv-stat-live','pv-stat-free','pv-stat-dead','pv-stat-error'].forEach(function(id) { document.getElementById(id).textContent = '0'; });
  document.getElementById('pv-donut-total').textContent = '0';
  document.getElementById('pv-hit-rate').textContent = '0%';
  document.getElementById('pv-hit-rate-bar').style.width = '0%';
  drawDonutChart('pv-donut-chart', []);
  showToast('Stats direset');
}

async function runPVSingle() {
  var cookie = document.getElementById('pv-cookie-input').value.trim();
  if (!cookie) return showToast('Cookie wajib diisi');

  var btn = document.getElementById('pv-single-btn');
  var btnText = document.getElementById('pv-single-btn-text');
  var outEl = document.getElementById('pv-single-out');
  var useProxy = document.getElementById('pv-proxy-toggle') ? document.getElementById('pv-proxy-toggle').checked : false;

  btn.disabled = true;
  btnText.textContent = 'Checking...';
  outEl.style.display = 'none';
  outEl.className = 'card-out';
  outEl.innerHTML = '';

  try {
    var res = await fetch('/api/primevideo/check', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ cookie: cookie, use_proxy: useProxy })
    });
    var data = await res.json();
    outEl.innerHTML = renderPVResult(data, 'single');
    outEl.style.display = 'block';
    updatePVStats(data.status);
    if (data.status === 'LIVE') playAlert('live');
    else if (data.status === 'FREE') playAlert('hold');
  } catch(e) {
    outEl.className = 'card-out dead';
    outEl.innerHTML = '<div class="card-header-status" style="color:var(--dead);"><span style="font-size:20px;">\u274c</span> <span>Request Gagal</span></div><div style="color:var(--text-muted); font-size:12.5px;">' + e.message + '</div>';
    outEl.style.display = 'block';
  }
  btn.disabled = false;
  btnText.textContent = 'CHECK COOKIE';
}

function handlePVFiles(files) {
  if (!files || !files.length) return;
  var fileInfo = document.getElementById('pv-file-info');
  var textarea = document.getElementById('pv-bulk-input');
  pvFileQueue = [];
  var processed = 0;
  var total = files.length;
  fileInfo.style.display = 'block';
  fileInfo.textContent = '\u23f3 Memuat ' + total + ' file...';

  Array.from(files).forEach(function(file) {
    var reader = new FileReader();
    reader.onload = function(e) {
      var content = e.target.result.trim();
      if (!content) { processed++; return; }

      if (file.name.endsWith('.json')) {
        try {
          var arr = JSON.parse(content);
          if (Array.isArray(arr) && arr.length > 0) {
            if (arr[0] && arr[0].name) {
              pvFileQueue.push(JSON.stringify(arr));
            } else {
              arr.forEach(function(item) {
                var val = typeof item === 'string' ? item.trim() : JSON.stringify(item);
                if (val) pvFileQueue.push(val);
              });
            }
          }
        } catch(ex) {
          pvFileQueue.push(content);
        }
      } else {
        // Check for '$' delimiter first (common PrimeVideo hit format)
        if (content.indexOf('$') >= 0 && content.split('$').length > 2) {
          var dollarBlocks = content.split('$').map(function(b) { return b.trim(); }).filter(function(b) { return b; });
          dollarBlocks.forEach(function(block) { pvFileQueue.push(block); });
        } else {
        var allLines = content.split('\n');
        var hasNetscape = allLines.some(function(l) { return l.trim().split('\t').length >= 7; });
        if (hasNetscape) {
          var blocks = [];
          var currentBlock = [];
          for (var i = 0; i < allLines.length; i++) {
            var line = allLines[i].trim();
            if (line.toLowerCase().startsWith('# netscape http cookie file') && currentBlock.length > 0) {
              var cookieLines = currentBlock.filter(function(l) { return l && !l.startsWith('#') && l.split('\t').length >= 7; });
              if (cookieLines.length > 0) blocks.push(cookieLines.join('\n'));
              currentBlock = [];
            }
            currentBlock.push(line);
          }
          if (currentBlock.length > 0) {
            var lastCookieLines = currentBlock.filter(function(l) { return l && !l.startsWith('#') && l.split('\t').length >= 7; });
            if (lastCookieLines.length > 0) blocks.push(lastCookieLines.join('\n'));
          }
          if (blocks.length === 0) {
            var fallbackLines = allLines.map(function(l) { return l.trim(); }).filter(function(l) { return l && !l.startsWith('#') && l.split('\t').length >= 7; });
            if (fallbackLines.length > 0) blocks.push(fallbackLines.join('\n'));
          }
          blocks.forEach(function(b) { pvFileQueue.push(b); });
        } else {
          var hasKeyVal = allLines.some(function(l) { return l.indexOf('session-token') >= 0; });
          if (hasKeyVal) {
            pvFileQueue.push(content);
          } else {
            var cleanLines = allLines.map(function(l) { return l.trim(); }).filter(function(l) { return l && !l.startsWith('#'); });
            cleanLines.forEach(function(l) { pvFileQueue.push(l); });
          }
        }
        }
      }

      processed++;
      if (processed === total) {
        var totalCookies = pvFileQueue.length;
        fileInfo.textContent = '\u2705 ' + total + ' file dimuat \u2192 ' + totalCookies + ' cookie ditemukan';
        fileInfo.style.color = 'var(--primary)';
        textarea.value = pvFileQueue.join('\n\n');
        showToast(totalCookies + ' cookies dari ' + total + ' file siap dicheck');
      }
    };
    reader.onerror = function() {
      processed++;
      if (processed === total) {
        fileInfo.textContent = '\u26a0\ufe0f Beberapa file gagal dimuat';
        fileInfo.style.color = 'var(--dead)';
      }
    };
    reader.readAsText(file);
  });
}

async function runPVBulk() {
  var raw = document.getElementById('pv-bulk-input').value.trim();
  if (!raw && pvFileQueue.length === 0) return showToast('Paste cookies atau upload file dulu');
  if (pvBulkRunning) return;

  var cookies = [];
  if (pvFileQueue.length > 0) {
    cookies = pvFileQueue.slice();
  } else {
    // Support '$' delimiter between accounts (common PrimeVideo hit format)
    if (raw.indexOf('$') >= 0) {
      cookies = raw.split('$').map(function(b) { return b.trim(); }).filter(function(b) { return b; });
    } else {
      var blocks = raw.split(/\n\s*\n/).filter(function(b) { return b.trim(); });
      if (blocks.length > 1) {
        cookies = blocks.map(function(b) { return b.trim(); });
      } else {
        cookies = raw.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
      }
    }
  }
  if (!cookies.length) return showToast('Tidak ada cookie valid');

  pvBulkRunning = true;
  pvBulkAbort = false;
  pvBulkResults = [];

  var outEl = document.getElementById('pv-bulk-out');
  var statsEl = document.getElementById('pv-bulk-stats');
  var progressEl = document.getElementById('pv-bulk-progress');
  var barEl = document.getElementById('pv-progress-bar');
  var useProxy = document.getElementById('pv-proxy-toggle') ? document.getElementById('pv-proxy-toggle').checked : false;

  outEl.innerHTML = '';
  progressEl.style.display = 'block';
  barEl.style.width = '0%';

  var done = 0, live = 0, dead = 0, errors = 0;
  var total = cookies.length;
  var startTime = Date.now();
  var currentIndex = 0;
  var concurrency = 2;

  async function worker() {
    while (currentIndex < cookies.length && !pvBulkAbort) {
      var idx = currentIndex++;
      var cookie = cookies[idx];
      var retries = 0;
      var success = false;
      while (retries < 3 && !success) {
        try {
          var res = await fetch('/api/primevideo/check', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ cookie: cookie, use_proxy: useProxy })
          });
          if (res.status === 429) {
            pvBulkAbort = true;
            showToast('Rate limit exceeded \u2014 stopping bulk');
            break;
          }
          var data = await res.json();
          success = true;
          pvBulkResults.push(data);
          done++;
          if (data.status === 'LIVE' || data.status === 'FREE') live++;
          else if (data.status === 'DEAD') dead++;
          else errors++;
          outEl.innerHTML += renderPVResult(data, 'bulk');
          outEl.scrollTop = outEl.scrollHeight;
          updatePVStats(data.status);
          if (data.status === 'LIVE') playAlert('live');
          else if (data.status === 'FREE') playAlert('hold');
        } catch(e) {
          retries++;
          if (retries >= 3) { done++; errors++; }
          await new Promise(function(r) { setTimeout(r, 1000); });
        }
      }
      var elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
      var pct = ((done / total) * 100).toFixed(1);
      barEl.style.width = pct + '%';
      statsEl.innerHTML = done + '/' + total + ' \u00b7 <span style="color:#10b981;">' + live + ' hits</span> \u00b7 <span style="color:#f43f5e;">' + dead + ' dead</span> \u00b7 <span style="color:#94a3b8;">' + errors + ' err</span> \u00b7 ' + elapsed + 's';
    }
  }

  var workers = [];
  for (var i = 0; i < concurrency; i++) workers.push(worker());
  await Promise.all(workers);
  pvBulkRunning = false;
  if (pvBulkAbort) statsEl.innerHTML += ' \u00b7 <span style="color:#f59e0b;">STOPPED</span>';
}

function stopPVBulk() { pvBulkAbort = true; }

function exportPVHits() {
  var hits = pvBulkResults.filter(function(r) { return r.status === 'LIVE' || r.status === 'FREE'; });
  if (!hits.length) return showToast('Belum ada hits untuk diexport');
  var text = hits.map(function(h) { return 'Profile: ' + (h.profile || 'N/A') + ' | Plan: ' + (h.plan || 'N/A') + ' | Region: ' + (h.region || 'N/A') + ' | Status: ' + h.status + ' | Route: ' + (h.route || 'Direct'); }).join('\n');
  var blob = new Blob([text], { type: 'text/plain' });
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'primevideo_hits_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click(); showToast(hits.length + ' hits exported');
}

function exportPVAll() {
  if (!pvBulkResults.length) return showToast('Belum ada hasil');
  var text = pvBulkResults.map(function(h) { return 'Profile: ' + (h.profile || 'N/A') + ' | Plan: ' + (h.plan || 'N/A') + ' | Region: ' + (h.region || 'N/A') + ' | Status: ' + h.status + ' | Reason: ' + (h.reason || 'N/A') + ' | Route: ' + (h.route || 'Direct'); }).join('\n');
  var blob = new Blob([text], { type: 'text/plain' });
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'primevideo_all_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click(); showToast(pvBulkResults.length + ' results exported');
}

// ── Proxy Manager Upgrade ──────────────────────────────────────────
let pmState = {
  page: 1,
  limit: 50,
  status: 'ALL',
  search: '',
  totalPages: 1,
  totalItems: 0,
  healthyCount: 0,
  deadCount: 0,
  unverifiedCount: 0,
  activeCount: 0,
  avgLatency: 0,
  testing: false,
  testMode: 'untested',
  batchLimit: 100,
  items: [],
  selectedKeys: new Set(),
  pollTimer: null,
  debounceTimer: null
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function pmRefresh(keepPage = false) {
  if (!keepPage) pmState.page = 1;
  const tbody = document.getElementById('pm-tbody');
  if (!tbody) return;

  if (!pmState.items.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-muted);">⏳ Memuat proxy data...</td></tr>';
  }

  try {
    const q = new URLSearchParams({
      page: String(pmState.page),
      limit: String(pmState.limit),
      status: pmState.status,
      search: pmState.search
    });
    const res = await fetch(`/api/proxies/detail?${q.toString()}`, { headers: getAuthHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();

    pmState.totalItems = d.total || 0;
    pmState.healthyCount = d.healthy_count || 0;
    pmState.deadCount = d.dead_count || 0;
    pmState.unverifiedCount = d.unverified_count || 0;
    pmState.activeCount = d.active_count || (d.healthy_count > 0 ? d.healthy_count : d.total);
    pmState.avgLatency = d.avg_latency || 0;
    pmState.page = d.page || 1;
    pmState.totalPages = d.total_pages || 1;
    pmState.items = d.list || [];
    pmState.testing = d.testing || false;

    // Update Top Stat Numbers
    const elTotal = document.getElementById('pm-total');
    if (elTotal) elTotal.textContent = Number(d.total).toLocaleString('id-ID');

    const elHealthy = document.getElementById('pm-healthy');
    if (elHealthy) {
      const pct = d.total > 0 ? Math.round((d.healthy_count / d.total) * 100) : 0;
      elHealthy.innerHTML = `${Number(d.healthy_count).toLocaleString('id-ID')} <span style="font-size:12px; font-weight:normal; opacity:0.8;">(${pct}%)</span>`;
    }

    const elMetaHealthy = document.getElementById('pm-meta-healthy');
    if (elMetaHealthy) {
      const latText = d.avg_latency > 0 ? `${d.avg_latency}ms` : 'Belum diuji';
      const pct = d.total > 0 ? Math.round((d.healthy_count / d.total) * 100) : 0;
      elMetaHealthy.textContent = `${pct}% pool terverifikasi • Rata-rata: ${latText}`;
    }

    const elDead = document.getElementById('pm-dead');
    if (elDead) elDead.textContent = Number(d.dead_count).toLocaleString('id-ID');

    const elUnverified = document.getElementById('pm-unverified');
    if (elUnverified) elUnverified.textContent = Number(d.unverified_count).toLocaleString('id-ID');

    // Update Filter Pills Badges
    const bAll = document.getElementById('pm-badge-all');
    if (bAll) bAll.textContent = Number(d.total).toLocaleString('id-ID');
    const bLive = document.getElementById('pm-badge-live');
    if (bLive) bLive.textContent = Number(d.healthy_count).toLocaleString('id-ID');
    const bDead = document.getElementById('pm-badge-dead');
    if (bDead) bDead.textContent = Number(d.dead_count).toLocaleString('id-ID');
    const bUnverified = document.getElementById('pm-badge-unverified');
    if (bUnverified) bUnverified.textContent = Number(d.unverified_count).toLocaleString('id-ID');

    // Sync header ribbon stats
    if (typeof fetchStats === 'function') {
      fetchStats();
    }

    // Update Testing Progress UI
    pmUpdateTestingUI(d.testing, d.test_progress);

    // Render Table & Pagination
    pmRenderTable(d.list);
    pmRenderPagination(d.page, d.total_pages, d.filtered_total);

    // Polling if test running
    if (d.testing) {
      if (!pmState.pollTimer) {
        pmState.pollTimer = setTimeout(() => {
          pmState.pollTimer = null;
          pmRefresh(true);
        }, 1500);
      }
    } else {
      if (pmState.pollTimer) {
        clearTimeout(pmState.pollTimer);
        pmState.pollTimer = null;
      }
    }
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--dead);">Gagal memuat proxy: ${escapeHtml(e.message)}</td></tr>`;
    showToast('Gagal memuat proxy: ' + e.message);
  }
}

function pmUpdateTestingUI(testing, p) {
  const box = document.getElementById('pm-test-progress-box');
  const btnStart = document.getElementById('pm-btn-start-test');
  const btnStop = document.getElementById('pm-btn-stop-test');
  const bar = document.getElementById('pm-progress-bar-inner');
  const pctEl = document.getElementById('pm-progress-pct');
  const titleEl = document.getElementById('pm-progress-title');

  const teleTested = document.getElementById('pm-tele-tested');
  const teleHealthy = document.getElementById('pm-tele-healthy');
  const teleDead = document.getElementById('pm-tele-dead');
  const teleSpeed = document.getElementById('pm-tele-speed');
  const teleEta = document.getElementById('pm-tele-eta');

  if (testing && p) {
    if (box) box.style.display = 'block';
    if (btnStart) btnStart.style.display = 'none';
    if (btnStop) btnStop.style.display = 'inline-flex';

    const total = p.total || 1;
    const tested = p.tested || 0;
    const pct = Math.min(100, Math.round((tested / total) * 100));

    if (bar) bar.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
    if (titleEl) titleEl.textContent = `Batch Testing Berjalan (80 Workers Concurrent)...`;

    if (teleTested) teleTested.textContent = `${Number(tested).toLocaleString('id-ID')} / ${Number(total).toLocaleString('id-ID')}`;
    if (teleHealthy) teleHealthy.textContent = Number(p.healthy || 0).toLocaleString('id-ID');
    if (teleDead) teleDead.textContent = Number(p.dead || 0).toLocaleString('id-ID');
    if (teleSpeed) teleSpeed.textContent = `${p.speed || 0} req/s`;
    if (teleEta) teleEta.textContent = `~${p.eta_seconds || 0}s`;
  } else {
    if (btnStart) btnStart.style.display = 'inline-flex';
    if (btnStop) btnStop.style.display = 'none';
    if (box && (!p || p.tested === 0 || p.tested >= (p.total || 0))) {
      if (!p || p.total === 0) {
        box.style.display = 'none';
      }
    }
  }
}

function pmSetTestMode(mode) {
  pmState.testMode = mode;
  ['untested', 'all', 'dead'].forEach(m => {
    const el = document.getElementById(`pm-mode-${m}`);
    if (el) {
      if (m === mode) el.classList.add('active');
      else el.classList.remove('active');
    }
  });
}

function pmSetBatchLimit(val) {
  pmState.batchLimit = val;
  const limits = [50, 100, 250, 500, 1000, 'all'];
  limits.forEach(lim => {
    const el = document.getElementById(`pm-limit-${lim}`);
    if (el) {
      if (lim === val) el.classList.add('active');
      else el.classList.remove('active');
    }
  });
  const customInp = document.getElementById('pm-custom-limit');
  if (customInp) customInp.value = '';
}

function pmOnCustomLimitInput(val) {
  const n = parseInt(val, 10);
  if (!isNaN(n) && n > 0) {
    pmState.batchLimit = n;
    [50, 100, 250, 500, 1000, 'all'].forEach(lim => {
      const el = document.getElementById(`pm-limit-${lim}`);
      if (el) el.classList.remove('active');
    });
  }
}

async function pmStartBatchTest() {
  const limit = pmState.batchLimit;
  const mode = pmState.testMode;
  try {
    showToast(`Memulai batch test concurrent (80 workers)...`);
    const res = await fetch('/api/proxies/test', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ limit, mode })
    });
    const d = await res.json();
    if (d.ok) {
      showToast(d.message || 'Batch test proxy dimulai!');
      pmRefresh(true);
    } else {
      showToast('Gagal memulai: ' + (d.error || 'Server error'));
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

async function pmStopBatchTest() {
  try {
    const res = await fetch('/api/proxies/test/stop', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: '{}'
    });
    const d = await res.json();
    if (d.ok) {
      showToast('Batch test dihentikan oleh user');
    } else {
      showToast(d.message || 'Tidak ada test berjalan');
    }
    pmRefresh(true);
  } catch(e) {
    showToast('Error stop: ' + e.message);
  }
}

function pmRenderTable(items) {
  const tbody = document.getElementById('pm-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!items || !items.length) {
    if (pmState.totalItems === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; padding:48px 20px;">
            <div style="font-size:42px; margin-bottom:12px;">🌐</div>
            <div style="font-size:16px; font-weight:700; color:var(--text-main); margin-bottom:6px;">Proxy Pool Masih Kosong</div>
            <div style="font-size:12px; color:var(--text-muted); max-width:460px; margin:0 auto 16px; line-height:1.6;">
              Tidak ada proxy yang tersimpan di sistem saat ini. Anda dapat mengimpor file list proxy (.txt) atau memasukkannya secara manual.
            </div>
            <div style="display:flex; justify-content:center; gap:8px; flex-wrap:wrap;">
              <button class="btn btn-sm" onclick="pmToggleAddBox(true)" style="background:linear-gradient(135deg, #2563eb, #1d4ed8); color:#fff; font-weight:600; padding:6px 14px; border:0; border-radius:6px;">➕ Tambah Proxy Baru</button>
              <button class="btn btn-sm" onclick="document.getElementById('pm-file-input').click()" style="background:#1e3a8a; border:1px solid #3b82f6; color:#93c5fd; font-weight:600; padding:6px 14px; border-radius:6px;">📁 Upload File .txt</button>
            </div>
          </td>
        </tr>
      `;
    } else {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; padding:36px 20px;">
            <div style="font-size:32px; margin-bottom:8px;">🔍</div>
            <div style="font-size:14px; font-weight:600; color:var(--text-main); margin-bottom:4px;">Tidak Ada Proxy yang Cocok</div>
            <div style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">Hasil filter status atau kata kunci pencarian tidak menemukan kecocokan.</div>
            <button class="btn btn-sm" onclick="pmResetFilters()" style="background:var(--bg-subtle); padding:5px 12px; border:1px solid var(--border); border-radius:6px;">↺ Reset Filter &amp; Pencarian</button>
          </td>
        </tr>
      `;
    }
    pmUpdateSelectedCount();
    return;
  }

  const df = document.createDocumentFragment();
  items.forEach(p => {
    const raw = p.raw || p.proxy || '';
    const line = p.line || raw;
    const isAuth = raw.includes('@') || line.includes('@') || (p.proxy && p.proxy.includes('@'));
    const scheme = (p.proxy && p.proxy.includes('://')) ? p.proxy.split('://')[0].toUpperCase() : 'HTTP';

    let statusBadge = '<span class="pm-badge-ready">⏳ READY</span>';
    if (p.status === 'OK') {
      statusBadge = '<span class="pm-badge-live"><span class="pulse-dot"></span> LIVE</span>';
    } else if (p.status === 'FAIL') {
      statusBadge = '<span class="pm-badge-dead">✕ DEAD</span>';
    }

    let latBadge = '<span style="color:var(--text-muted)">—</span>';
    if (p.latency && p.latency > 0) {
      let latColor = '#22c55e';
      if (p.latency > 800) latColor = '#ef4444';
      else if (p.latency > 300) latColor = '#eab308';
      latBadge = `<span style="color:${latColor}; font-weight:700; font-size:11.5px; font-family:\'JetBrains Mono\', monospace;">${p.latency}ms</span>`;
    }

    const isChecked = pmState.selectedKeys.has(line);
    const tr = document.createElement('tr');
    tr.id = `pm-row-${p.id || raw.replace(/[^a-zA-Z0-9]/g, '_')}`;
    tr.innerHTML = `
      <td style="width:36px; text-align:center;">
        <input type="checkbox" class="pm-cb" data-key="${encodeURIComponent(line)}" data-raw="${encodeURIComponent(raw)}" ${isChecked ? 'checked' : ''} onchange="pmOnCheckboxChange(this)">
      </td>
      <td>
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-family:\'JetBrains Mono\', monospace; font-size:12px; color:var(--text-main);">${escapeHtml(raw)}</span>
          <button title="Salin Proxy" onclick="pmCopyText('${escapeHtml(raw)}')" style="background:transparent; border:0; color:var(--text-muted); cursor:pointer; padding:2px 4px; font-size:12px;">📋</button>
        </div>
      </td>
      <td style="font-size:11px;">
        <span class="pm-badge-proto">${scheme}</span>
        ${isAuth ? '<span class="pm-badge-auth">AUTH</span>' : ''}
      </td>
      <td>${statusBadge}</td>
      <td>${latBadge}</td>
      <td style="text-align:right;">
        <div style="display:inline-flex; gap:6px;">
          <button class="btn btn-sm" onclick="pmTestSingle('${escapeHtml(line)}', this)" title="Test Proxy Ini" style="padding:4px 8px; font-size:11px; background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3); border-radius:4px;">⚡ Test</button>
          <button class="btn btn-sm" onclick="pmDeleteSingle('${escapeHtml(line)}')" title="Hapus Proxy Ini" style="padding:4px 8px; font-size:11px; background:rgba(239,68,68,0.15); color:#fca5a5; border:1px solid rgba(239,68,68,0.3); border-radius:4px;">🗑</button>
        </div>
      </td>
    `;
    df.appendChild(tr);
  });
  tbody.appendChild(df);
  pmUpdateSelectedCount();
}

function pmRenderPagination(page, totalPages, filteredTotal) {
  const wrap = document.getElementById('pm-pagination');
  if (!wrap) return;
  wrap.innerHTML = `
    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; width:100%; font-size:12px; color:var(--text-muted);">
      <div>
        Total: <b>${Number(filteredTotal).toLocaleString('id-ID')}</b> proxy (Hal <b>${page}</b> dari <b>${totalPages}</b>)
      </div>
      <div style="display:flex; gap:4px; align-items:center;">
        <button class="btn btn-sm" onclick="pmGoPage(1)" ${page <= 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>« First</button>
        <button class="btn btn-sm" onclick="pmGoPage(${page - 1})" ${page <= 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>‹ Prev</button>
        <span style="padding:0 8px; font-weight:600; color:var(--text-main); font-size:11px;">${page} / ${totalPages}</span>
        <button class="btn btn-sm" onclick="pmGoPage(${page + 1})" ${page >= totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>Next ›</button>
        <button class="btn btn-sm" onclick="pmGoPage(${totalPages})" ${page >= totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : ''}>Last »</button>
      </div>
    </div>
  `;
}

function pmGoPage(page) {
  if (page < 1 || page > pmState.totalPages) return;
  pmState.page = page;
  pmRefresh(true);
}

function pmChangeLimit(limit) {
  pmState.limit = parseInt(limit, 10) || 50;
  pmState.page = 1;
  pmRefresh(true);
}

function pmSetStatusFilter(status) {
  pmState.status = status;
  pmState.page = 1;
  document.querySelectorAll('#pm-filter-buttons .pm-filter-btn').forEach(btn => {
    if (btn.dataset.status === status) {
      btn.style.background = 'var(--accent)';
      btn.style.color = '#fff';
    } else {
      btn.style.background = 'var(--bg-subtle)';
      btn.style.color = 'var(--text-muted)';
    }
  });
  pmRefresh(true);
}

function pmSearch(val) {
  clearTimeout(pmState.debounceTimer);
  pmState.debounceTimer = setTimeout(() => {
    pmState.search = val.trim();
    pmState.page = 1;
    pmRefresh(true);
  }, 300);
}

function pmToggleSelectAll(masterCb) {
  const checked = masterCb.checked;
  document.querySelectorAll('.pm-cb').forEach(cb => {
    cb.checked = checked;
    const key = decodeURIComponent(cb.dataset.key || '');
    if (key) {
      if (checked) pmState.selectedKeys.add(key);
      else pmState.selectedKeys.delete(key);
    }
  });
  pmUpdateSelectedCount();
}

function pmOnCheckboxChange(cb) {
  const key = decodeURIComponent(cb.dataset.key || '');
  if (!key) return;
  if (cb.checked) pmState.selectedKeys.add(key);
  else pmState.selectedKeys.delete(key);
  pmUpdateSelectedCount();
}

function pmUpdateSelectedCount() {
  const count = pmState.selectedKeys.size;
  const el = document.getElementById('pm-selected-count');
  if (el) el.textContent = `${count} dipilih`;
  const btn = document.getElementById('pm-btn-remove-selected');
  if (btn) btn.disabled = count === 0;
  const master = document.getElementById('pm-select-all');
  if (master) {
    const pageCbs = document.querySelectorAll('.pm-cb');
    master.checked = pageCbs.length > 0 && Array.from(pageCbs).every(cb => cb.checked);
  }
}

async function pmTestSingle(proxyStr, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = '⏳...';
  }
  try {
    const res = await fetch('/api/proxies/test_single', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ proxy: proxyStr })
    });
    const d = await res.json();
    if (d.ok) {
      showToast(`Proxy LIVE: ${d.latency}ms`);
      pmRefresh(true);
    } else {
      showToast(`Proxy FAIL: ${d.error || 'Timeout'}`);
      pmRefresh(true);
    }
  } catch(e) {
    showToast('Test Error: ' + e.message);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = '⚡ Test';
    }
  }
}

async function pmClearDead() {
  if (!confirm('Hapus semua proxy yang berstatus FAIL / DEAD dari database & file?')) return;
  try {
    const res = await fetch('/api/proxies/remove', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ action: 'clear_dead' })
    });
    const d = await res.json();
    if (d.ok) {
      showToast(`✓ ${d.removed} dead proxy berhasil dibersihkan! (Tersisa: ${d.total})`);
      pmState.selectedKeys.clear();
      pmRefresh(false);
    } else {
      showToast('Gagal: ' + (d.error || 'Error server'));
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

async function pmDeleteSingle(proxyStr) {
  if (!confirm(`Hapus proxy: ${proxyStr}?`)) return;
  try {
    const res = await fetch('/api/proxies/remove', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ text: proxyStr })
    });
    const d = await res.json();
    if (d.ok) {
      showToast('Proxy berhasil dihapus');
      pmState.selectedKeys.delete(proxyStr);
      pmRefresh(true);
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

async function pmRemoveSelected() {
  if (!pmState.selectedKeys.size) return showToast('Pilih proxy dulu');
  const arr = Array.from(pmState.selectedKeys);
  if (!confirm(`Hapus ${arr.length} proxy yang dipilih?`)) return;
  try {
    const res = await fetch('/api/proxies/remove', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ text: arr.join('\n') })
    });
    const d = await res.json();
    if (d.ok) {
      showToast(`${d.removed} proxy dihapus`);
      pmState.selectedKeys.clear();
      pmRefresh(true);
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

function pmToggleAddBox(forceOpen) {
  const box = document.getElementById('pm-add-box');
  if (!box) return;
  const isHidden = box.style.display === 'none' || !box.style.display;
  const shouldOpen = forceOpen !== undefined ? forceOpen : isHidden;
  box.style.display = shouldOpen ? 'block' : 'none';
  if (shouldOpen) {
    const inp = document.getElementById('pm-add-input');
    if (inp) inp.focus();
  }
}

async function pmClearAll() {
  if (!confirm('⚠️ PERINGATAN: Apakah Anda yakin ingin MENGHAPUS SEMUA DATA PROXY dari database dan file netflix_proxies.txt? Tindakan ini akan mengosongkan seluruh pool proxy.')) return;
  try {
    const res = await fetch('/api/proxies/remove', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ action: 'clear_all' })
    });
    const d = await res.json();
    if (d.ok) {
      showToast('✓ Seluruh data proxy berhasil dikosongkan!');
      pmState.selectedKeys.clear();
      pmRefresh(false);
    } else {
      showToast('Gagal: ' + (d.error || 'Server error'));
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  }
}

function pmOnFileSelected(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(evt) {
    const content = evt.target.result;
    const inp = document.getElementById('pm-add-input');
    if (inp) {
      inp.value = content;
      pmUpdateInputCount();
      pmToggleAddBox(true);
      const lines = content.trim().split('\n').filter(l => l.trim() && !l.trim().startsWith('#')).length;
      showToast(`File "${file.name}" dimuat (${lines} proxy terdeteksi)`);
    }
  };
  reader.readAsText(file);
}

function pmUpdateInputCount() {
  const inp = document.getElementById('pm-add-input');
  const countEl = document.getElementById('pm-input-count');
  if (!inp || !countEl) return;
  const lines = inp.value.split('\n').filter(l => l.trim() && !l.trim().startsWith('#')).length;
  countEl.textContent = `(${lines} baris)`;
}

function pmInsertSampleProxies() {
  const inp = document.getElementById('pm-add-input');
  if (!inp) return;
  const samples = [
    '103.152.112.162:80',
    '45.167.124.5:999',
    '185.199.229.156:7492',
    '103.149.130.38:80',
    '103.155.218.106:8080'
  ];
  inp.value = samples.join('\n');
  pmUpdateInputCount();
  showToast('Contoh format proxy dimasukkan ke input');
}

function pmResetFilters() {
  pmState.status = 'ALL';
  pmState.search = '';
  pmState.page = 1;
  const searchInput = document.getElementById('pm-search');
  if (searchInput) searchInput.value = '';
  document.querySelectorAll('#pm-filter-buttons .pm-filter-btn').forEach(btn => {
    if (btn.dataset.status === 'ALL') {
      btn.style.background = 'var(--accent)';
      btn.style.color = '#fff';
    } else {
      btn.style.background = 'var(--bg-subtle)';
      btn.style.color = 'var(--text-muted)';
    }
  });
  pmRefresh(false);
}

async function pmAddProxies() {
  const text = document.getElementById('pm-add-input').value.trim();
  if (!text) return showToast('Paste proxy list terlebih dahulu');
  const statusEl = document.getElementById('pm-add-status');
  if (statusEl) {
    statusEl.textContent = 'Menambahkan ke pool...';
    statusEl.style.color = 'var(--text-muted)';
  }
  try {
    const res = await fetch('/api/proxies/add', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ text })
    });
    const d = await res.json();
    if (d.ok) {
      if (statusEl) {
        statusEl.textContent = `✓ ${d.added} proxy baru ditambahkan (Total: ${d.total})`;
        statusEl.style.color = 'var(--live)';
      }
      document.getElementById('pm-add-input').value = '';
      showToast(`✓ ${d.added} proxy baru ditambahkan!`);
      setTimeout(() => {
        pmToggleAddBox();
        pmRefresh(false);
      }, 1000);
    } else {
      if (statusEl) {
        statusEl.textContent = '✕ ' + (d.error || 'Gagal');
        statusEl.style.color = 'var(--dead)';
      }
    }
  } catch(e) {
    if (statusEl) {
      statusEl.textContent = '✕ ' + e.message;
      statusEl.style.color = 'var(--dead)';
    }
  }
}

async function pmReplaceAll() {
  const text = prompt('Paste SEMUA proxy baru (ini akan me-replace seluruh list yang ada):');
  if (text === null) return;
  if (!text.trim()) return showToast('Input kosong, dibatalkan.');
  try {
    const res = await fetch('/api/proxies/save', {
      method: 'POST',
      headers: getAuthHeaders({'Content-Type': 'application/json'}),
      body: JSON.stringify({ text })
    });
    const d = await res.json();
    if (d.ok) {
      showToast(`✓ Seluruh proxy diganti — ${d.count} proxy dimuat`);
      pmState.selectedKeys.clear();
      pmRefresh(false);
    }
  } catch(e) {
    showToast('Error replace: ' + e.message);
  }
}

function pmExportHealthy() {
  window.open('/api/proxies/export?mode=healthy', '_blank');
}

async function pmCopyHealthy() {
  try {
    const res = await fetch('/api/proxies/export?mode=healthy', { headers: getAuthHeaders() });
    const txt = await res.text();
    if (!txt.trim()) return showToast('Belum ada proxy LIVE untuk disalin');
    await navigator.clipboard.writeText(txt.trim());
    const count = txt.trim().split('\n').length;
    showToast(`📋 ${count} proxy LIVE disalin ke clipboard!`);
  } catch(e) {
    showToast('Gagal menyalin: ' + e.message);
  }
}

function pmCopyText(text) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast(`Disalin: ${text}`);
  }).catch(() => {
    showToast('Gagal menyalin text');
  });
}

// Drag & drop directly onto bulk-input textarea
(function initBulkDragDrop() {
  const bulkInput = document.getElementById('bulk-input');
  if (bulkInput) {
    bulkInput.addEventListener('dragover', (e) => {
      e.preventDefault();
      bulkInput.style.borderColor = 'var(--primary)';
    });
    bulkInput.addEventListener('dragleave', () => {
      bulkInput.style.borderColor = '';
    });
    bulkInput.addEventListener('drop', (e) => {
      e.preventDefault();
      bulkInput.style.borderColor = '';
      handleBulkDrop(e);
    });
  }
})();



// ═══════════════════════════════════════════════════════════════════
// NEW REDESIGNED UI CONTROLLERS & DASHBOARD TELEMETRY
// ═══════════════════════════════════════════════════════════════════

// Live Digital Clock
function updateClock() {
  const clockEl = document.getElementById('topbar-clock');
  if (clockEl) {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    clockEl.textContent = `${h}:${m}:${s}`;
  }
}
setInterval(updateClock, 1000);
updateClock();

// Topbar Scroll Shadow Controller
(function initScrollShadow() {
  const topbar = document.querySelector('.topbar');
  if (!topbar) return;
  let ticking = false;
  window.addEventListener('scroll', function() {
    if (!ticking) {
      requestAnimationFrame(function() {
        topbar.classList.toggle('scrolled', window.scrollY > 8);
        ticking = false;
      });
      ticking = true;
    }
  }, { passive: true });
})();

// Sidebar Collapse Controller
function toggleSidebarCollapse() {
  const sidebar = document.getElementById('app-sidebar');
  if (sidebar) {
    sidebar.classList.toggle('collapsed');
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebar_collapsed', isCollapsed ? '1' : '0');
    // Update main-content margin via JS as fallback for sibling selector
    const main = document.querySelector('.main-content');
    if (main) main.style.marginLeft = isCollapsed ? '68px' : '250px';
  }
}

// Mobile Sidebar Controller
function toggleMobileSidebar(force) {
  const sidebar = document.getElementById('app-sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (!sidebar || !overlay) return;
  
  const isOpen = (typeof force === 'boolean') ? force : !sidebar.classList.contains('mobile-open');
  sidebar.classList.toggle('mobile-open', isOpen);
  overlay.classList.toggle('active', isOpen);
  document.body.style.overflow = isOpen ? 'hidden' : '';
}

// Restore saved sidebar preference
(function restoreSidebar() {
  if (localStorage.getItem('sidebar_collapsed') === '1' && window.innerWidth > 992) {
    const sidebar = document.getElementById('app-sidebar');
    if (sidebar) {
      sidebar.classList.add('collapsed');
      const main = document.querySelector('.main-content');
      if (main) main.style.marginLeft = '68px';
    }
  }
})();

// Dynamic View Header updater
function updateViewHeader(tab) {
  const titleEl = document.getElementById('view-title');
  const subEl = document.getElementById('view-subtitle');
  const actionsEl = document.getElementById('view-header-actions');
  if (!titleEl) return;

  const meta = {
    dashboard: {
      title: 'Operations Dashboard',
      subtitle: 'Real-time telemetry, service launchers & suite performance',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="fetchDashboardData()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg> Refresh Telemetry</button>'
    },
    checkers: {
      title: 'Account Checkers Hub',
      subtitle: 'Select a specialized credential validation engine below',
      actions: ''
    },
    single: {
      title: 'Netflix Token Generator & Single Check',
      subtitle: 'Inspect raw cookie, generate direct Netflix Token & launch links',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    bulk: {
      title: 'Netflix Concurrent Bulk Check',
      subtitle: 'Multi-threaded high-speed cookie batch processing with Netscape/JSON parser',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    disney: {
      title: 'Disney+ BAMTech Checker',
      subtitle: 'Direct API authentication & subscription entitlement validation',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    crunchyroll: {
      title: 'Crunchyroll Anime Checker',
      subtitle: 'Direct authentication endpoint & subscription tier detection',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    expressvpn: {
      title: 'ExpressVPN Account Checker',
      subtitle: 'VPN authentication engine & expiration / subscription status',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    spotify: {
      title: 'Spotify Account Checker',
      subtitle: 'Web Player API & sp_dc validation for Premium, Family & Duo plans',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    outlook: {
      title: 'Outlook / Hotmail MS Graph Checker',
      subtitle: 'Microsoft protocol verification with accurate 2FA & phone lock detection',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    openai: {
      title: 'OpenAI / ChatGPT Cookie Checker',
      subtitle: 'Session-token validation & subscription plan detection (Free, Plus, Pro, Team, Enterprise)',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    primevideo: {
      title: 'Prime Video Cookie Checker',
      subtitle: 'Amazon Prime Video session cookie validation & subscription status detection',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="switchTab(\'dashboard\')">← Dashboard</button>'
    },
    history: {
      title: 'History Database',
      subtitle: 'SQLite persistent verification history with real-time query & CSV export',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="exportCsvWithAuth()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Export CSV</button>'
    },
    analytics: {
      title: 'Visual Analytics',
      subtitle: 'Graphical telemetry on account statuses, subscription tiers & geographic distribution',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="loadAnalytics()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg> Refresh</button>'
    },
    proxymanager: {
      title: 'Proxy Manager & Batch Tester',
      subtitle: 'High-speed proxy pool inspection, parallel batch testing & health management',
      actions: '<button type="button" class="btn-subtle btn-sm" onclick="pmRefresh()"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg> Refresh Pool</button>'
    },
    settings: {
      title: 'System Settings & Security',
      subtitle: 'Manage dashboard security PIN, notification preferences & runtime diagnostics',
      actions: ''
    }
  };

  const current = meta[tab] || meta['dashboard'];
  titleEl.textContent = current.title;
  subEl.textContent = current.subtitle;
  if (actionsEl) actionsEl.innerHTML = current.actions;
}

// Global Dashboard Telemetry Aggregator
let globalDbStats = { total: 0, live: 0, bad: 0, hold: 0, raw: {}, services: {} };
let _dashRefreshTimer = null;

// Debounced dashboard refresh — call after any check saves to DB.
// Waits 800ms so rapid bulk checks batch into a single API call.
function scheduleDashboardRefresh() {
  if (_dashRefreshTimer) clearTimeout(_dashRefreshTimer);
  _dashRefreshTimer = setTimeout(() => { _dashRefreshTimer = null; fetchDashboardData(); }, 800);
}

async function fetchDashboardData() {
  try {
    const aRes = await fetch('/api/stats');
    if (aRes.ok) {
      const aData = await aRes.json();
      if (aData.status_counts) {
        const sc = aData.status_counts;
        const dbLive = (sc.LIVE || 0) + (sc.PREMIUM || 0) + (sc.FREE || 0);
        const dbBad = (sc.BAD || 0) + (sc.DEAD || 0);
        const dbHold = (sc.HOLD || 0) + (sc.LOCKED || 0) + (sc['2FA'] || 0) + (sc.PHONE_LOCKED || 0);
        const dbTotal = Object.values(sc).reduce((a, b) => a + b, 0);
        globalDbStats = {
          total: dbTotal,
          live: dbLive,
          bad: dbBad,
          hold: dbHold,
          raw: sc,
          services: aData.services || {}
        };
      }
      if (aData.proxy) {
        pmState.total = aData.proxy.total || 0;
        pmState.healthy = aData.proxy.healthy || 0;
      }
    }
  } catch(e) {
    console.error('fetchDashboardData error:', e);
  }

  refreshDashboardCards();
}

function refreshDashboardCards() {
  // All results are saved to DB immediately on check, so DB stats are the
  // single source of truth.  Re-fetch from /api/stats on every dashboard
  // refresh so numbers stay current without double-counting session vars.
  const grandTotal = globalDbStats.total || 0;
  const grandLive  = globalDbStats.live  || 0;
  const grandBad   = globalDbStats.bad   || 0;
  const grandHold  = globalDbStats.hold  || 0;
  const hitRate = grandTotal > 0 ? ((grandLive / grandTotal) * 100).toFixed(1) : '0.0';

  // Update DOM elements
  const elTotal = document.getElementById('dash-stat-total');
  const elLive = document.getElementById('dash-stat-live');
  const elBad = document.getElementById('dash-stat-bad');
  const elHold = document.getElementById('dash-stat-hold');
  const elHitRate = document.getElementById('dash-stat-hitrate');
  const elHitRateBar = document.getElementById('dash-hitrate-bar');
  const elProxy = document.getElementById('dash-stat-proxy');
  const elProxyMeta = document.getElementById('dash-meta-proxy-live');
  const elTeleTotal = document.getElementById('dash-tele-total');
  const elTeleLive = document.getElementById('dash-tele-live');

  if (elTotal) elTotal.textContent = grandTotal.toLocaleString('id-ID');
  if (elLive) elLive.textContent = grandLive.toLocaleString('id-ID');
  if (elBad) elBad.textContent = grandBad.toLocaleString('id-ID');
  if (elHold) elHold.textContent = grandHold.toLocaleString('id-ID');
  if (elHitRate) elHitRate.textContent = `${hitRate}%`;
  if (elHitRateBar) elHitRateBar.style.width = `${Math.min(100, Math.max(0, hitRate))}%`;
  
  const poolTot = (pmState.total || 10534);
  const poolLive = (pmState.healthy || 10529);
  if (elProxy) elProxy.textContent = poolTot.toLocaleString('id-ID');
  if (elProxyMeta) elProxyMeta.textContent = `${poolLive.toLocaleString('id-ID')} Verified Live`;
  if (elTeleTotal) elTeleTotal.textContent = poolTot.toLocaleString('id-ID');
  if (elTeleLive) elTeleLive.textContent = poolLive.toLocaleString('id-ID');

  // Update hub cards
  updateServiceHubCards();
}

function updateServiceHubCards() {
  const s = globalDbStats.services || {};

  // All checkers save to DB immediately, so DB is the single source of truth.
  // No session stats added — prevents double-counting.

  // 1. Netflix
  const nfDb = s.netflix || { checks: 0, live: 0, bad: 0 };
  const nfElChecks = document.getElementById('hub-stat-nf-checks');
  const nfElLive = document.getElementById('hub-stat-nf-live');
  const nfElBad = document.getElementById('hub-stat-nf-bad');
  if (nfElChecks) nfElChecks.textContent = (nfDb.checks || 0).toLocaleString('id-ID');
  if (nfElLive) nfElLive.textContent = (nfDb.live || 0).toLocaleString('id-ID');
  if (nfElBad) nfElBad.textContent = (nfDb.bad || 0).toLocaleString('id-ID');

  // 2. Disney+
  const dDb = s.disney || { checks: 0, live: 0, bad: 0 };
  const dElChecks = document.getElementById('hub-stat-disney-checks');
  const dElLive = document.getElementById('hub-stat-disney-live');
  const dElBad = document.getElementById('hub-stat-disney-bad');
  if (dElChecks) dElChecks.textContent = (dDb.checks || 0).toLocaleString('id-ID');
  if (dElLive) dElLive.textContent = (dDb.live || 0).toLocaleString('id-ID');
  if (dElBad) dElBad.textContent = (dDb.bad || 0).toLocaleString('id-ID');

  // 3. Crunchyroll
  const crDb = s.crunchyroll || { checks: 0, live: 0, bad: 0 };
  const crElChecks = document.getElementById('hub-stat-cr-checks');
  const crElLive = document.getElementById('hub-stat-cr-live');
  const crElBad = document.getElementById('hub-stat-cr-bad');
  if (crElChecks) crElChecks.textContent = (crDb.checks || 0).toLocaleString('id-ID');
  if (crElLive) crElLive.textContent = (crDb.live || 0).toLocaleString('id-ID');
  if (crElBad) crElBad.textContent = (crDb.bad || 0).toLocaleString('id-ID');

  // 4. ExpressVPN
  const evpnDb = s.expressvpn || { checks: 0, live: 0, bad: 0 };
  const evpnElChecks = document.getElementById('hub-stat-evpn-checks');
  const evpnElLive = document.getElementById('hub-stat-evpn-live');
  const evpnElBad = document.getElementById('hub-stat-evpn-bad');
  if (evpnElChecks) evpnElChecks.textContent = (evpnDb.checks || 0).toLocaleString('id-ID');
  if (evpnElLive) evpnElLive.textContent = (evpnDb.live || 0).toLocaleString('id-ID');
  if (evpnElBad) evpnElBad.textContent = (evpnDb.bad || 0).toLocaleString('id-ID');

  // 5. Spotify
  const spDb = s.spotify || { checks: 0, live: 0, bad: 0 };
  const spElChecks = document.getElementById('hub-stat-sp-checks');
  const spElLive = document.getElementById('hub-stat-sp-live');
  const spElBad = document.getElementById('hub-stat-sp-bad');
  if (spElChecks) spElChecks.textContent = (spDb.checks || 0).toLocaleString('id-ID');
  if (spElLive) spElLive.textContent = (spDb.live || 0).toLocaleString('id-ID');
  if (spElBad) spElBad.textContent = (spDb.bad || 0).toLocaleString('id-ID');

  // 6. Outlook
  const outDb = s.outlook || { checks: 0, live: 0, bad: 0 };
  const outElChecks = document.getElementById('hub-stat-out-checks') || document.getElementById('hub-stat-outlook-checks');
  const outElLive = document.getElementById('hub-stat-out-live') || document.getElementById('hub-stat-outlook-live');
  const outElBad = document.getElementById('hub-stat-out-bad') || document.getElementById('hub-stat-outlook-bad');
  if (outElChecks) outElChecks.textContent = (outDb.checks || 0).toLocaleString('id-ID');
  if (outElLive) outElLive.textContent = (outDb.live || 0).toLocaleString('id-ID');
  if (outElBad) outElBad.textContent = (outDb.bad || 0).toLocaleString('id-ID');

  // 7. OpenAI / ChatGPT
  const oaiDb = s.openai || { checks: 0, live: 0, bad: 0 };
  const oaiElChecks = document.getElementById('hub-stat-oai-checks');
  const oaiElLive = document.getElementById('hub-stat-oai-live');
  const oaiElBad = document.getElementById('hub-stat-oai-bad');
  if (oaiElChecks) oaiElChecks.textContent = (oaiDb.checks || 0).toLocaleString('id-ID');
  if (oaiElLive) oaiElLive.textContent = (oaiDb.live || 0).toLocaleString('id-ID');
  if (oaiElBad) oaiElBad.textContent = (oaiDb.bad || 0).toLocaleString('id-ID');

  // 8. Prime Video
  const pvDb = s.primevideo || { checks: 0, live: 0, bad: 0 };
  const pvElChecks = document.getElementById('hub-stat-pv-checks');
  const pvElLive = document.getElementById('hub-stat-pv-live');
  const pvElBad = document.getElementById('hub-stat-pv-bad');
  if (pvElChecks) pvElChecks.textContent = (pvDb.checks || 0).toLocaleString('id-ID');
  if (pvElLive) pvElLive.textContent = (pvDb.live || 0).toLocaleString('id-ID');
  if (pvElBad) pvElBad.textContent = (pvDb.bad || 0).toLocaleString('id-ID');
}



// Initialization
fetchDashboardData();
updateViewHeader('dashboard');


// ── BULLETPROOF CLIPBOARD & GRAB LIVE ACCOUNT LOGIC ───────────────────
let currentGrabbedData = null;

async function copyToClipboardBulletproof(text) {
  if (!text) return false;
  let copied = false;

  // Layer 1: Modern navigator.clipboard API
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (e) {
      console.warn('navigator.clipboard.writeText failed, falling back to textarea...', e);
    }
  }

  // Layer 2: Textarea selection + execCommand
  if (!copied) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      ta.style.top = '-9999px';
      ta.style.opacity = '0';
      ta.setAttribute('readonly', '');
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, ta.value.length);
      copied = document.execCommand('copy');
      document.body.removeChild(ta);
    } catch (e2) {
      console.warn('execCommand copy failed:', e2);
      copied = false;
    }
  }

  return copied;
}

async function grabRandomLiveAccount(service, btn) {
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<svg class="animate-spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> <span>Mengambil...</span>`;
  }

  try {
    const authHeaders = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
    const res = await fetch(`/api/account/random?service=${encodeURIComponent(service)}`, {
      headers: authHeaders
    });
    const d = await res.json();

    if (d.success && d.content) {
      currentGrabbedData = d;
      currentGrabbedData.requestedService = service;

      // 1. Copy to clipboard
      const copySuccess = await copyToClipboardBulletproof(d.content);

      // 2. Audio feedback
      if (typeof playAlertSound === 'function') {
        playAlertSound('live');
      }

      // 3. Visual button feedback
      if (btn) {
        btn.classList.add('copied');
        btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> <span>Tersalin!</span>`;
      }

      // 4. Open Grab Modal for full visual confirmation and 1-click actions
      openGrabModal(d, service, copySuccess);

      const identifier = d.email ? maskEmail(d.email) : (d.plan || 'Live Cookie');
      const svcLabel = service.toUpperCase();
      showToast(`✓ [${svcLabel}] ${identifier} berhasil diambil!`, 'success');

      setTimeout(() => {
        if (btn) {
          btn.classList.remove('copied');
          btn.disabled = false;
          btn.innerHTML = originalHtml;
        }
      }, 2500);
    } else {
      showToast(d.error || `Belum ada akun/cookie LIVE untuk ${service} di database`, 'warn');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }
  } catch (err) {
    console.error('grabRandomLiveAccount error:', err);
    showToast(`✕ Gagal mengambil data: ${err.message}`, 'error');
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}

function openGrabModal(data, service, copySuccess) {
  const modal = document.getElementById('grab-modal');
  if (!modal) return;

  const titleEl = document.getElementById('grab-modal-title');
  const subEl = document.getElementById('grab-modal-sub');
  const svcEl = document.getElementById('grab-modal-service');
  const planEl = document.getElementById('grab-modal-plan');
  const countryEl = document.getElementById('grab-modal-country');
  const contentEl = document.getElementById('grab-modal-content');
  const copyStatusEl = document.getElementById('grab-modal-copy-status');

  const svcName = (service || data.service || 'Account').toUpperCase();
  if (titleEl) titleEl.textContent = `Live ${svcName} Retrieved`;
  if (subEl) subEl.textContent = data.email ? `Akun: ${maskEmail(data.email)}` : 'Cookie live ditarik langsung dari database';
  if (svcEl) {
    svcEl.textContent = svcName;
    svcEl.className = `service-tag ${service === 'netflix' ? 'red' : service === 'expressvpn' ? 'crimson' : service === 'disney' ? 'teal' : service === 'crunchyroll' ? 'orange' : service === 'spotify' ? 'green' : 'blue'}`;
  }
  if (planEl) planEl.textContent = data.plan || 'Active / Live';
  if (countryEl) countryEl.textContent = data.country || 'Global';
  if (copyStatusEl) {
    if (copySuccess) {
      copyStatusEl.textContent = '✓ Otomatis Tersalin ke Clipboard';
      copyStatusEl.style.color = '#10b981';
    } else {
      copyStatusEl.textContent = '⚠️ Klik "Salin Ulang" di bawah jika belum tersalin';
      copyStatusEl.style.color = '#f59e0b';
    }
  }
  if (contentEl) {
    contentEl.value = data.content;
    setTimeout(() => {
      contentEl.focus();
      contentEl.select();
    }, 60);
  }

  modal.style.display = 'flex';
}

function closeGrabModal() {
  const modal = document.getElementById('grab-modal');
  if (modal) modal.style.display = 'none';
}

async function copyGrabModalContent(btn) {
  const contentEl = document.getElementById('grab-modal-content');
  if (!contentEl) return;
  contentEl.focus();
  contentEl.select();
  const ok = await copyToClipboardBulletproof(contentEl.value);
  if (ok) {
    showToast('✓ Berhasil disalin ke clipboard!', 'success');
  } else {
    showToast('Teks dipilih, tekan Ctrl+C untuk menyalin', 'info');
  }
  if (btn) {
    const orig = btn.innerHTML;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> <span>Tersalin!</span>`;
    setTimeout(() => { btn.innerHTML = orig; }, 1800);
  }
}

function launchGrabModalService() {
  if (!currentGrabbedData) return;
  const svc = (currentGrabbedData.requestedService || currentGrabbedData.service || '').toLowerCase();
  const content = currentGrabbedData.content || '';
  closeGrabModal();

  if (svc === 'netflix' || svc === 'checker') {
    const sinp = document.getElementById('single-cookie');
    if (sinp) {
      sinp.value = content;
      switchTab('single');
      showToast('✓ Cookie Netflix dimasukkan ke Single Token Suite!', 'success');
    }
  } else if (svc === 'expressvpn' || svc === 'evpn') {
    const parts = content.split(':');
    if (parts.length >= 2) {
      const einp = document.getElementById('evpn-email');
      const pinp = document.getElementById('evpn-password');
      if (einp) einp.value = parts[0];
      if (pinp) pinp.value = parts.slice(1).join(':');
    }
    switchTab('expressvpn');
    showToast('✓ Akun ExpressVPN dimasukkan ke Checker!', 'success');
  } else if (svc === 'disney') {
    const parts = content.split(':');
    if (parts.length >= 2) {
      const einp = document.getElementById('disney-email');
      const pinp = document.getElementById('disney-password');
      if (einp) einp.value = parts[0];
      if (pinp) pinp.value = parts.slice(1).join(':');
    }
    switchTab('disney');
    showToast('✓ Akun Disney+ dimasukkan ke Checker!', 'success');
  } else if (svc === 'crunchyroll' || svc === 'cr') {
    const parts = content.split(':');
    if (parts.length >= 2) {
      const einp = document.getElementById('cr-email');
      const pinp = document.getElementById('cr-password');
      if (einp) einp.value = parts[0];
      if (pinp) pinp.value = parts.slice(1).join(':');
    }
    switchTab('crunchyroll');
    showToast('✓ Akun Crunchyroll dimasukkan ke Checker!', 'success');
  } else if (svc === 'spotify') {
    const sinp = document.getElementById('spotify-cookie');
    if (sinp) {
      sinp.value = content;
      switchTab('spotify');
      showToast('✓ Cookie/Akun Spotify dimasukkan ke Checker!', 'success');
    }
  } else if (svc === 'outlook' || svc === 'hotmail') {
    const parts = content.split(':');
    if (parts.length >= 2) {
      const einp = document.getElementById('outlook-email');
      const pinp = document.getElementById('outlook-password');
      if (einp) einp.value = parts[0];
      if (pinp) pinp.value = parts.slice(1).join(':');
    }
    switchTab('outlook');
    showToast('✓ Akun Outlook dimasukkan ke Checker!', 'success');
  } else if (svc === 'openai' || svc === 'chatgpt') {
    const sinp = document.getElementById('openai-cookie-input');
    if (sinp) {
      sinp.value = content;
      switchTab('openai');
      showToast('✓ Cookie OpenAI dimasukkan ke Checker!', 'success');
    }
  } else if (svc === 'primevideo' || svc === 'prime' || svc === 'amazon') {
    const sinp = document.getElementById('pv-cookie-input');
    if (sinp) {
      sinp.value = content;
      switchTab('primevideo');
      showToast('✓ Cookie PrimeVideo dimasukkan ke Checker!', 'success');
    }
  }
}



// PWA Service Worker Registration
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('NF-Sawava PWA active, scope:', reg.scope))
      .catch(err => console.debug('PWA registration skipped:', err));
  });
}
