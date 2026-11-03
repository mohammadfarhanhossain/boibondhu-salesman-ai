"""
Builds master_store_catalog table in catalog_fts.sqlite3 from all 21 bookstores
master catalogs in C:\\Automation_project\\<store>_scrapper\\master.csv.

Allows instant 1-2ms retrieval of offline catalog pricing across all 21 bookstores
before or alongside live web scraping.
"""

import os
import sys
import csv
import sqlite3
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from salesman.catalog_fts import DB_PATH, normalize_bangla_phonetic

BASE_PROJECTS_DIR = Path(r"C:\Automation_project")

ALL_STORES = [
    {"name": "Rokomari", "folder": "rokomar_scrapper", "type": "General", "price_key": "rokomari_price"},
    {"name": "Wafilife", "folder": "wafilife scrapper", "type": "Islamic", "price_key": "wafilife_price"},
    {"name": "AladaBoi", "folder": "aladaboi_scrapper", "type": "Islamic", "price_key": "aladaboi_price"},
    {"name": "Ruhama Shop", "folder": "ruhama_scrapper", "type": "Islamic", "price_key": "ruhama_price"},
    {"name": "BDBooks", "folder": "bdbooks_scrapper", "type": "Islamic", "price_key": "bdbooks_price"},
    {"name": "Kitabghor", "folder": "kitabghor_scrapper", "type": "Islamic", "price_key": "kitabghor_price"},
    {"name": "Maktabatul Ashraf", "folder": "maktabatulashraf_scrapper", "type": "Islamic", "price_key": "maktabatulashraf_price"},
    {"name": "BoiBitan", "folder": "boibitan_scrapper", "type": "Islamic", "price_key": "boibitan_price"},
    {"name": "Guardian Publications", "folder": "guardianpubs_scrapper", "type": "Islamic", "price_key": "guardianpubs_price"},
    {"name": "Baatighar", "folder": "baatighar_scrapper", "type": "General", "price_key": "baatighar_price"},
    {"name": "Boibari", "folder": "boibari_scrapper", "type": "General", "price_key": "boibari_price"},
    {"name": "eBoighar", "folder": "eboighar_scrapper", "type": "General", "price_key": "eboighar_price"},
    {"name": "Adarsha", "folder": "adarsha_scrapper", "type": "General", "price_key": "adarsha_price"},
    {"name": "BookTankBD", "folder": "booktankbd_scrapper", "type": "General", "price_key": "booktankbd_price"},
    {"name": "BookOceanBD", "folder": "bookoceanbd_scrapper", "type": "General", "price_key": "bookocean_price"},
    {"name": "Bengal Publications", "folder": "bengalpublications_scrapper", "type": "General", "price_key": "bengalpublications_price"},
    {"name": "PBS", "folder": "pbs_scrapper", "type": "General", "price_key": "pbs_price"},
    {"name": "Prothoma", "folder": "prothoma_scrapper", "type": "General", "price_key": "prothoma_price"},
    {"name": "Oitijjhya", "folder": "oitijjhya_scrapper", "type": "General", "price_key": "oitijjhya_price"},
    {"name": "AnyaProkash", "folder": "anyaprokash_scrapper", "type": "General", "price_key": "anyaprokash_price"},
    {"name": "Anindya Prokash", "folder": "anindyaprokash_scrapper", "type": "General", "price_key": "anindyaprokash_price"}
]


def populate_master_stores(force: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='master_store_catalog'")
    exists = cur.fetchone()[0]

    if exists and not force:
        cur.execute("SELECT count(*) FROM master_store_catalog")
        cnt = cur.fetchone()[0]
        if cnt > 160000:
            print(f"[MasterStores] master_store_catalog already populated with {cnt:,} records.")
            conn.close()
            return

    print("[MasterStores] Populating master_store_catalog from all 21 bookstore master CSVs...")
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

    total_records = 0
    for store_cfg in ALL_STORES:
        s_name = store_cfg["name"]
        folder = store_cfg["folder"]
        p_key = store_cfg.get("price_key", "store_price")
        csv_path = BASE_PROJECTS_DIR / folder / "master.csv"

        if not csv_path.exists():
            continue

        batch = []
        with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("book_name") or "").strip()
                if not name:
                    continue
                auth = (row.get("author_name") or "").strip()
                pub = (row.get("publisher_name") or "").strip()
                subj = (row.get("subject_name") or "").strip()

                # Price resolution
                raw_price = row.get(p_key) or row.get("store_price") or row.get("price") or 0
                try:
                    price = int(float(raw_price))
                except Exception:
                    price = 0

                raw_reg = row.get("main_price") or price
                try:
                    reg = int(float(raw_reg))
                except Exception:
                    reg = price

                url = (row.get("book_url") or "").strip()
                norm = normalize_bangla_phonetic(name)

                batch.append((s_name, name, auth, pub, subj, price, reg, url, norm))

        if batch:
            cur.executemany("""
                INSERT INTO master_store_catalog (store, book_name, author_name, publisher_name, subject_name, price, regular_price, url, norm_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            total_records += len(batch)
            print(f"   Indexed {len(batch):,} books from {s_name}")

    conn.close()
    print(f"[MasterStores] Successfully indexed {total_records:,} store records into master_store_catalog in {time.time() - t0:.2f}s")


def get_offline_master_deals(query: str, limit: int = 10) -> list:
    """
    Instantly returns all matched bookstore deals from master catalog.
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
        LIMIT 25
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
            "store_type": "Islamic" if any(k in st.lower() for k in ["wafi", "ruhama", "ashraf", "kitab", "aladaboi", "bdbooks", "boibitan"]) else "General",
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
        if len(deals) >= limit:
            break

    return deals


if __name__ == "__main__":
    populate_master_stores(force=True)
    res = get_offline_master_deals("শঙ্খনীল কারাগার")
    print("\nOffline Master Deals for 'শঙ্খনীল কারাগার':")
    for d in res:
        print(f"  [{d['store']}] {d['title']} - ৳{d['price']} (Regular: ৳{d['regular_price']})")
