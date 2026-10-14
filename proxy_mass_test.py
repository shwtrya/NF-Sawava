#!/usr/bin/env python3
"""Mass proxy tester for NF-Sawava Suite.
Tests all proxies against netflix.com, saves alive ones to netflix_proxies.txt and proxy_cache DB.
"""
import asyncio
import aiohttp
import time
import sqlite3
import os
import sys

PROXY_FILE = r"C:\Users\Administrator\AppData\Local\hermes\cache\documents\doc_0c841482e1a1_proxies_raw.txt"
OUTPUT_FILE = r"C:\Users\Administrator\NF-Sawava\netflix_proxies.txt"
DB_FILE = r"C:\Users\Administrator\NF-Sawava\netflix_suite.db"
TEST_URL = "https://www.netflix.com"
CONCURRENCY = 300
TIMEOUT = 8  # seconds per proxy

alive = []
dead_count = 0
tested = 0
total = 0
lock = asyncio.Lock()

async def test_proxy(session, proxy_raw, sem):
    global dead_count, tested
    async with sem:
        # Normalize proxy URL
        if "://" in proxy_raw:
            proxy_url = proxy_raw
        else:
            proxy_url = f"http://{proxy_raw}"
        
        start = time.time()
        try:
            async with session.get(
                TEST_URL,
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                ssl=False,
                allow_redirects=True
            ) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status in (200, 301, 302, 303, 307, 403):
                    async with lock:
                        alive.append((proxy_raw, latency))
                        tested += 1
                    return
        except:
            pass
        
        async with lock:
            dead_count += 1
            tested += 1

async def main():
    global total
    
    # Load proxies
    with open(PROXY_FILE) as f:
        proxies = [l.strip() for l in f if l.strip()]
    total = len(proxies)
    print(f"[*] Testing {total} proxies with {CONCURRENCY} concurrent workers...")
    print(f"[*] Timeout: {TIMEOUT}s per proxy")
    print(f"[*] Target: {TEST_URL}")
    print()
    
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, limit_per_host=0, force_close=True, enable_cleanup_closed=True)
    
    start_time = time.time()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Progress reporter
        async def progress():
            while tested < total:
                elapsed = time.time() - start_time
                rate = tested / elapsed if elapsed > 0 else 0
                eta = (total - tested) / rate if rate > 0 else 0
                print(f"\r[~] Progress: {tested}/{total} tested | ✅ {len(alive)} alive | ❌ {dead_count} dead | {rate:.0f}/s | ETA: {eta:.0f}s", end="", flush=True)
                await asyncio.sleep(2)
        
        progress_task = asyncio.create_task(progress())
        
        # Launch all tests
        tasks = [test_proxy(session, p, sem) for p in proxies]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        progress_task.cancel()
    
    elapsed = time.time() - start_time
    print(f"\n\n[✓] Done in {elapsed:.1f}s")
    print(f"[✓] ALIVE: {len(alive)} | DEAD: {dead_count}")
    
    if not alive:
        print("[!] No alive proxies found.")
        return
    
    # Sort by latency
    alive.sort(key=lambda x: x[1])
    
    # Save to netflix_proxies.txt
    with open(OUTPUT_FILE, 'w') as f:
        for proxy, lat in alive:
            f.write(f"{proxy}\n")
    print(f"[✓] Saved {len(alive)} proxies to {OUTPUT_FILE}")
    
    # Update DB proxy_cache
    db = sqlite3.connect(DB_FILE)
    db.execute("PRAGMA busy_timeout = 30000")
    c = db.cursor()
    
    # Clear old cache
    c.execute("DELETE FROM proxy_cache")
    
    # Insert alive ones
    now = time.time()
    batch = [(p, "OK", lat, now) for p, lat in alive]
    c.executemany(
        "INSERT OR REPLACE INTO proxy_cache (proxy_key, status, latency, last_tested) VALUES (?, ?, ?, ?)",
        batch
    )
    db.commit()
    db.close()
    print(f"[✓] Updated proxy_cache DB: {len(alive)} OK entries")
    
    # Show top 20
    print(f"\n[*] Top 20 fastest proxies:")
    for i, (proxy, lat) in enumerate(alive[:20], 1):
        print(f"  {i:3}. {proxy} ({lat}ms)")

if __name__ == "__main__":
    asyncio.run(main())
