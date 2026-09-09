# NF-Sawava ⚡

Netflix NFToken Generator & Membership Checker Web App.

Built-in:
- **NFToken Auto-login Link Generator** (via iOS mobile GraphQL API bypass).
- **Account Membership & Subscription Checker** (detect 4K / Premium / Standard, Next Billing Date, Country).
- **Multi-Proxy Support**: Webshare rotation / direct routing.
- **Cookie Format Support**: Raw `Cookie:` header, Netscape cookie export, and Cookie-Editor JSON format.
- Single-file zero-dependency backend (Python stdlib HTTP + `requests`).

---

## 🚀 Quick Start

### 1. Requirements
```bash
pip install requests urllib3
```

### 2. Run Server
```bash
python server.py
```

Buka browser di:
```text
http://localhost:8080
```

---

## ⚙️ Proxy Setup (Opsional)
Buat file `netflix_proxies.txt` di satu folder dengan `server.py` jika ingin menggunakan rotasi proxy:
```text
ip:port:username:password
http://ip:port
https://ip:port
socks5://ip:port
socks4://ip:port
ip:port
http://user:pass@ip:port
socks5://user:pass@ip:port
```

Jika file tidak ada atau opsi dimatikan di UI, server otomatis memakai koneksi direct.

---

## 📜 License
MIT
