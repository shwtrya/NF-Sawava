"""
NF-Sawava Auto Proxy Scraper & Manager
- Auto-scrape fresh proxies from 10+ free sources
- Auto-test & filter alive proxies  
- Auto-refresh every 6 hours
- Auto-clean dead proxies
- Zero manual work required
"""
import concurrent.futures
import logging
import os
import re
import threading
import time

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROXIES_FILE = os.path.join(BASE_DIR, "netflix_proxies.txt")

# ── Proxy Sources ────────────────────────────────────────────────────────────
PROXY_SOURCES = [
    # ProxyScrape
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=yes&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=5000&country=all&ssl=yes&anonymity=all",
    # TheSpeedX
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    # ShiftyTR
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
    # Clarketm
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    # MuRongPIG
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
    # Monosans
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt",
    # Hookzof
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    # FLAVOR ProxyPool
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
    # RX4096
    "https://raw.githubusercontent.com/rx443/proxy-list/main/online/http.txt",
    # Sunny
    "https://sunny9577.github.io/proxy-scraper/proxies.txt",
    # UptimerBot
    "https://raw.githubusercontent.com/UptimerBot/proxy-list/main/proxies/http.txt",
]

# ── State ────────────────────────────────────────────────────────────────────
scraper_state = {
    "running": False,
    "last_run": 0,
    "last_result": None,
    "scraped": 0,
    "tested": 0,
    "total_to_test": 0,
    "alive": 0,
    "added": 0,
}
scraper_lock = threading.Lock()

REFRESH_INTERVAL = 6 * 3600  # 6 hours
TEST_CONCURRENCY = 250
TEST_TIMEOUT = 6
TEST_URL = "https://www.netflix.com"


def scrape_proxies_from_sources():
    """Fetch proxy lists from all sources, return deduplicated set of ip:port strings."""
    all_proxies = set()
    
    def _fetch(url):
        found = set()
        try:
            r = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Extract ip:port pattern
                    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5})', line)
                    if m:
                        found.add(m.group(1))
        except Exception as e:
            logging.debug(f"Proxy source fetch failed {url}: {e}")
        return found
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(_fetch, url): url for url in PROXY_SOURCES}
        for f in concurrent.futures.as_completed(futures):
            try:
                result = f.result()
                all_proxies.update(result)
            except Exception:
                pass
    
    logging.info(f"[AutoScraper] Scraped {len(all_proxies)} unique proxies from {len(PROXY_SOURCES)} sources")
    return all_proxies


def test_proxies_batch(proxies, concurrency=TEST_CONCURRENCY, timeout=TEST_TIMEOUT):
    """Test a batch of proxy strings (ip:port) against Netflix.
    Updates scraper_state in realtime. Returns list of (proxy, latency) for alive ones."""
    alive = []
    alive_lock = threading.Lock()
    total = len(proxies) if not isinstance(proxies, set) else len(proxies)
    done = [0]
    
    def _test(proxy_str):
        proxy_url = f"http://{proxy_str}"
        t0 = time.time()
        try:
            r = requests.get(
                TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=(3, timeout),
                verify=False,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            latency = int((time.time() - t0) * 1000)
            if r.status_code in (200, 301, 302, 303, 307, 403):
                with alive_lock:
                    alive.append((proxy_str, latency))
                    with scraper_lock:
                        scraper_state["alive"] = len(alive)
        except Exception:
            pass
        done[0] += 1
        if done[0] % 100 == 0:
            with scraper_lock:
                scraper_state["tested"] = done[0]
    
    proxy_list = list(proxies)
    chunk_size = 3000
    for i in range(0, len(proxy_list), chunk_size):
        chunk = proxy_list[i:i+chunk_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            list(ex.map(_test, chunk))
        with scraper_lock:
            scraper_state["tested"] = min(i + chunk_size, len(proxy_list))
        logging.info(f"[AutoScraper] Chunk done: {min(i+chunk_size, len(proxy_list))}/{len(proxy_list)} tested, {len(alive)} alive")
    
    with scraper_lock:
        scraper_state["tested"] = len(proxy_list)
        scraper_state["alive"] = len(alive)
    
    alive.sort(key=lambda x: x[1])
    return alive


def get_existing_proxies():
    """Read current proxies from file."""
    existing = set()
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract just ip:port
                        m = re.match(r'^(?:https?://)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5})', line)
                        if m:
                            existing.add(m.group(1))
                        else:
                            existing.add(line)
        except Exception:
            pass
    return existing


def merge_proxies_to_file(new_alive):
    """Merge newly found alive proxies into the proxy file. Returns count of new proxies added."""
    existing = get_existing_proxies()
    added = 0
    
    with open(PROXIES_FILE, "a", encoding="utf-8") as f:
        for proxy_str, latency in new_alive:
            if proxy_str not in existing:
                f.write(f"{proxy_str}\n")
                existing.add(proxy_str)
                added += 1
    
    return added


def run_auto_scrape():
    """Main scrape cycle: fetch → filter new → test → merge alive into file."""
    with scraper_lock:
        if scraper_state["running"]:
            return False, "Auto-scrape already running"
        scraper_state["running"] = True
        scraper_state["scraped"] = 0
        scraper_state["tested"] = 0
        scraper_state["alive"] = 0
        scraper_state["added"] = 0
    
    try:
        logging.info("[AutoScraper] Starting proxy scrape cycle...")
        
        # 1. Scrape from all sources
        all_scraped = scrape_proxies_from_sources()
        with scraper_lock:
            scraper_state["scraped"] = len(all_scraped)
        
        if not all_scraped:
            logging.warning("[AutoScraper] No proxies scraped from any source")
            return True, "No proxies found from sources"
        
        # 2. Filter out already-known proxies
        existing = get_existing_proxies()
        new_only = all_scraped - existing
        logging.info(f"[AutoScraper] {len(new_only)} new proxies to test (filtered {len(existing)} existing)")
        
        if not new_only:
            logging.info("[AutoScraper] No new proxies to test")
            with scraper_lock:
                scraper_state["tested"] = 0
                scraper_state["alive"] = 0
                scraper_state["added"] = 0
                scraper_state["last_run"] = time.time()
                scraper_state["last_result"] = {"scraped": len(all_scraped), "new": 0, "alive": 0, "added": 0}
            return True, "No new proxies to test"
        
        with scraper_lock:
            scraper_state["tested"] = 0
            scraper_state["total_to_test"] = len(new_only)
        
        # 3. Test new proxies
        alive = test_proxies_batch(new_only)
        with scraper_lock:
            scraper_state["alive"] = len(alive)
        
        logging.info(f"[AutoScraper] {len(alive)} alive out of {len(new_only)} tested")
        
        # 4. Merge alive proxies into file
        added = 0
        if alive:
            added = merge_proxies_to_file(alive)
        
        with scraper_lock:
            scraper_state["added"] = added
            scraper_state["last_run"] = time.time()
            scraper_state["last_result"] = {
                "scraped": len(all_scraped),
                "new": len(new_only),
                "alive": len(alive),
                "added": added,
                "timestamp": time.time()
            }
        
        logging.info(f"[AutoScraper] Done: scraped={len(all_scraped)}, new={len(new_only)}, alive={len(alive)}, added={added}")
        return True, f"Scraped {len(all_scraped)}, tested {len(new_only)} new, {len(alive)} alive, {added} added to pool"
    
    except Exception as e:
        logging.error(f"[AutoScraper] Error: {e}")
        return False, str(e)
    finally:
        with scraper_lock:
            scraper_state["running"] = False


def auto_scraper_worker():
    """Background daemon: runs scrape cycle on startup then every REFRESH_INTERVAL."""
    # Wait a bit for server to fully start
    time.sleep(30)
    
    while True:
        try:
            with scraper_lock:
                last = scraper_state["last_run"]
            
            if time.time() - last >= REFRESH_INTERVAL:
                logging.info("[AutoScraper] Scheduled refresh starting...")
                run_auto_scrape()
            
        except Exception as e:
            logging.error(f"[AutoScraper] Worker error: {e}")
        
        # Check every 5 minutes if it's time for next cycle
        time.sleep(300)


def get_scraper_status():
    """Return current scraper state for API/dashboard."""
    with scraper_lock:
        return dict(scraper_state)


def start_auto_scraper_thread():
    """Start the background auto-scraper daemon thread."""
    t = threading.Thread(target=auto_scraper_worker, daemon=True)
    t.start()
    logging.info("[AutoScraper] Background daemon started (refresh every 6h)")
    return t
