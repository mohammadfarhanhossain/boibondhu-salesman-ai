"""
BoiBondhu B2B SaaS Analytics & Business Intelligence Engine
Tracks customer demand, lost sales opportunities, peak hours, and order conversions.
"""

import os
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

ANALYTICS_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "analytics.sqlite3"))


def init_analytics_db():
    conn = sqlite3.connect(ANALYTICS_DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            merchant_id TEXT DEFAULT 'neutral',
            query TEXT NOT NULL,
            category TEXT DEFAULT '',
            books_found INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lost_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            merchant_id TEXT DEFAULT 'neutral',
            book_query TEXT NOT NULL,
            reason TEXT DEFAULT 'not_in_catalog'  -- 'not_in_catalog', 'out_of_stock'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            merchant_id TEXT DEFAULT 'neutral',
            session_id TEXT DEFAULT '',
            user_message TEXT NOT NULL
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_se_merchant ON search_events(merchant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_se_time ON search_events(timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_merchant ON lost_sales(merchant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ls_book ON lost_sales(book_query)")

    conn.commit()
    conn.close()


def track_search(query: str, merchant_id: str = "neutral", category: str = "", books_found: int = 0):
    init_analytics_db()
    if not query or len(query.strip()) < 2:
        return
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO search_events (timestamp, merchant_id, query, category, books_found)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), merchant_id, query.strip()[:100], category[:50], books_found))

        if books_found == 0:
            cur.execute("""
                INSERT INTO lost_sales (timestamp, merchant_id, book_query, reason)
                VALUES (?, ?, ?, 'not_in_catalog')
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), merchant_id, query.strip()[:100]))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Analytics] Error tracking search: {e}")


def track_lost_sale(book_query: str, merchant_id: str = "neutral", reason: str = "out_of_stock"):
    init_analytics_db()
    if not book_query:
        return
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lost_sales (timestamp, merchant_id, book_query, reason)
            VALUES (?, ?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), merchant_id, book_query.strip()[:100], reason))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Analytics] Error tracking lost sale: {e}")


def track_chat_message(message: str, merchant_id: str = "neutral", session_id: str = ""):
    init_analytics_db()
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_events (timestamp, merchant_id, session_id, user_message)
            VALUES (?, ?, ?, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), merchant_id, session_id, message.strip()[:150]))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Analytics] Error tracking chat: {e}")


def get_analytics_summary(merchant_id: Optional[str] = None) -> Dict[str, Any]:
    init_analytics_db()
    conn = sqlite3.connect(ANALYTICS_DB)
    cur = conn.cursor()

    where_m = "WHERE merchant_id = ?" if merchant_id and merchant_id != "all" else ""
    params = (merchant_id,) if merchant_id and merchant_id != "all" else ()

    # Total searches
    cur.execute(f"SELECT count(*) FROM search_events {where_m}", params)
    total_searches = cur.fetchone()[0]

    # Total chats
    cur.execute(f"SELECT count(*) FROM chat_events {where_m}", params)
    total_chats = cur.fetchone()[0]

    # Top searched queries
    cur.execute(f"""
        SELECT query, count(*) as cnt
        FROM search_events {where_m}
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT 10
    """, params)
    top_searches = [{"query": r[0], "count": r[1]} for r in cur.fetchall()]

    # Lost Sales Opportunities
    cur.execute(f"""
        SELECT book_query, count(*) as cnt, reason
        FROM lost_sales {where_m}
        GROUP BY book_query
        ORDER BY cnt DESC
        LIMIT 10
    """, params)
    lost_sales = [{"book": r[0], "count": r[1], "reason": r[2]} for r in cur.fetchall()]

    # Categories breakdown
    cur.execute(f"""
        SELECT category, count(*) as cnt
        FROM search_events {where_m} {'AND' if where_m else 'WHERE'} category != ''
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 6
    """, params)
    categories = [{"category": r[0], "count": r[1]} for r in cur.fetchall()]

    conn.close()

    return {
        "total_searches": total_searches,
        "total_chats": total_chats,
        "top_searches": top_searches,
        "lost_sales": lost_sales,
        "categories": categories
    }
