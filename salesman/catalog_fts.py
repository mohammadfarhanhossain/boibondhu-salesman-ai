"""
BoiBondhu FTS5 (Full-Text Search) Engine & Typo-Tolerant Fuzzy Matcher
Searches 136,000+ books in SQLite FTS5 in 1-5 milliseconds with Bengali phonetic/typo correction.
"""

import os
import csv
import sqlite3
import time
import difflib
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "catalog_fts.sqlite3"))
CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_combined_catalog.csv"))

# In-memory caches for fast fuzzy lookups
_CACHED_AUTHORS: Optional[List[str]] = None
_CACHED_TITLES: Optional[List[str]] = None
_NORM_AUTHOR_MAP: Dict[str, str] = {}
_NORM_TITLE_MAP: Dict[str, str] = {}


def normalize_bangla_phonetic(text: str) -> str:
    """Normalize Bengali characters to handle common phonetic variants and typos."""
    if not text:
        return ""
    res = text.strip()
    # Sibilants
    res = res.replace("ষ", "শ").replace("স", "শ")
    # Flaps & Rs
    res = res.replace("ড়", "র").replace("ঢ়", "র")
    # Stops & Dentals
    res = res.replace("ৎ", "ত").replace("থ", "ত")
    res = res.replace("ধ", "দ")
    res = res.replace("ণ", "ন")
    # Vowel lengths
    res = res.replace("ী", "ি").replace("ূ", "ু")
    res = res.replace("ঐ", "ৈ").replace("ঔ", "ৌ")
    # Hasanta / Nukta
    res = res.replace("্", "").replace("়", "")
    return " ".join(res.split()).lower()


def _ensure_fuzzy_cache():
    global _CACHED_AUTHORS, _CACHED_TITLES, _NORM_AUTHOR_MAP, _NORM_TITLE_MAP
    if _CACHED_AUTHORS is not None and _CACHED_TITLES is not None:
        return

    if not os.path.exists(DB_PATH):
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Load distinct authors
        cur.execute("SELECT DISTINCT author_name FROM books WHERE author_name != '' AND author_name != 'Unknown Author'")
        authors = [r[0].strip() for r in cur.fetchall() if len(r[0].strip()) > 2]
        _CACHED_AUTHORS = authors
        _NORM_AUTHOR_MAP = {normalize_bangla_phonetic(a): a for a in authors}

        # Load popular / distinct titles (books with price or top 25,000)
        cur.execute("SELECT DISTINCT book_name FROM books WHERE book_name != '' AND book_name != 'Unknown Book' ORDER BY price DESC LIMIT 30000")
        titles = [r[0].strip() for r in cur.fetchall() if len(r[0].strip()) > 2]
        _CACHED_TITLES = titles
        _NORM_TITLE_MAP = {normalize_bangla_phonetic(t): t for t in titles}

        conn.close()
    except Exception as e:
        print(f"[CatalogFTS] Error loading fuzzy cache: {e}")
        _CACHED_AUTHORS = []
        _CACHED_TITLES = []


def find_fuzzy_correction(term: str) -> Optional[Tuple[str, str, float]]:
    """
    Checks if a term is a misspelled author or book title.
    Returns (matched_type, corrected_term, similarity_ratio) or None.
    """
    _ensure_fuzzy_cache()
    if not term or len(term.strip()) < 3:
        return None

    raw_clean = term.strip()
    norm_t = normalize_bangla_phonetic(raw_clean)

    # 1. Check phonetic dictionary hit directly
    if norm_t in _NORM_AUTHOR_MAP:
        orig = _NORM_AUTHOR_MAP[norm_t]
        if orig.lower() != raw_clean.lower():
            return ("author", orig, 0.95)

    if norm_t in _NORM_TITLE_MAP:
        orig = _NORM_TITLE_MAP[norm_t]
        if orig.lower() != raw_clean.lower():
            return ("title", orig, 0.95)

    # 2. Check difflib similarity on authors
    norm_auth_keys = list(_NORM_AUTHOR_MAP.keys())
    close_authors = difflib.get_close_matches(norm_t, norm_auth_keys, n=1, cutoff=0.65)
    if close_authors:
        best_key = close_authors[0]
        ratio = difflib.SequenceMatcher(None, norm_t, best_key).ratio()
        return ("author", _NORM_AUTHOR_MAP[best_key], ratio)

    # 3. Check difflib similarity on book titles
    norm_title_keys = list(_NORM_TITLE_MAP.keys())
    close_titles = difflib.get_close_matches(norm_t, norm_title_keys, n=1, cutoff=0.68)
    if close_titles:
        best_key = close_titles[0]
        ratio = difflib.SequenceMatcher(None, norm_t, best_key).ratio()
        return ("title", _NORM_TITLE_MAP[best_key], ratio)

    return None


def search_fts(query: str, limit: int = 5, author_filter: str = None, publisher_filter: str = None, max_price: int = None, operator: str = "AND") -> List[Dict[str, Any]]:
    """Fast FTS5 search across book title, author, publisher, and subjects."""
    if not os.path.exists(DB_PATH):
        return []

    raw_tokens = [t.strip().replace('"', '') for t in query.split() if len(t.strip()) > 0 and t.upper() != "OR" and t.upper() != "AND"]
    if not raw_tokens:
        return []

    fts_terms = [f'"{t}"*' for t in raw_tokens]
    fts_expr = f" {operator} ".join(fts_terms)

    norm_query = normalize_bangla_phonetic(query)
    norm_tokens = [t.strip().replace('"', '') for t in norm_query.split() if len(t.strip()) > 0 and t.upper() != "OR" and t.upper() != "AND"]
    if norm_tokens:
        norm_expr = f" {operator} ".join([f'"{t}"*' for t in norm_tokens])
        fts_expr = f"({fts_expr}) OR ({norm_expr})"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = """
        SELECT b.id, b.book_name AS title, b.author_name AS author, b.publisher_name AS publisher,
               b.subject_name AS subject, b.price, b.image_url, bm25(books_fts) AS rank
        FROM books_fts f
        JOIN books b ON b.id = f.rowid
        WHERE books_fts MATCH ?
    """
    params = [fts_expr]

    if author_filter:
        sql += " AND (b.author_name LIKE ? OR b.norm_author LIKE ?)"
        norm_a = normalize_bangla_phonetic(author_filter)
        params.extend([f"%{author_filter}%", f"%{norm_a}%"])

    if publisher_filter:
        sql += " AND (b.publisher_name LIKE ? OR b.norm_publisher LIKE ?)"
        norm_p = normalize_bangla_phonetic(publisher_filter)
        params.extend([f"%{publisher_filter}%", f"%{norm_p}%"])

    if max_price:
        sql += " AND b.price > 0 AND b.price <= ?"
        params.append(max_price)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    results = []
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
        results = [dict(r) for r in rows]
    except Exception as e:
        print(f"[CatalogFTS] Query error for '{fts_expr}': {e}")
        results = []
    finally:
        conn.close()

    return results


def search_fts_smart(query: str, limit: int = 5, author_filter: str = None, publisher_filter: str = None, max_price: int = None) -> Dict[str, Any]:
    """
    FTS search with token fallback and automatic Typo Tolerance / Fuzzy Correction.
    """
    # 1. Try direct full query FTS search (AND)
    results = search_fts(query, limit=limit, author_filter=author_filter, publisher_filter=publisher_filter, max_price=max_price, operator="AND")
    if results:
        return {
            "books": results,
            "corrected": False,
            "original_query": query,
            "corrected_query": query,
            "correction_type": None
        }

    # 2. If multi-token, try searching with OR operator
    words = [w.strip() for w in query.split() if len(w.strip()) > 2 and w.upper() not in ("OR", "AND")]
    if len(words) > 1:
        or_results = search_fts(" ".join(words), limit=limit, author_filter=author_filter, publisher_filter=publisher_filter, max_price=max_price, operator="OR")
        if or_results:
            return {
                "books": or_results,
                "corrected": False,
                "original_query": query,
                "corrected_query": query,
                "correction_type": "token_match"
            }

    # 3. Check for fuzzy typo correction on individual words or full query
    correction = find_fuzzy_correction(query)
    if not correction and words:
        for w in words:
            c = find_fuzzy_correction(w)
            if c:
                correction = c
                break

    if correction:
        c_type, corrected_term, ratio = correction
        if c_type == "author":
            fuzzy_results = search_fts(corrected_term, limit=limit, author_filter=corrected_term, publisher_filter=publisher_filter, max_price=max_price)
            if not fuzzy_results:
                fuzzy_results = search_fts(corrected_term, limit=limit)
        else:
            fuzzy_results = search_fts(corrected_term, limit=limit, publisher_filter=publisher_filter, max_price=max_price)

        if fuzzy_results:
            return {
                "books": fuzzy_results,
                "corrected": True,
                "original_query": query,
                "corrected_query": corrected_term,
                "correction_type": c_type,
                "confidence": round(ratio, 2)
            }

    return {
        "books": [],
        "corrected": False,
        "original_query": query,
        "corrected_query": query,
        "correction_type": None
    }


if __name__ == "__main__":
    test_queries = ["হূমায়ুন", "পারমানবিক অভ্যাস", "ঝংকার মাহাবুব", "হতাশা কাটানোর বই"]
    for q in test_queries:
        out = search_fts_smart(q, limit=2)
        print(f"\nQuery: '{q}' -> Corrected: {out['corrected']} ({out['corrected_query']})")
        for b in out["books"]:
            print(f"  * {b['title']} by {b['author']} (Tk. {b['price']})")
