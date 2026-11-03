"""
Builds master_store_catalog table in catalog_fts.sqlite3 from:
1. C:\\Automation_project\\wafilife scrapper\\master.csv
2. C:\\Automation_project\\rokomar_scrapper\\master.csv

Allows instant 1-2ms retrieval of offline Rokomari & Wafilife catalog pricing
before or alongside live web scraping.
"""

import os
import sys
import csv
import sqlite3
import time
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from salesman.catalog_fts import DB_PATH, normalize_bangla_phonetic

WAFILIFE_CSV = r"C:\Automation_project\wafilife scrapper\master.csv"
ROKOMARI_CSV = r"C:\Automation_project\rokomar_scrapper\master.csv"


def populate_master_stores(force: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='master_store_catalog'")
    exists = cur.fetchone()[0]

    if exists and not force:
        cur.execute("SELECT count(*) FROM master_store_catalog")
        cnt = cur.fetchone()[0]
        if cnt > 5000:
            print(f"[MasterStores] master_store_catalog already populated with {cnt:,} records.")
            conn.close()
            return

    print("[MasterStores] Populating master_store_catalog from Rokomari and Wafilife master CSVs...")
    t0 = time.time()

    cur.execute("DROP TABLE IF EXISTS master_store_catalog")
    cur.execute("""
        CREATE TABLE master_store_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store TEXT NOT NULL,
            book_name TEXT NOT NULL,
            author_name TEXT,
            publisher_name TEXT,
            subject_name TEXT,
            price INTEGER DEFAULT 0,
            regular_price INTEGER DEFAULT 0,
            url TEXT,
            norm_name TEXT
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_msc_norm ON master_store_catalog(norm_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_msc_store ON master_store_catalog(store)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_msc_book ON master_store_catalog(book_name)")

    # 1. Ingest Wafilife
    w_batch = []
    if os.path.exists(WAFILIFE_CSV):
        with open(WAFILIFE_CSV, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("book_name") or "").strip()
                if not name:
                    continue
                auth = (row.get("author_name") or "").strip()
                pub = (row.get("publisher_name") or "").strip()
                subj = (row.get("subject_name") or "").strip()
                try:
                    price = int(float(row.get("wafilife_price") or 0))
                except Exception:
                    price = 0
                try:
                    reg = int(float(row.get("main_price") or price))
                except Exception:
                    reg = price
                url = f"https://www.wafilife.com/?s={urllib.parse.quote(name)}&post_type=product"
                norm = normalize_bangla_phonetic(name)
                w_batch.append(("Wafilife", name, auth, pub, subj, price, reg, url, norm))
                if len(w_batch) >= 10000:
                    cur.executemany("""
                        INSERT INTO master_store_catalog (store, book_name, author_name, publisher_name, subject_name, price, regular_price, url, norm_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, w_batch)
                    conn.commit()
                    w_batch = []

            if w_batch:
                cur.executemany("""
                    INSERT INTO master_store_catalog (store, book_name, author_name, publisher_name, subject_name, price, regular_price, url, norm_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, w_batch)
                conn.commit()

    # 2. Ingest Rokomari
    r_batch = []
    if os.path.exists(ROKOMARI_CSV):
        with open(ROKOMARI_CSV, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("book_name") or "").strip()
                if not name:
                    continue
                auth = (row.get("author_name") or "").strip()
                pub = (row.get("publisher_name") or "").strip()
                try:
                    price = int(float(row.get("rokomari_price") or 0))
                except Exception:
                    price = 0
                try:
                    reg = int(float(row.get("main_price") or price))
                except Exception:
                    reg = price
                url = (row.get("book_url") or "").strip()
                if not url:
                    url = f"https://www.rokomari.com/search?term={urllib.parse.quote(name)}"
                norm = normalize_bangla_phonetic(name)
                r_batch.append(("Rokomari", name, auth, pub, "সাধারণ বই", price, reg, url, norm))
                if len(r_batch) >= 10000:
                    cur.executemany("""
                        INSERT INTO master_store_catalog (store, book_name, author_name, publisher_name, subject_name, price, regular_price, url, norm_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, r_batch)
                    conn.commit()
                    r_batch = []

            if r_batch:
                cur.executemany("""
                    INSERT INTO master_store_catalog (store, book_name, author_name, publisher_name, subject_name, price, regular_price, url, norm_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, r_batch)
                conn.commit()

    cur.execute("SELECT count(*) FROM master_store_catalog")
    total = cur.fetchone()[0]
    conn.close()
    print(f"[MasterStores] Successfully indexed {total:,} store records into master_store_catalog in {time.time() - t0:.2f}s")


def get_offline_master_deals(query: str) -> list:
    """
    Instantly returns Rokomari and Wafilife pricing and metadata from master catalog.
    Runs in 1-2 milliseconds.
    """
    if not query:
        return []

    norm_q = normalize_bangla_phonetic(query)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT store, book_name, author_name, publisher_name, subject_name, price, regular_price, url
        FROM master_store_catalog
        WHERE norm_name = ? OR norm_name LIKE ? OR book_name LIKE ?
        ORDER BY (price > 0) DESC, price ASC
        LIMIT 6
    """, (norm_q, f"%{norm_q}%", f"%{query.strip()}%"))

    rows = cur.fetchall()
    conn.close()

    deals = []
    seen_stores = set()
    for r in rows:
        st = r["store"]
        if st in seen_stores:
            continue
        seen_stores.add(st)
        deals.append({
            "store": st,
            "store_type": "Islamic" if st == "Wafilife" else "General",
            "title": r["book_name"],
            "author": r["author_name"],
            "publisher": r["publisher_name"],
            "subject": r["subject_name"],
            "price": r["price"],
            "regular_price": r["regular_price"],
            "in_stock": True,
            "stock_text": "স্টকে আছে (ক্যাটালগ)",
            "url": r["url"],
            "image": "",
            "match_score": 100,
            "is_catalog_fast": True
        })

    return deals


if __name__ == "__main__":
    populate_master_stores()
    res = get_offline_master_deals("শঙ্খনীল কারাগার")
    print("Offline Master Deals for 'শঙ্খনীল কারাগার':", res)
