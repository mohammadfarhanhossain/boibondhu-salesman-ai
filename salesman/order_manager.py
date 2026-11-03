"""
BoiBondhu Cash-on-Delivery (COD) Order Manager
Handles customer orders placed directly inside the chat widget or website.
Saves to SQLite and integrates with B2B Merchant notifications.
"""

import os
import sqlite3
import re
import uuid
import random
from datetime import datetime
from typing import Dict, Any, List, Optional

ORDERS_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "orders.sqlite3"))


def init_orders_db():
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            merchant_id TEXT DEFAULT 'neutral',
            book_title TEXT NOT NULL,
            book_author TEXT DEFAULT '',
            price INTEGER DEFAULT 0,
            quantity INTEGER DEFAULT 1,
            delivery_fee INTEGER DEFAULT 60,
            total_amount INTEGER DEFAULT 0,
            customer_name TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            customer_address TEXT NOT NULL,
            district TEXT DEFAULT 'Dhaka',
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending'
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_merchant ON orders(merchant_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(customer_phone)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)")
    conn.commit()
    conn.close()


def validate_bd_phone(phone: str) -> bool:
    """Validates 11-digit Bangladeshi mobile numbers."""
    cleaned = re.sub(r"[^\d]", "", phone or "")
    if cleaned.startswith("88"):
        cleaned = cleaned[2:]
    return bool(re.match(r"^01[3-9]\d{8}$", cleaned))


def create_order(
    book_title: str,
    customer_name: str,
    customer_phone: str,
    customer_address: str,
    merchant_id: str = "neutral",
    book_author: str = "",
    price: int = 0,
    quantity: int = 1,
    delivery_fee: int = 60,
    district: str = "ঢাকা",
    notes: str = ""
) -> Dict[str, Any]:
    init_orders_db()

    name = customer_name.strip()
    if not name or len(name) < 2:
        return {"status": "error", "message": "দয়া করে সঠিক নাম লিখুন।"}

    phone = customer_phone.strip()
    if not validate_bd_phone(phone):
        return {"status": "error", "message": "দয়া করে সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন (যেমন: 017xxxxxxxx)।"}

    addr = customer_address.strip()
    if not addr or len(addr) < 5:
        return {"status": "error", "message": "দয়া করে আপনার সম্পূর্ণ ডেলিভারি ঠিকানা লিখুন।"}

    if not book_title or len(book_title.strip()) < 2:
        return {"status": "error", "message": "অর্ডার করার জন্য বইয়ের নাম আবশ্যক।"}

    price = max(0, int(price))
    quantity = max(1, int(quantity))
    total_amount = (price * quantity) + delivery_fee

    # Order ID format: #ORD-XXXXX
    rand_suffix = "".join(random.choices("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
    order_id = f"#ORD-{rand_suffix}"

    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (
            order_id, created_at, merchant_id, book_title, book_author,
            price, quantity, delivery_fee, total_amount, customer_name,
            customer_phone, customer_address, district, notes, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        merchant_id,
        book_title.strip(),
        book_author.strip(),
        price,
        quantity,
        delivery_fee,
        total_amount,
        name,
        phone,
        addr,
        district.strip() if district else "ঢাকা",
        notes.strip() if notes else "",
        "pending"
    ))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "order_id": order_id,
        "book_title": book_title,
        "customer_name": name,
        "customer_phone": phone,
        "delivery_fee": delivery_fee,
        "total_amount": total_amount,
        "delivery_timeline": "২-৩ কার্যদিবস",
        "message": f"🎉 ধন্যবাদ {name}! আপনার '{book_title}' বইটির অর্ডার নিশ্চিত হয়েছে (Order ID: {order_id})। ক্যাশ অন ডেলিভারিতে আগামী ২-৩ কার্যদিবসের মধ্যে আপনার ঠিকানায় পৌঁছে যাবে।"
    }


def get_orders(merchant_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    init_orders_db()
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if merchant_id and merchant_id != "all":
        cur.execute("SELECT * FROM orders WHERE merchant_id = ? ORDER BY created_at DESC LIMIT ?", (merchant_id, limit))
    else:
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_stats(merchant_id: Optional[str] = None) -> Dict[str, Any]:
    init_orders_db()
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()

    where_clause = "WHERE merchant_id = ?" if merchant_id and merchant_id != "all" else ""
    params = (merchant_id,) if merchant_id and merchant_id != "all" else ()

    cur.execute(f"SELECT count(*), coalesce(sum(total_amount), 0) FROM orders {where_clause}", params)
    total_orders, total_revenue = cur.fetchone()

    cur.execute(f"SELECT count(*) FROM orders {where_clause} {'AND' if where_clause else 'WHERE'} status = 'pending'", params)
    pending_orders = cur.fetchone()[0]

    cur.execute(f"SELECT count(*) FROM orders {where_clause} {'AND' if where_clause else 'WHERE'} status = 'confirmed'", params)
    confirmed_orders = cur.fetchone()[0]

    conn.close()
    return {
        "total_orders": total_orders or 0,
        "total_revenue": total_revenue or 0,
        "pending_orders": pending_orders or 0,
        "confirmed_orders": confirmed_orders or 0
    }
