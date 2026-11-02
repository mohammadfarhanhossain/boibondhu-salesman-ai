import os
import re
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "book_images.sqlite3")
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
}

_MEM_CACHE = {}

def normalize_key(val):
    if not val:
        return ""
    val = str(val).lower().strip()
    val = val.replace("ী", "ি").replace("ূ", "ু").replace("ণ", "ন").replace("শ", "স").replace("ষ", "স")
    val = re.sub(r"[^\w\s\u0980-\u09FF]", " ", val)
    return " ".join(val.split())

def init_image_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS book_covers (
                    title_norm TEXT PRIMARY KEY,
                    image_url TEXT,
                    updated_at REAL
                )
            """)
    except Exception as e:
        print(f"[CoverResolver] DB init error: {e}")

def get_cached_image(title):
    norm = normalize_key(title)
    if not norm:
        return None
    if norm in _MEM_CACHE:
        return _MEM_CACHE[norm]
    try:
        init_image_db()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT image_url FROM book_covers WHERE title_norm = ?", (norm,)).fetchone()
            if row and row[0]:
                _MEM_CACHE[norm] = row[0]
                return row[0]
    except Exception:
        pass
    return None

def set_cached_image(title, url):
    if not url or 'placeholder' in url:
        return
    norm = normalize_key(title)
    if not norm:
        return
    _MEM_CACHE[norm] = url
    try:
        init_image_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO book_covers VALUES (?, ?, ?)", (norm, url, time.time()))
    except Exception:
        pass

def fetch_cover_wafilife(title):
    try:
        url = f"https://www.wafilife.com/api/search?keyword={quote(title)}"
        r = requests.get(url, headers={**HEADERS, 'Referer': 'https://www.wafilife.com/'}, timeout=2.2)
        if r.status_code == 200:
            for it in r.json().get('items', []):
                img = it.get('image', {}).get('original') or it.get('image', {}).get('thumbnail')
                if img and 'placeholder' not in img and ('http://' in img or 'https://' in img):
                    return img
    except Exception:
        pass
    return None

def fetch_cover_rokomari(title):
    try:
        url = f"https://www.rokomari.com/search?term={quote(title)}&search_type=ALL"
        r = requests.get(url, headers=HEADERS, timeout=2.5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            card = soup.find('div', class_=lambda c: c and 'productGridItem' in c)
            if card:
                img = card.find('img')
                if img:
                    src = img.get('data-src') or img.get('src') or ""
                    if src and ('http://' in src or 'https://' in src):
                        return src
    except Exception:
        pass
    return None

def resolve_book_cover(title):
    if not title:
        return ""
    cached = get_cached_image(title)
    if cached:
        return cached

    # Query Wafilife first (fast JSON API), fallback to Rokomari
    img = fetch_cover_wafilife(title)
    if not img:
        img = fetch_cover_rokomari(title)

    if img:
        set_cached_image(title, img)
        return img
    return ""

def resolve_covers_for_books(books, max_workers=4, timeout=2.5):
    """
    Enriches a list of book dictionaries with real cover images in parallel.
    Skips books that already have a valid image.
    """
    if not books:
        return books

    missing_indices = []
    for idx, b in enumerate(books):
        img = b.get('image') or b.get('image_url') or ""
        if not img or not ('http://' in str(img) or 'https://' in str(img)):
            missing_indices.append(idx)

    if not missing_indices:
        return books

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(resolve_book_cover, books[i].get('title') or books[i].get('book_name') or ""): i
            for i in missing_indices
        }
        for future in as_completed(future_to_idx, timeout=timeout):
            idx = future_to_idx[future]
            try:
                img_url = future.result()
                if img_url:
                    books[idx]['image'] = img_url
                    books[idx]['image_url'] = img_url
            except Exception:
                pass

    return books

# Initialize DB on module import
init_image_db()
