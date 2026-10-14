# ⚡ NF-Sawava Suite

An advanced, modern, high-performance Multi-Service Account & Cookie Validation Suite, featuring an **Operations Dashboard**, real-time **Live Account Grabber**, resilient **Proxy Pool Management**, and browser-level **TLS Impersonation**.

---

## 🌟 Overview

**NF-Sawava Suite** is a modular web platform engineered for verifying credentials, session cookies, and refresh tokens across top streaming, VPN, AI, and utility services. It combines zero-dependency lightweight server architecture with browser-grade security impersonation, cryptographic database encryption, and seamless automated workflows.

---

## ✨ Supported Services & Checkers

| Service | Supported Input Formats | Detection & Capabilities |
| :--- | :--- | :--- |
| 🎬 **Netflix** | `NetflixId` Cookies, Netscape, JSON | iOS GraphQL API bypass, NFToken 1-click auto-login link generator, Plan tier (4K UHD / Standard / Basic), Expiration / Billing date, Country code. |
| ✨ **Disney+** | Combo (`user:pass`), Refresh Tokens | BAMSDK OAuth flow, Active subscription detection, Renewal date, Multi-profile support. |
| 🍙 **Crunchyroll** | Combo, `etp_rt_live` token, JSON Cookies | Direct OAuth token extraction, Profile inspection, Membership tier (Mega Fan / Fan / Free), Country code. |
| 🛡️ **ExpressVPN** | Combo (`email:password`) | Native Auth API verification, Premium Active, 7-Day Free Trial, Free, and Expired account validation. |
| 🎵 **Spotify** | Combo, `sp_dc` Cookies, JSON | Web Player API authentication, Plan type (Individual, Family, Duo, Student), Country, Auto-renew flag. |
| 📬 **Outlook / MS** | Combo (`email:pass`) | Microsoft OAuth 2.0 flow, Live / Hotmail / Outlook account validity testing. |
| 🤖 **OpenAI / ChatGPT** | Session Tokens, Raw Cookies | API session verification, Plan detection (`account.plan_type`: Free / Plus / Pro / Team), Token revocation status. |
| 📦 **Prime Video** | Regional JSON Cookies, Netscape | Multi-account parsing, Regional cookie keys (`-av`, `-acbid`), Prime membership active verification. |

---

## 🚀 Key Features

### 1. 🎯 Operations Dashboard & 1-Click Live Account Vault
- **Instant Grabber**: Click *"Ambil Akun Live"* on any service card in the Operations Hub to fetch a fresh LIVE account from the database.
- **Bulletproof Clipboard Copying**: Automatically decrypts credentials and copies them straight to your clipboard with audio feedback.
- **Grab Confirmation Modal**: Inspect masked email, plan details, country, and trigger 1-click launcher links directly.
- **Open Dashboard Mode**: Public access to account grabbing without forced login, backed by optional Dashboard PIN locks and persistent HMAC-signed tokens (survives server restarts).

### 2. 🌐 Adaptive TLS Fingerprint Engine
- Powered by `curl_cffi` to mimic authentic browser TLS ClientHellos (`Chrome 131`, `Chrome 124`, `Safari 18`, `Edge 101`).
- Bypasses Cloudflare, Akamai, and perimeter anti-bot defenses without launching headless browsers.
- Automatic fallback to standard connection engines when impersonation is unavailable.

### 3. 🛡️ Resilient Proxy Architecture
- **Multi-Protocol Support**: HTTP, HTTPS, SOCKS4, and SOCKS5 with custom authentication (`user:pass@ip:port` or `ip:port:user:pass`).
- **Live Health Diagnostics**: Concurrent multi-worker background proxy checker testing real latency against validation endpoints.
- **Auto-Scraping Engine**: Built-in background scraper harvesting free proxy lists continuously.
- **External Provider Sync**: Integrates with external proxy APIs (Custom, Webshare, etc.) with configurable synchronization intervals.
- **Intelligent Routing**: Dynamic cooldown and penalty scoring for failed proxies.

### 4. 🔒 Enterprise-Grade Security
- **Transparent Credential Encryption**: Sensitive account combos and raw session cookies are encrypted at rest using AES-GCM (`enc:...`).
- **Cryptographic Dashboard Tokens**: Signed HMAC session tokens that remain valid across server reboots.
- **Granular Rate-Limiting**: IP-bucket rate limiters protecting public endpoints and administrative operations.
- **Protected Admin Panel**: `/admin` dashboard isolated by master API keys and session tokens.

### 5. 🔔 Multi-Channel Webhook Notifications
- Real-time instant alerts dispatched to **Telegram Bot** and **Discord Webhooks** upon discovering LIVE / Premium accounts or completing batch validation jobs.

---

## 📂 Project Structure

```text
NF-Sawava/
├── checkers/                   # Service checker modules
│   ├── netflix.py              # Netflix NFToken & membership logic
│   ├── disney.py               # Disney+ BAMSDK token validator
│   ├── crunchyroll.py          # Crunchyroll OAuth & profile extractor
│   ├── expressvpn.py           # ExpressVPN auth & plan checker
│   ├── spotify.py              # Spotify sp_dc & web player checker
│   ├── outlook.py              # Microsoft / Outlook OAuth checker
│   ├── openai.py               # ChatGPT session & plan checker
│   └── primevideo.py           # Prime Video regional cookie validator
├── modules/                    # Core system components
│   ├── auth.py                 # HMAC session signing & client auth guards
│   ├── batch_runner.py         # Multi-worker async batch execution engine
│   ├── config.py               # Centralized configuration management
│   ├── db.py                   # SQLite engine with AES-GCM encryption
│   ├── detector.py             # Cookie & combo auto-format detectors
│   ├── notifications.py        # Telegram & Discord webhook dispatchers
│   ├── proxy_auto_scraper.py   # Multi-source public proxy collector
│   ├── proxy_manager.py        # Proxy pool, scoring, health checks
│   ├── rechecker.py            # Automated re-check engine
│   ├── sse.py                  # Server-Sent Events live status streaming
│   └── tls_engine.py           # curl_cffi browser impersonation wrapper
├── static/                     # Frontend client assets
│   ├── css/style.css           # Premium dark-mode interface stylesheet
│   └── js/app.js               # Reactive single-page application logic
├── web/                        # Web templates & PWA manifests
│   ├── index.html              # Main Operations Dashboard & Checker UI
│   ├── admin.html              # Dedicated Administration Control Panel
│   ├── manifest.json           # PWA web manifest
│   └── sw.js                   # Service Worker cache
├── data/                       # Local databases and proxy lists (ignored in git)
├── deploy/                     # Deployment configurations (Docker, Render)
├── server.py                   # Main HTTP API & web application server
├── start.bat                   # 1-Click launcher script for Windows
└── requirements.txt            # Python dependencies
```

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- Git

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone https://github.com/shwtrya/NF-Sawava.git
cd NF-Sawava
pip install -r requirements.txt
```

### 3. Running the Server

#### Windows (1-Click):
Double-click `start.bat` or run:
```cmd
start.bat
```

#### Terminal / Linux / macOS:
```bash
python server.py
```

Access the web applications:
- **Operations Dashboard**: `http://localhost:8080`
- **Admin Control Panel**: `http://localhost:8080/admin`

---

## 🛠️ Configuration (`suite_config.json`)

The server automatically initializes `suite_config.json` on its first run:
```json
{
  "api_key": "YOUR_MASTER_API_KEY",
  "dashboard_pin": "",
  "rate_limits": {
    "checker": 200,
    "admin": 50
  },
  "notifications": {
    "telegram": {
      "enabled": false,
      "bot_token": "",
      "chat_id": "",
      "notify_on_live": true
    },
    "discord": {
      "enabled": false,
      "webhook_url": "",
      "notify_on_live": true
    }
  },
  "db_encryption_key": "YOUR_AES_KEY"
}
```
*Note: If `dashboard_pin` is empty, the Operations Dashboard operates in open mode. You can set or change the PIN at any time in `/admin`.*

---

## 🌐 API Overview

| Endpoint | Method | Description | Auth Required |
| :--- | :---: | :--- | :---: |
| `/api/health` | `GET` | Health check, proxy pool size, and TLS status | ❌ Public |
| `/api/stats` | `GET` | Aggregated checker statistics & analytics | ❌ Public |
| `/api/account/random` | `GET` | Fetch random decrypted LIVE account for service | 🛡️ Dashboard / API Key |
| `/api/{service}/check` | `POST` | Check combo credentials or cookies | ❌ Public / Rate-limited |
| `/api/bulk/start` | `POST` | Start background multi-threaded batch job | ❌ Public / Rate-limited |
| `/api/bulk/status` | `GET` | Retrieve real-time progress of batch job | ❌ Public |
| `/api/proxies` | `GET` | List tested proxies and health metrics | ❌ Public |
| `/api/admin/keys` | `GET/POST`| Create, list, or revoke API Keys | 🔑 Admin Auth |
| `/api/history/delete` | `POST` | Delete specific history records | 🔑 Admin Auth |
| `/api/dashboard-pin/set`| `POST` | Set or update dashboard lock PIN | 🔑 Admin Auth |

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
