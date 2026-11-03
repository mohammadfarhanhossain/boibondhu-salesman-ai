import os
import sys
import json
import sqlite3
import time
from flask import Flask, request, jsonify, render_template_string, Response
from comparator_engine import compare_books, stream_compare_books, STORE_REGISTRY
from salesman.salesman_engine import salesman_agent
from salesman.merchant_registry import get_merchant, list_merchants, register_custom_merchant
from cover_resolver import resolve_book_cover, resolve_covers_for_books, set_cached_image
from salesman.order_manager import create_order, get_orders, get_order_stats
from salesman.analytics_tracker import track_search, track_chat_message, track_lost_sale, get_analytics_summary

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

app = Flask(__name__)

CACHE_DB = os.path.join(os.path.dirname(__file__), "book_cache.sqlite3")
CACHE_TTL = 3600  # 1 hour (Optimized for 10-100 concurrent users)


def init_cache():
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multi_store_cache (
                cache_key TEXT PRIMARY KEY,
                created_at REAL,
                data TEXT
            )
        """)


def get_cached(key):
    try:
        init_cache()
        with sqlite3.connect(CACHE_DB) as conn:
            row = conn.execute(
                "SELECT created_at, data FROM multi_store_cache WHERE cache_key = ?",
                (key,)
            ).fetchone()
        if row and (time.time() - row[0] < CACHE_TTL):
            return json.loads(row[1])
    except Exception as e:
        print(f"Cache get error: {e}")
    return None


def set_cached(key, data):
    try:
        init_cache()
        with sqlite3.connect(CACHE_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO multi_store_cache VALUES (?, ?, ?)",
                (key, time.time(), json.dumps(data, ensure_ascii=False))
            )
    except Exception as e:
        print(f"Cache set error: {e}")


# ==============================================================================
# HTML TEMPLATE
# ==============================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>বইবন্ধু ডট কম | বাংলাদেশের বৃহত্তম অনলাইন বইয়ের মার্কেটপ্লেস ও প্রাইজ কম্প্যারিজন</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --wafi-green: #008060;
  --wafi-green-dark: #005a36;
  --wafi-green-light: #e6f7f2;
  --wafi-orange: #ea580c;
  --wafi-yellow: #f59e0b;
  --dark-text: #1e293b;
  --muted-text: #64748b;
  --light-bg: #f8fafc;
  --card-bg: #ffffff;
  --border: #e2e8f0;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  --shadow-lg: 0 10px 25px rgba(0,0,0,0.12);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Hind Siliguri', sans-serif;
  background: var(--light-bg);
  color: var(--dark-text);
  line-height: 1.6;
}

a { color: inherit; text-decoration: none; }

/* 1. TOP ANNOUNCEMENT BAR */
.top-bar {
  background: var(--wafi-green-dark);
  color: #ffffff;
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.top-bar-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.top-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.top-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.top-right a:hover {
  text-decoration: underline;
}

/* 2. MAIN HEADER */
.main-header {
  background: #ffffff;
  border-bottom: 1px solid var(--border);
  padding: 14px 0;
  position: sticky;
  top: 0;
  z-index: 90;
  box-shadow: var(--shadow-sm);
}
.header-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}
.logo-icon {
  font-size: 32px;
}
.brand-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--wafi-green);
  line-height: 1.1;
  display: block;
}
.brand-domain {
  color: var(--wafi-orange);
}
.brand-tag {
  font-size: 11px;
  color: var(--muted-text);
  display: block;
}

/* MEGA SEARCH BAR */
.mega-search-form {
  flex: 1;
  max-width: 620px;
  display: flex;
  align-items: center;
  border: 2px solid var(--wafi-green);
  border-radius: 8px;
  overflow: hidden;
  background: #ffffff;
}
.search-category-select {
  padding: 10px 14px;
  border: none;
  background: #f1f5f9;
  font-family: inherit;
  font-size: 13px;
  color: var(--dark-text);
  border-right: 1px solid var(--border);
  outline: none;
  cursor: pointer;
}
.search-input-wrap {
  flex: 1;
  display: flex;
  position: relative;
}
.search-input {
  width: 100%;
  padding: 10px 14px;
  border: none;
  outline: none;
  font-family: inherit;
  font-size: 14px;
}
.search-btn {
  background: var(--wafi-green);
  color: #ffffff;
  border: none;
  padding: 0 20px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s;
}
.search-btn:hover {
  background: var(--wafi-green-dark);
}

/* HEADER ICONS */
.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  padding: 6px 10px;
  border-radius: 6px;
  transition: background 0.2s;
}
.header-action-btn:hover {
  background: #f1f5f9;
}
.header-action-btn .icon {
  font-size: 18px;
}
.cart-btn .badge {
  background: var(--wafi-orange);
  color: white;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  font-weight: 700;
}

/* 3. SUB NAV MENU BAR */
.sub-nav {
  background: #0f172a;
  color: #f8fafc;
}
.sub-nav-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
  align-items: center;
  overflow-x: auto;
  white-space: nowrap;
}
.nav-item {
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s, color 0.2s;
  border-bottom: 2px solid transparent;
}
.nav-item:hover, .nav-item.active {
  background: rgba(255,255,255,0.08);
  border-bottom-color: var(--wafi-green);
  color: #ffffff;
}

/* 4. HERO PROMOTIONAL BANNER */
.hero-section {
  max-width: 1240px;
  margin: 16px auto;
  padding: 0 16px;
}
.hero-banner {
  background: linear-gradient(135deg, #065f46 0%, #047857 50%, #0f172a 100%);
  color: #ffffff;
  border-radius: 12px;
  padding: 32px 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: var(--shadow-md);
  position: relative;
  overflow: hidden;
}
.hero-banner::after {
  content: "📚";
  position: absolute;
  right: -20px;
  bottom: -30px;
  font-size: 180px;
  opacity: 0.12;
  pointer-events: none;
}
.hero-content {
  max-width: 680px;
  z-index: 1;
}
.hero-pill {
  display: inline-block;
  background: rgba(255,255,255,0.18);
  backdrop-filter: blur(4px);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 12px;
  border: 1px solid rgba(255,255,255,0.25);
}
.hero-title {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.3;
  margin-bottom: 10px;
}
.hero-subtitle {
  font-size: 15px;
  opacity: 0.92;
  margin-bottom: 20px;
}
.hero-btns {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.hero-btn-primary {
  background: #ffffff;
  color: var(--wafi-green-dark);
  font-weight: 600;
  padding: 10px 22px;
  border-radius: 8px;
  font-size: 14px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.hero-btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.2);
}
.hero-btn-secondary {
  background: rgba(255,255,255,0.15);
  color: #ffffff;
  border: 1px solid rgba(255,255,255,0.3);
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
}

/* 5. BENEFITS BAR */
.benefits-bar {
  max-width: 1240px;
  margin: 16px auto;
  padding: 0 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 12px;
}
.benefit-item {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: var(--shadow-sm);
}
.benefit-icon {
  font-size: 26px;
}
.benefit-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--dark-text);
}
.benefit-desc {
  font-size: 12px;
  color: var(--muted-text);
}

/* 6. QUICK CATEGORY PILLS */
.category-pills {
  max-width: 1240px;
  margin: 12px auto;
  padding: 0 16px;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 6px;
}
.cat-pill {
  background: #ffffff;
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: all 0.2s;
  cursor: pointer;
}
.cat-pill:hover, .cat-pill.active {
  background: var(--wafi-green);
  color: #ffffff;
  border-color: var(--wafi-green);
}

/* 7. SHELVES & BOOK CARDS GRID */
.shelf-section {
  max-width: 1240px;
  margin: 24px auto;
  padding: 0 16px;
}
.shelf-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 8px;
}
.shelf-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--dark-text);
  display: flex;
  align-items: center;
  gap: 8px;
}
.shelf-link {
  font-size: 13px;
  color: var(--wafi-green);
  font-weight: 600;
}
.shelf-link:hover { text-decoration: underline; }

.books-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(185px, 1fr));
  gap: 16px;
}

/* WAFILIFE BOOK CARD */
.book-card {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.2s, box-shadow 0.2s;
  position: relative;
  cursor: pointer;
}
.book-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
  border-color: #cbd5e1;
}

.card-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: var(--wafi-orange);
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  z-index: 2;
}

.book-card-cover {
  width: 100%;
  height: 180px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}
.book-card-cover img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: transform 0.3s;
}
.book-card:hover .book-card-cover img {
  transform: scale(1.05);
}
.book-cover-placeholder {
  font-size: 50px;
  color: #cbd5e1;
}

.book-card-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.book-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--dark-text);
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  height: 38px;
}
.book-author {
  font-size: 12px;
  color: var(--muted-text);
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.book-rating {
  font-size: 11px;
  color: #f59e0b;
  margin-bottom: 6px;
}
.book-pricing {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: auto;
  margin-bottom: 10px;
}
.price-current {
  font-size: 17px;
  font-weight: 700;
  color: var(--wafi-green);
}
.price-regular {
  font-size: 13px;
  color: var(--muted-text);
  text-decoration: line-through;
}

.card-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.btn-compare {
  background: var(--wafi-green-light);
  color: var(--wafi-green-dark);
  border: 1px solid rgba(0,128,96,0.3);
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.btn-compare:hover {
  background: var(--wafi-green);
  color: #ffffff;
}
.btn-cod {
  background: #f1f5f9;
  color: var(--dark-text);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
}
.btn-cod:hover {
  background: #e2e8f0;
}

/* 8. SEARCH RESULTS VIEW (When query active) */
.search-results-section {
  max-width: 1240px;
  margin: 20px auto;
  padding: 0 16px;
}
.results-header-banner {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

/* 9. ON-CLICK COMPARISON MODAL POPUP */
.modal-overlay {
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(4px);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.modal-overlay.active {
  display: flex;
}
.modal-card {
  background: #ffffff;
  border-radius: 16px;
  width: 100%;
  max-width: 720px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
  animation: modalSlideUp 0.25s ease-out;
  position: relative;
}
@keyframes modalSlideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
.modal-close-btn {
  position: absolute;
  top: 14px;
  right: 14px;
  background: #f1f5f9;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.modal-close-btn:hover { background: #e2e8f0; }

.modal-book-header {
  padding: 20px 24px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 16px;
  align-items: center;
}
.modal-book-thumb {
  width: 80px;
  height: 105px;
  background: #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-book-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.modal-book-info h3 {
  font-size: 18px;
  color: var(--dark-text);
  margin-bottom: 4px;
}
.modal-book-info p {
  font-size: 13px;
  color: var(--muted-text);
  margin-bottom: 2px;
}

.modal-top3-section {
  padding: 20px 24px;
}
.modal-top3-title {
  font-size: 16px;
  font-weight: 700;
  color: #166534;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.top3-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.top3-deal-item {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  transition: all 0.2s;
}
.top3-deal-item.rank-1 {
  background: #f0fdf4;
  border-color: #86efac;
  box-shadow: 0 2px 8px rgba(34,197,94,0.15);
}
.deal-store-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}
.deal-rank-badge {
  font-size: 20px;
}
.deal-store-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--dark-text);
}
.deal-store-tag {
  font-size: 11px;
  padding: 2px 6px;
  background: #e2e8f0;
  border-radius: 4px;
  color: var(--muted-text);
}
.deal-pricing-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}
.deal-prices {
  text-align: right;
}
.deal-current-price {
  font-size: 18px;
  font-weight: 700;
  color: #166534;
}
.deal-savings {
  font-size: 11px;
  color: #dc2626;
  font-weight: 600;
}
.deal-btns {
  display: flex;
  gap: 6px;
}
.btn-modal-order {
  background: var(--wafi-green);
  color: #ffffff;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  cursor: pointer;
}
.btn-modal-order:hover { background: var(--wafi-green-dark); }
.btn-modal-link {
  background: #f1f5f9;
  color: var(--dark-text);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  border: 1px solid var(--border);
}

.modal-all-stores {
  padding: 0 24px 20px;
}
.all-stores-toggle {
  background: #f8fafc;
  border: 1px solid var(--border);
  width: 100%;
  padding: 8px;
  border-radius: 6px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted-text);
  cursor: pointer;
  text-align: center;
}

/* COD ORDER FORM MODAL */
.cod-form-wrap {
  padding: 20px 24px;
  background: #f8fafc;
  border-top: 1px solid var(--border);
}
.cod-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 10px;
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-family: inherit;
  font-size: 13px;
}
.btn-submit-order {
  grid-column: 1 / -1;
  background: #166534;
  color: white;
  border: none;
  padding: 10px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
}

/* 10. FOOTER */
.site-footer {
  background: #0f172a;
  color: #94a3b8;
  padding: 40px 0 20px;
  margin-top: 40px;
  font-size: 13px;
}
.footer-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 16px;
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1.5fr;
  gap: 30px;
}
.footer-col h4 {
  color: #ffffff;
  font-size: 15px;
  margin-bottom: 12px;
}
.footer-col ul { list-style: none; }
.footer-col li { margin-bottom: 8px; }
.footer-col a:hover { color: #ffffff; }
.footer-bottom {
  max-width: 1240px;
  margin: 30px auto 0;
  padding: 16px 16px 0;
  border-top: 1px solid #1e293b;
  text-align: center;
  font-size: 12px;
}

/* RESPONSIVE */
@media (max-width: 768px) {
  .header-inner { flex-direction: column; align-items: stretch; }
  .mega-search-form { max-width: 100%; }
  .header-actions { justify-content: space-around; }
  .hero-banner { padding: 20px; }
  .hero-title { font-size: 20px; }
  .footer-inner { grid-template-columns: 1fr; }
  .cod-form-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- 1. TOP ANNOUNCEMENT BAR -->
<div class="top-bar">
  <div class="top-bar-inner">
    <div class="top-left">
      <span>📞 হেল্পলাইন: ০৯৬৩৮-০০১১২২</span>
      <span>🚚 সারাদেশে ক্যাশ অন ডেলিভারি</span>
      <span>⚡ ২১টি বুকশপের মধ্যে সর্বনিম্ন দামের নিশ্চয়তা!</span>
    </div>
    <div class="top-right">
      <a href="/demo">🤖 AI সেলসম্যান ডেমো</a>
      <a href="/merchant">🏪 মার্চেন্ট পোর্টাল</a>
      <a href="/admin/analytics">📈 অ্যানালিটিক্স</a>
    </div>
  </div>
</div>

<!-- 2. MAIN HEADER -->
<header class="main-header">
  <div class="header-inner">
    <a href="/" class="logo">
      <span class="logo-icon">📚</span>
      <div class="logo-text">
        <span class="brand-name">বইবন্ধু<span class="brand-domain">.com</span></span>
        <span class="brand-tag">বাংলাদেশের বৃহত্তম বইয়ের মার্কেটপ্লেস</span>
      </div>
    </a>

    <form action="/" method="GET" class="mega-search-form" id="searchForm">
      <select name="category" class="search-category-select">
        <option value="all">সকল বিষয়</option>
        <option value="islamic" {% if category == 'islamic' %}selected{% endif %}>ইসলামিক বই</option>
        <option value="general" {% if category == 'general' %}selected{% endif %}>উপন্যাস ও সাহিত্য</option>
      </select>
      <div class="search-input-wrap">
        <input type="text" name="q" id="searchInput" class="search-input" value="{{ query }}" placeholder="বইয়ের নাম, লেখক বা প্রকাশনী দিয়ে খুঁজুন (Banglish ও বাংলা)..." autocomplete="off">
        <button type="submit" class="search-btn">
          <span>🔍</span> <span>খুঁজুন</span>
        </button>
      </div>
    </form>

    <div class="header-actions">
      <a href="#" class="header-action-btn" onclick="alert('আপনার মোবাইল নম্বর দিয়ে সহজেই যে কোনো অর্ডার ট্র্যাক করতে পারবেন'); return false;">
        <span class="icon">📦</span>
        <span class="label">অর্ডার ট্র্যাক</span>
      </a>
      <a href="#" class="header-action-btn" onclick="alert('আপনার পছন্দের বই সংরক্ষিত রয়েছে'); return false;">
        <span class="icon">❤️</span>
        <span class="label">উইশলিস্ট</span>
      </a>
      <a href="#" class="header-action-btn cart-btn" onclick="alert('কার্টে বই যুক্ত করতে বইয়ের পাশে থাকা অর্ডার বাটনে চাপুন'); return false;">
        <span class="icon">🛒</span>
        <span class="label">কার্ট <span class="badge" id="cartCount">০</span></span>
      </a>
    </div>
  </div>
</header>

<!-- 3. SUB NAVIGATION BAR -->
<nav class="sub-nav">
  <div class="sub-nav-inner">
    <a href="/?category=all" class="nav-item active">📂 বিষয়সমূহ</a>
    <a href="/?q=হুমায়ূন আহমেদ" class="nav-item">✍️ হুমায়ূন আহমেদ</a>
    <a href="/?q=আরিফ আজাদ" class="nav-item">✍️ আরিফ আজাদ</a>
    <a href="/?category=islamic" class="nav-item">🕌 ইসলামিক বই</a>
    <a href="/?category=general" class="nav-item">📖 কথাসাহিত্য ও উপন্যাস</a>
    <a href="/?q=আত্মউন্নয়ন" class="nav-item">🎯 আত্মউন্নয়ন</a>
    <a href="/?q=প্রোগ্রামিং" class="nav-item">💻 প্রোগ্রামিং ও ক্যারিয়ার</a>
    <a href="/?q=অফার" class="nav-item">🏷️ বিশেষ ছাড়</a>
    <a href="/?q=বেস্টসেলার" class="nav-item">🏆 বেস্টসেলার</a>
  </div>
</nav>

{% if not query %}
<!-- 4. HERO SECTION (Wafilife Banner) -->
<section class="hero-section">
  <div class="hero-banner">
    <div class="hero-content">
      <span class="hero-pill">⚡ ২১টি বুকশপের বই এক ছাদের নিচে</span>
      <h1 class="hero-title">রকমারি, ওয়াফিলাইফ, বাতিঘর সহ সকল বুকশপের সেরা দাম এক ক্লিকেই!</h1>
      <p class="hero-subtitle">বাংলাদেশের যেকোনো বই খুঁজুন—আমরা ২১টি অনলাইন বুকশপে তাৎক্ষণিক দাম তুলনা করে আপনাকে সবচেয়ে কম দামে কেনার সুযোগ করে দেব।</p>
      <div class="hero-btns">
        <a href="#bestsellers" class="hero-btn-primary">🔥 বেস্টসেলার বইগুলো দেখুন</a>
        <a href="/?category=islamic" class="hero-btn-secondary">🕌 ইসলামিক বই সম্ভার</a>
      </div>
    </div>
  </div>
</section>

<!-- 5. BENEFITS BAR -->
<div class="benefits-bar">
  <div class="benefit-item">
    <span class="benefit-icon">⚡</span>
    <div>
      <div class="benefit-title">সর্বনিম্ন দামের নিশ্চয়তা</div>
      <div class="benefit-desc">২১টি বুকশপে রিয়েল-টাইম তুলনা</div>
    </div>
  </div>
  <div class="benefit-item">
    <span class="benefit-icon">🚚</span>
    <div>
      <div class="benefit-title">ক্যাশ অন ডেলিভারি</div>
      <div class="benefit-desc">সারা দেশে ঘরে বসে মূল্য পরিশোধ</div>
    </div>
  </div>
  <div class="benefit-item">
    <span class="benefit-icon">💯</span>
    <div>
      <div class="benefit-title">১০০% আসল বই</div>
      <div class="benefit-desc">সরাসরি অনুমোদিত প্রকাশনী থেকে</div>
    </div>
  </div>
  <div class="benefit-item">
    <span class="benefit-icon">🤖</span>
    <div>
      <div class="benefit-title">বইবন্ধু AI গাইড</div>
      <div class="benefit-desc">চাহিদা অনুযায়ী সেরা বইয়ের পরামর্শ</div>
    </div>
  </div>
</div>

<!-- 6. CATEGORY QUICK PILLS -->
<div class="category-pills">
  <a href="/" class="cat-pill active">সকল বই</a>
  <a href="/?category=islamic" class="cat-pill">🕌 ইসলামিক বই</a>
  <a href="/?q=উপন্যাস" class="cat-pill">📖 উপন্যাস ও গল্প</a>
  <a href="/?q=আত্মউন্নয়ন" class="cat-pill">🎯 মোটিভেশন ও আত্মউন্নয়ন</a>
  <a href="/?q=প্রোগ্রামিং" class="cat-pill">💻 কোডিং ও সফটওয়্যার</a>
  <a href="/?q=থ্রিলার" class="cat-pill">🔍 থ্রিলার ও গোয়েন্দা</a>
  <a href="/?q=শিশু-কিশোর" class="cat-pill">👶 শিশু-কিশোর সাহিত্য</a>
</div>

<!-- 7. CURATED SHELVES (Loaded from 269k+ database) -->
{% for shelf in shelves %}
<section class="shelf-section" id="{{ shelf.id }}">
  <div class="shelf-header">
    <div>
      <h2 class="shelf-title">{{ shelf.title }}</h2>
      <p style="font-size:12px; color:var(--muted-text); margin-top:2px;">{{ shelf.subtitle }}</p>
    </div>
    <a href="/?q={{ shelf.title.split()[1] if shelf.title.split()|length > 1 else 'বই' }}" class="shelf-link">সবগুলো দেখুন →</a>
  </div>

  <div class="books-grid">
    {% for b in shelf.books %}
    <div class="book-card" onclick="openCompareModal('{{ b.title }}')">
      <span class="card-badge">-{{ b.discount_pct }}% ছাড়</span>
      <div class="book-card-cover">
        <span class="book-cover-placeholder">📖</span>
      </div>
      <div class="book-card-body">
        <h3 class="book-title" title="{{ b.title }}">{{ b.title }}</h3>
        <p class="book-author">👤 {{ b.author }}</p>
        <div class="book-rating">⭐⭐⭐⭐⭐ (৪.৯)</div>
        <div class="book-pricing">
          <span class="price-current">৳{{ b.price }}</span>
          <span class="price-regular">৳{{ b.regular_price }}</span>
        </div>
        <div class="card-actions">
          <button class="btn-compare" onclick="event.stopPropagation(); openCompareModal('{{ b.title }}');">
            <span>⚡</span> সর্বনিম্ন দাম (Top 3)
          </button>
          <button class="btn-cod" onclick="event.stopPropagation(); openCodModal('{{ b.title }}', '{{ b.price }}', 'সেরা বুকশপ');">
            🛒 অর্ডার করুন (COD)
          </button>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
</section>
{% endfor %}

{% else %}
<!-- 8. SEARCH RESULTS VIEW -->
<section class="search-results-section">
  <div class="results-header-banner">
    <div>
      <h2 style="font-size:20px; font-weight:700;">'{{ query }}' এর জন্য সেরা অফারসমূহ</h2>
      <p style="font-size:13px; color:var(--muted-text);">আমাদের ২১টি বুকশপের মধ্যে মোট <strong>{{ total_found }}টি</strong> অপশন পাওয়া গেছে।</p>
    </div>
    <a href="/" class="btn-compare" style="padding:8px 16px;">← বুকস্টোর হোমে ফিরে যান</a>
  </div>

  {% if top_5 %}
  <div style="margin-bottom:24px;">
    <h3 style="font-size:17px; font-weight:700; margin-bottom:12px; color:#166534;">🏆 স্টকে থাকা সেরা কম দাম (Top Deals)</h3>
    <div class="books-grid">
      {% for item in top_5 %}
      <div class="book-card" onclick="openCompareModal('{{ item.title }}')">
        <span class="card-badge" style="background:#166534;">{{ item.badge }}</span>
        <div class="book-card-cover">
          {% if item.image %}
          <img src="{{ item.image }}" alt="{{ item.title }}" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
          <span class="book-cover-placeholder" style="display:none;">📖</span>
          {% else %}
          <span class="book-cover-placeholder">📖</span>
          {% endif %}
        </div>
        <div class="book-card-body">
          <h3 class="book-title">{{ item.title }}</h3>
          <p class="book-author">🏪 {{ item.store }} | 👤 {{ item.author or 'অজ্ঞাত' }}</p>
          <div class="book-pricing">
            <span class="price-current">৳{{ item.price }}</span>
            {% if item.regular_price and item.regular_price > item.price %}
            <span class="price-regular">৳{{ item.regular_price }}</span>
            {% endif %}
          </div>
          <div class="card-actions">
            <button class="btn-compare" onclick="event.stopPropagation(); openCompareModal('{{ item.title }}');">
              <span>⚡</span> দাম তুলনা (Top 3)
            </button>
            <button class="btn-cod" onclick="event.stopPropagation(); openCodModal('{{ item.title }}', '{{ item.price }}', '{{ item.store }}');">
              🛒 অর্ডার করুন (COD)
            </button>
          </div>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {% if all_results %}
  <div>
    <h3 style="font-size:17px; font-weight:700; margin-bottom:12px;">📊 সব বুকশপের পূর্ণাঙ্গ তালিকা ({{ all_results|length }}টি অপশন)</h3>
    <div class="books-grid">
      {% for item in all_results %}
      <div class="book-card" onclick="openCompareModal('{{ item.title }}')">
        <div class="book-card-cover">
          <span class="book-cover-placeholder">📖</span>
        </div>
        <div class="book-card-body">
          <h3 class="book-title">{{ item.title }}</h3>
          <p class="book-author">🏪 {{ item.store }}</p>
          <div class="book-pricing">
            <span class="price-current">৳{{ item.price }}</span>
          </div>
          <div class="card-actions">
            <button class="btn-compare" onclick="event.stopPropagation(); openCompareModal('{{ item.title }}');">
              <span>⚡</span> যাচাই করুন
            </button>
          </div>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}
</section>
{% endif %}

<!-- 9. ON-CLICK COMPARISON MODAL POPUP (Top 3 Lowest Price Stores) -->
<div id="compareModal" class="modal-overlay" onclick="closeCompareModal(event)">
  <div class="modal-card" onclick="event.stopPropagation();">
    <button class="modal-close-btn" onclick="closeCompareModal()">✕</button>
    
    <div class="modal-book-header">
      <div class="modal-book-thumb" id="modalThumb">
        <span style="font-size:36px;">📖</span>
      </div>
      <div class="modal-book-info">
        <h3 id="modalBookTitle">বইয়ের নাম লোড হচ্ছে...</h3>
        <p id="modalBookAuthor">👤 লেখক: ...</p>
        <p id="modalBookPublisher">🏢 প্রকাশনী: ...</p>
      </div>
    </div>

    <div class="modal-top3-section">
      <div class="modal-top3-title">
        <span>🏆 এই বইটি সবচেয়ে কম দামে পাওয়া যাচ্ছে এমন ৩টি ওয়েবসাইট:</span>
      </div>
      
      <div class="top3-cards" id="modalTop3Container">
        <div style="text-align:center; padding:20px; color:var(--muted-text);">ডাটা লোড হচ্ছে...</div>
      </div>
    </div>

    <!-- Collapsible Full Store List -->
    <div class="modal-all-stores">
      <button class="all-stores-toggle" onclick="toggleAllStores()">
        <span>▼ অন্যান্য বুকশপের তালিকা ও দাম দেখুন</span>
      </button>
      <div id="allStoresContent" style="display:none; margin-top:12px;">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="border-bottom:2px solid var(--border); text-align:left;">
              <th style="padding:6px;">বুকশপ</th>
              <th style="padding:6px;">মূল্য</th>
              <th style="padding:6px;">স্ট্যাটাস</th>
              <th style="padding:6px; text-align:right;">লিংক</th>
            </tr>
          </thead>
          <tbody id="modalAllStoresBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- 10. CASH ON DELIVERY (COD) ORDER MODAL -->
<div id="codModal" class="modal-overlay" onclick="closeCodModal(event)">
  <div class="modal-card" style="max-width:480px;" onclick="event.stopPropagation();">
    <button class="modal-close-btn" onclick="closeCodModal()">✕</button>
    <div style="padding:20px 24px; border-bottom:1px solid var(--border);">
      <h3 style="font-size:18px; color:var(--wafi-green-dark);">🛒 ১-ক্লিক ক্যাশ অন ডেলিভারি অর্ডার</h3>
      <p style="font-size:13px; color:var(--muted-text); margin-top:2px;">ঘরে বসে বই হাতে পেয়ে মূল্য পরিশোধ করুন।</p>
    </div>
    <div class="cod-form-wrap">
      <div style="background:#ffffff; padding:10px 14px; border:1px solid var(--border); border-radius:8px; margin-bottom:12px;">
        <strong id="codBookTitle" style="color:var(--dark-text); font-size:14px;">বইয়ের নাম</strong>
        <div style="font-size:13px; color:#166534; font-weight:700; margin-top:2px;">মূল্য: <span id="codBookPrice">৳০</span> (<span id="codBookStore">বুকশপ</span>)</div>
      </div>

      <form id="codForm" onsubmit="submitCodOrder(event)">
        <input type="hidden" id="codOrderBook">
        <input type="hidden" id="codOrderPrice">
        <input type="hidden" id="codOrderStore">
        
        <div class="cod-form-grid">
          <div>
            <label style="font-size:12px; font-weight:600;">আপনার নাম *</label>
            <input type="text" id="custName" class="form-input" required placeholder="পুরো নাম">
          </div>
          <div>
            <label style="font-size:12px; font-weight:600;">মোবাইল নম্বর *</label>
            <input type="tel" id="custPhone" class="form-input" required placeholder="০১XXXXXXXXX">
          </div>
          <div style="grid-column: 1 / -1;">
            <label style="font-size:12px; font-weight:600;">জেলা / শহর *</label>
            <input type="text" id="custDistrict" class="form-input" required placeholder="যেমন: ঢাকা / চট্টগ্রাম">
          </div>
          <div style="grid-column: 1 / -1;">
            <label style="font-size:12px; font-weight:600;">সম্পূর্ণ ডেলিভারি ঠিকানা *</label>
            <textarea id="custAddress" class="form-input" rows="2" required placeholder="বাসা/রোড নম্বর, এলাকা ও পোস্ট কোড"></textarea>
          </div>
          <button type="submit" class="btn-submit-order" id="btnSubmitOrder">✅ অর্ডার নিশ্চিত করুন</button>
        </div>
      </form>
      <div id="codSuccessMsg" style="display:none; text-align:center; padding:16px; background:#f0fdf4; border-radius:8px; margin-top:12px;">
        <div style="font-size:24px;">🎉</div>
        <strong style="color:#166534;">আপনার অর্ডারটি সফল হয়েছে!</strong>
        <p style="font-size:12px; color:var(--dark-text); margin-top:4px;">অর্ডার আইডি: <strong id="resOrderId">#</strong>। শীঘ্রই আমাদের প্রতিনিধি কল দিয়ে ডেলিভারি কনফার্ম করবেন।</p>
      </div>
    </div>
  </div>
</div>

<!-- 11. FOOTER -->
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-col">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
        <span style="font-size:24px;">📚</span>
        <strong style="color:#ffffff; font-size:18px;">বইবন্ধু ডট কম</strong>
      </div>
      <p style="margin-bottom:12px;">বাংলাদেশের প্রথম স্মার্ট বুকস্টোর প্ল্যাটফর্ম ও প্রাইজ কম্প্যারিজন ইঞ্জিন। ২১টি শীর্ষ বুকশপের ২,৭০,০০০+ বইয়ের মধ্যে সর্বনিম্ন মূল্যে পছন্দের বইটি খুঁজে নিন।</p>
      <p>📞 হেল্পলাইন: ০৯৬৩৮-০০১১২২ (সকাল ৯টা - রাত ১০টা)</p>
    </div>
    <div class="footer-col">
      <h4>জনপ্রিয় বিষয়</h4>
      <ul>
        <li><a href="/?category=islamic">ইসলামিক বই</a></li>
        <li><a href="/?q=উপন্যাস">উপন্যাস ও কথাসাহিত্য</a></li>
        <li><a href="/?q=আত্মউন্নয়ন">আত্মউন্নয়ন ও ক্যারিয়ার</a></li>
        <li><a href="/?q=প্রোগ্রামিং">বিজ্ঞান ও প্রযুক্তি</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>বুকশপ পার্টনারস</h4>
      <ul>
        <li>রকমারি ডট কম</li>
        <li>ওয়াফিলাইফ</li>
        <li>বাতিঘর প্রকাশনী</li>
        <li>অন্যপ্রকাশ ও প্রথমা</li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>নিরাপদ কেনাকাটা</h4>
      <p>🔒 সারাদেশে ক্যাশ অন ডেলিভারি (হোম ডেলিভারি) এবং বিকাশের মাধ্যমে ১০০% নিরাপদ কেনাকাটার সুযোগ।</p>
      <div style="margin-top:14px; display:flex; gap:8px;">
        <span style="background:rgba(255,255,255,0.1); padding:4px 8px; border-radius:4px;">🚚 Cash on Delivery</span>
        <span style="background:rgba(255,255,255,0.1); padding:4px 8px; border-radius:4px;">⚡ 24/7 AI Salesman</span>
      </div>
    </div>
  </div>
  <div class="footer-bottom">
    <p>© 2026 বইবন্ধু (BoiBondhu.com) — সর্বস্বত্ব সংরক্ষিত। একটি স্বয়ংক্রিয় এআই চালিত বুকস্টোর প্ল্যাটফর্ম।</p>
  </div>
</footer>

<!-- 12. FLOATING BOI BONDHU AI CHATBOT WIDGET -->
<script src="/widget.js" async></script>

<script>
// ON-CLICK PRICE COMPARISON POPUP LOGIC
async function openCompareModal(bookTitle) {
  const modal = document.getElementById('compareModal');
  const modalTitle = document.getElementById('modalBookTitle');
  const modalAuthor = document.getElementById('modalBookAuthor');
  const modalPublisher = document.getElementById('modalBookPublisher');
  const top3Container = document.getElementById('modalTop3Container');
  const allStoresBody = document.getElementById('modalAllStoresBody');

  modalTitle.textContent = bookTitle;
  modalAuthor.textContent = 'লোড হচ্ছে...';
  modalPublisher.textContent = '';
  top3Container.innerHTML = '<div style="text-align:center; padding:20px; color:var(--muted-text);">২১টি বুকশপে রিয়েলটাইম দাম যাচাই করা হচ্ছে...</div>';
  modal.classList.add('active');

  try {
    const res = await fetch('/api/book/compare?title=' + encodeURIComponent(bookTitle));
    const data = await res.json();

    modalTitle.textContent = data.title;
    modalAuthor.textContent = '👤 লেখক: ' + data.author;
    modalPublisher.textContent = '🏢 প্রকাশনী: ' + data.publisher;

    if (data.top_3 && data.top_3.length > 0) {
      top3Container.innerHTML = data.top_3.map((deal, idx) => `
        <div class="top3-deal-item ${idx === 0 ? 'rank-1' : ''}">
          <div class="deal-store-meta">
            <span class="deal-rank-badge">${deal.badge.split(' ')[0]}</span>
            <div>
              <div class="deal-store-name">${deal.store}</div>
              <span class="deal-store-tag">${deal.store_type}</span>
            </div>
          </div>
          <div class="deal-pricing-actions">
            <div class="deal-prices">
              <div class="deal-current-price">৳${deal.price}</div>
              ${deal.savings > 0 ? `<div class="deal-savings">৳${deal.savings} সাশ্রয়!</div>` : ''}
            </div>
            <div class="deal-btns">
              <button class="btn-modal-order" onclick="openCodModal('${escapeHtml(data.title)}', '${deal.price}', '${escapeHtml(deal.store)}');">
                অর্ডার (COD)
              </button>
              ${deal.url ? `<a href="${deal.url}" target="_blank" rel="noopener noreferrer" class="btn-modal-link">ভিজিট ↗</a>` : ''}
            </div>
          </div>
        </div>
      `).join('');
    } else {
      top3Container.innerHTML = '<div style="text-align:center; padding:20px; color:var(--muted-text);">কোনো দামের রেকর্ড পাওয়া যায়নি।</div>';
    }

    // Populate all remaining stores
    if (data.all_stores && data.all_stores.length > 0) {
      allStoresBody.innerHTML = data.all_stores.map(d => `
        <tr style="border-bottom:1px solid #f1f5f9;">
          <td style="padding:8px 6px;"><strong>${d.store}</strong></td>
          <td style="padding:8px 6px; color:#166534; font-weight:700;">৳${d.price}</td>
          <td style="padding:8px 6px;"><span style="color:#059669; font-size:11px;">✅ ${d.stock_text}</span></td>
          <td style="padding:8px 6px; text-align:right;">
            ${d.url ? `<a href="${d.url}" target="_blank" style="color:var(--wafi-green); font-weight:600;">দেখুন ↗</a>` : '-'}
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    top3Container.innerHTML = '<div style="text-align:center; padding:20px; color:red;">তথ্য লোড করতে সমস্যা হয়েছে।</div>';
  }
}

function closeCompareModal(event) {
  if (!event || event.target.id === 'compareModal' || event.target.classList.contains('modal-close-btn')) {
    document.getElementById('compareModal').classList.remove('active');
  }
}

function toggleAllStores() {
  const content = document.getElementById('allStoresContent');
  content.style.display = content.style.display === 'none' ? 'block' : 'none';
}

// COD MODAL LOGIC
function openCodModal(title, price, store) {
  closeCompareModal();
  document.getElementById('codBookTitle').textContent = title;
  document.getElementById('codBookPrice').textContent = '৳' + price;
  document.getElementById('codBookStore').textContent = store;
  document.getElementById('codOrderBook').value = title;
  document.getElementById('codOrderPrice').value = price;
  document.getElementById('codOrderStore').value = store;
  document.getElementById('codSuccessMsg').style.display = 'none';
  document.getElementById('codForm').style.display = 'block';
  document.getElementById('codModal').classList.add('active');
}

function closeCodModal(event) {
  if (!event || event.target.id === 'codModal' || event.target.classList.contains('modal-close-btn')) {
    document.getElementById('codModal').classList.remove('active');
  }
}

async function submitCodOrder(e) {
  e.preventDefault();
  const btn = document.getElementById('btnSubmitOrder');
  btn.textContent = 'অর্ডার প্রক্রিয়াধীন...';
  btn.disabled = true;

  const payload = {
    customer_name: document.getElementById('custName').value.trim(),
    customer_phone: document.getElementById('custPhone').value.trim(),
    customer_district: document.getElementById('custDistrict').value.trim(),
    delivery_address: document.getElementById('custAddress').value.trim(),
    book_title: document.getElementById('codOrderBook').value,
    price: parseInt(document.getElementById('codOrderPrice').value) || 0,
    store: document.getElementById('codOrderStore').value,
    merchant_id: 'neutral'
  };

  try {
    const res = await fetch('/api/salesman/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === 'ok') {
      document.getElementById('codForm').style.display = 'none';
      document.getElementById('resOrderId').textContent = '#' + (data.order_id || 'ORD-1001');
      document.getElementById('codSuccessMsg').style.display = 'block';
      const cartBadge = document.getElementById('cartCount');
      if (cartBadge) cartBadge.textContent = '১';
    } else {
      alert('অর্ডার সাবমিট করতে সমস্যা হয়েছে: ' + (data.message || 'আবার চেষ্টা করুন'));
      btn.textContent = '✅ অর্ডার নিশ্চিত করুন';
      btn.disabled = false;
    }
  } catch (err) {
    alert('সার্ভার এরর, অনুগ্রহ করে আবার চেষ্টা করুন।');
    btn.textContent = '✅ অর্ডার নিশ্চিত করুন';
    btn.disabled = false;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/'/g, "\'").replace(/"/g, '&quot;');
}
</script>
</body>
</html>"""


# ==============================================================================
# SALESMAN FULLSCREEN HTML TEMPLATE
# ==============================================================================
SALESMAN_TEMPLATE = """
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>বইবন্ধু AI সেলসম্যান | BoiBondhu Book Assistant</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #1e3a8a;
  --primary-light: #2563eb;
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --text: #0f172a;
  --text-muted: #64748b;
  --border: #e2e8f0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Hind Siliguri', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
header {
  background: linear-gradient(135deg, #1e3a8a, #0f172a);
  color: white;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-icon {
  font-size: 36px;
  background: rgba(255,255,255,0.18);
  width: 58px;
  height: 58px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  flex-shrink: 0;
}
.brand-title h1 {
  font-size: 23px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-title p {
  font-size: 13.5px;
  color: #94a3b8;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.nav-link {
  color: white;
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  background: rgba(255,255,255,0.12);
  padding: 8px 14px;
  border-radius: 8px;
  transition: background 0.2s;
}
.nav-link:hover { background: rgba(255,255,255,0.22); }
.credits-pill {
  background: #e0e7ff;
  color: #3730a3;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}
.settings-btn {
  background: rgba(255,255,255,0.15);
  border: none;
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
}

.chat-container {
  flex: 1;
  max-width: 1060px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  padding: 24px 20px;
  height: calc(100vh - 80px);
}
.messages-box {
  flex: 1;
  overflow-y: auto;
  background: white;
  border-radius: 18px;
  border: 1px solid var(--border);
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.msg {
  max-width: 85%;
  padding: 12px 18px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.6;
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.msg-user {
  align-self: flex-end;
  background: linear-gradient(135deg, #1e3a8a, #2563eb);
  color: white;
  border-bottom-right-radius: 4px;
}
.msg-assistant {
  align-self: flex-start;
  background: #f8fafc;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
}
.msg-assistant strong { color: #0f172a; }
.msg-assistant a { color: #2563eb; text-decoration: none; font-weight: 600; }
.msg-assistant a:hover { text-decoration: underline; }

.deal-card {
  background: white;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 14px;
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.deal-store { font-weight: 700; color: #0f172a; }
.deal-price { color: #16a34a; font-weight: 700; font-size: 16px; }
.deal-stock { font-size: 12px; color: #059669; }
.deal-btn {
  background: #2563eb;
  color: white !important;
  padding: 6px 14px;
  border-radius: 6px;
  text-decoration: none !important;
  font-weight: 600;
  font-size: 13px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.chip {
  background: white;
  border: 1px solid #cbd5e1;
  color: #334155;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.chip:hover {
  background: #eff6ff;
  border-color: #3b82f6;
  color: #1d4ed8;
}

.typing {
  display: inline-flex;
  gap: 5px;
  padding: 10px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  width: fit-content;
}
.dot {
  width: 8px;
  height: 8px;
  background: #94a3b8;
  border-radius: 50%;
  animation: blink 1.4s infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.input-bar {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}
.input-field {
  flex: 1;
  padding: 14px 18px;
  border: 1px solid #cbd5e1;
  border-radius: 14px;
  font-size: 15px;
  outline: none;
  font-family: inherit;
  background: white;
}
.input-field:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
.send-button {
  background: #1e3a8a;
  color: white;
  border: none;
  padding: 0 24px;
  border-radius: 14px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: inherit;
  transition: background 0.2s;
}
.send-button:hover { background: #2563eb; }
.send-button:disabled { background: #94a3b8; cursor: not-allowed; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-overlay.active { display: flex; }
.modal-card {
  background: white;
  padding: 24px;
  border-radius: 16px;
  max-width: 440px;
  width: 90%;
  box-shadow: 0 20px 40px rgba(0,0,0,0.2);
}
.modal-card h3 { font-size: 18px; margin-bottom: 8px; }
.modal-card p { font-size: 13px; color: var(--text-muted); margin-bottom: 14px; }
.modal-card input {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  margin-bottom: 16px;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn-sm {
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  font-size: 13px;
  cursor: pointer;
  font-weight: 600;
}
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-icon">🤖</div>
    <div class="brand-title">
      <h1>বইবন্ধু AI সেলসম্যান <span style="font-size:12px; font-weight:normal; background:rgba(255,255,255,0.2); padding:2px 8px; border-radius:999px;">২১+ বুকশপ ও প্রকাশনী কানেক্টেড</span></h1>
      <p>আপনার চাহিদা বুঝে বই বাছাই ও ২১টি বুকশপের লাইভ সেরা অফার</p>
    </div>
  </div>
  <div class="header-right">
    <a href="/" class="nav-link">🔍 প্রাইস কম্প্যারেটর</a>
    <span class="credits-pill" id="credits-badge">অনলাইন একটিভ</span>
  </div>
</header>

<div class="chat-container">
  <div class="messages-box" id="messages-box">
    <div class="msg msg-assistant">
      <p>সালাম/নমস্কার প্রিয় পাঠক! 👋</p>
      <p>আমি <strong>বইবন্ধু</strong>—আপনার পার্সোনাল বই সেলসম্যান ও কনসালট্যান্ট। ৬০,০০০+ বইয়ের ক্যাটালগ এবং বাংলাদেশের <strong>২১টি অনলাইন বুকশপ ও শীর্ষ প্রকাশনীর রিয়েল-টাইম স্ক্র্যাপার</strong> আমার সাথে যুক্ত।</p>
      <p style="margin-top:6px; color:#64748b;">আপনি কী ধরনের বই পড়তে পছন্দ করেন বা বর্তমান অনুভূতি কেমন? নিচে চাপ দিন অথবা লিখে জানান:</p>
      <div class="chips">
        <button class="chip" data-prompt="হতাশা ও দুশ্চিন্তা কাটানোর ভালো বই">🌱 হতাশা ও আত্ম-উন্নয়ন</button>
        <button class="chip" data-prompt="৫০০ টাকার মধ্যে সেরা ইসলামিক বই">📖 ৫০০ টাকার মধ্যে ইসলামিক বই</button>
        <button class="chip" data-prompt="রহস্য রোমাঞ্চ ও থ্রিলার বই">🕵️‍♂️ থ্রিলার ও গোয়েন্দা বই</button>
        <button class="chip" data-prompt="হুমায়ূন আহমেদের সেরা উপন্যাস">✨ হুমায়ূন আহমেদের উপন্যাস</button>
        <button class="chip" data-prompt="সায়েন্স ফিকশন ও মহাকাশ বিজ্ঞান">🚀 সায়েন্স ফিকশন ও বিজ্ঞান</button>
      </div>
    </div>
  </div>

  <div class="input-bar">
    <input type="text" class="input-field" id="user-input" placeholder="আপনার অনুভূতি, বাজেট বা বইয়ের নাম লিখুন (যেমন: হতাশা কাটানোর জন্য ৪০০ টাকার মধ্যে বই...)" autocomplete="off">
    <button class="send-button" id="send-btn">
      <span>পাঠান</span>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
    </button>
  </div>
</div>

<!-- Settings Modal -->
<div class="modal-overlay" id="settings-modal">
  <div class="modal-card">
    <h3>Gemini API কী সেটিংস (ঐচ্ছিক)</h3>
    <p>সেশনের ১৫টি ফ্রি ক্রেডিটের বাইরে নিজের আনলিমিটেড Google Gemini 1.5/2.0 Flash কী ব্যবহার করতে পারেন:</p>
    <input type="password" id="gemini-key-input" placeholder="AIzaSy...">
    <div class="modal-actions">
      <button class="btn-sm" style="background:#f1f5f9; color:#475569;" id="cancel-settings">বাতিল</button>
      <button class="btn-sm" style="background:#2563eb; color:white;" id="save-settings">সংরক্ষণ করুন</button>
    </div>
  </div>
</div>

<script>
(function() {
  var sessionId = localStorage.getItem('bb_sess_id');
  if (!sessionId) {
    sessionId = 'bb_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();
    localStorage.setItem('bb_sess_id', sessionId);
  }
  var userKey = localStorage.getItem('bb_api_key') || '';

  var box = document.getElementById('messages-box');
  var input = document.getElementById('user-input');
  var sendBtn = document.getElementById('send-btn');
  var creditsBadge = document.getElementById('credits-badge');
  var modal = document.getElementById('settings-modal');
  var openSettings = document.getElementById('open-settings');
  var cancelSettings = document.getElementById('cancel-settings');
  var saveSettings = document.getElementById('save-settings');
  var keyInput = document.getElementById('gemini-key-input');

  keyInput.value = userKey;

  openSettings.onclick = function() { modal.classList.add('active'); };
  cancelSettings.onclick = function() { modal.classList.remove('active'); };
  saveSettings.onclick = function() {
    userKey = keyInput.value.trim();
    localStorage.setItem('bb_api_key', userKey);
    modal.classList.remove('active');
    appendAssistant('আপনার Gemini API কী সংরক্ষিত হয়েছে!');
  };

  function formatMarkdown(text) {
    if (!text) return '';
    var safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    safe = safe.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
    safe = safe.replace(/\\*(.*?)\\*/g, '<em>$1</em>');
    safe = safe.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1 ↗</a>');
    safe = safe.replace(/^[•\\-\\*]\\s+(.*)$/gm, '<li style="margin-left:16px;">$1</li>');
    safe = safe.replace(/\\n\\n+/g, '</p><p>');
    safe = safe.replace(/\\n/g, '<br>');
    return '<p>' + safe + '</p>';
  }

  function appendUser(text) {
    var d = document.createElement('div');
    d.className = 'msg msg-user';
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  }

  function appendAssistant(text, deals) {
    var d = document.createElement('div');
    d.className = 'msg msg-assistant';
    d.innerHTML = formatMarkdown(text);

    if (deals && deals.length > 0) {
      deals.forEach(function(deal, idx) {
        var card = document.createElement('div');
        card.className = 'deal-card';
        var badge = idx === 0 ? '🥇 ১ম' : (idx === 1 ? '🥈 ২য়' : '🥉 ৩য়');
        var reg = deal.regular_price ? '<span style="text-decoration:line-through; color:#94a3b8; font-size:12px; margin-left:4px;">৳' + deal.regular_price + '</span>' : '';
        card.innerHTML = '<div><div class="deal-store">' + badge + ' ' + deal.store + '</div><div><span class="deal-price">৳' + deal.price + '</span>' + reg + '</div><div class="deal-stock">' + (deal.stock_text || 'স্টকে আছে') + '</div></div>' +
          (deal.url ? '<a href="' + deal.url + '" target="_blank" rel="noopener noreferrer" class="deal-btn">কিনুন ↗</a>' : '');
        d.appendChild(card);
      });
      var chipsDiv = document.createElement('div');
      chipsDiv.className = 'chips';
      chipsDiv.style.marginTop = '10px';
      chipsDiv.innerHTML = '<button class="chip" data-prompt="বইটির বিস্তারিত বিষয়বস্তু ও সূচিপত্র দেখতে চাই">📑 সূচিপত্র ও বিষয়বস্তু জানুন</button><button class="chip" data-prompt="বইটির পাঠক রিভিউ ও রেটিং কেমন?">⭐ পাঠক রিভিউ জানুন</button>';
      d.appendChild(chipsDiv);
    }

    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  }

  var typingElem = null;
  function showTyping() {
    if (typingElem) return;
    typingElem = document.createElement('div');
    typingElem.className = 'typing';
    typingElem.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    box.appendChild(typingElem);
    box.scrollTop = box.scrollHeight;
  }
  function hideTyping() {
    if (typingElem && typingElem.parentNode) {
      typingElem.parentNode.removeChild(typingElem);
      typingElem = null;
    }
  }

  box.addEventListener('click', function(e) {
    var chip = e.target.closest('.chip');
    if (chip) {
      input.value = chip.getAttribute('data-prompt');
      sendMessage();
    }
  });

  function sendMessage() {
    var msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    appendUser(msg);

    sendBtn.disabled = true;
    showTyping();

    fetch('/api/salesman/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        session_id: sessionId,
        api_key: userKey || undefined
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      hideTyping();
      sendBtn.disabled = false;
      if (data.session_id) sessionId = data.session_id;
      if (typeof data.credits_left === 'number') {
        creditsBadge.textContent = data.credits_left + ' ক্রেডিট বাকি';
      }
      appendAssistant(data.reply, data.live_deals);
    })
    .catch(function(err) {
      hideTyping();
      sendBtn.disabled = false;
      appendAssistant('দুঃখিত, কোনো একটি ত্রুটি ঘটেছে। পুনরায় চেষ্টা করুন।');
    });
  }

  sendBtn.onclick = sendMessage;
  input.onkeydown = function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendMessage();
    }
  };
})();
</script>
</body>
</html>
"""


# ==============================================================================
# METADATA ENRICHMENT HELPER (Image + Writer + Publication + Topic)
# ==============================================================================
def enrich_book_results(data, query):
    """Enriches bookstore results with Author, Publisher, Subject and best Image from Master Catalog and cross-store data."""
    if not data:
        return data

    best_img = ""
    best_auth = ""
    for item in data.get("all_results", []):
        img_val = str(item.get("image") or "")
        if not best_img and ("http://" in img_val or "https://" in img_val):
            best_img = img_val
        auth_val = str(item.get("author") or "").strip()
        if not best_auth and len(auth_val) > 1 and auth_val not in ['-', 'N/A', 'None']:
            best_auth = auth_val

    # If no live store had an image, resolve cover from cache / providers
    if not best_img and query:
        best_img = resolve_book_cover(query)

    cat_author = ""
    cat_publisher = ""
    cat_subject = ""
    try:
        hits = salesman_agent.catalog.search(keywords=query.split()[:3], limit=1)
        if hits:
            c = hits[0]
            cat_author = c.get("author") or ""
            cat_publisher = c.get("publisher") or ""
            cat_subject = c.get("subject") or ""
    except Exception as e:
        print(f"[Enrich] Catalog lookup error: {e}")

    final_auth = best_auth or cat_author

    for item in data.get("all_results", []):
        if not item.get("image") and best_img:
            item["image"] = best_img
        if not item.get("author") and final_auth:
            item["author"] = final_auth
        if not item.get("publisher") and cat_publisher:
            item["publisher"] = cat_publisher
        if not item.get("subject") and cat_subject:
            item["subject"] = cat_subject

    top_deals_list = data.get("top_5") or data.get("top_3", [])
    for deal in top_deals_list:
        if not deal.get("image") and best_img:
            deal["image"] = best_img
        if not deal.get("author") and final_auth:
            deal["author"] = final_auth
        if not deal.get("publisher") and cat_publisher:
            deal["publisher"] = cat_publisher
        if not deal.get("subject") and cat_subject:
            deal["subject"] = cat_subject

    return data


# ==============================================================================
# ROUTES
# ==============================================================================
# ==============================================================================
# WAFILIFE STORE SHELVES & TOP 3 COMPARE API
# ==============================================================================
STORE_SHELVES_CACHE = None

def get_store_shelves():
    global STORE_SHELVES_CACHE
    if STORE_SHELVES_CACHE is not None:
        return STORE_SHELVES_CACHE

    from salesman.catalog_fts import DB_PATH, normalize_bangla_phonetic
    import sqlite3

    shelves_config = [
        {
            "id": "bestsellers",
            "title": "🔥 সর্বাধিক বিক্রিত ও জনপ্রিয় বই (Top Bestsellers)",
            "subtitle": "পাঠকদের সর্বাধিক পঠিত ও আলোচিত শীর্ষ বইসমূহ — সর্বনিম্ন দামে অর্ডার করুন",
            "titles": [
                "শঙ্খনীল কারাগার", "প্যারাডক্সিক্যাল সাজিদ", "বেলা ফুরাবার আগে", "দেবী",
                "রিচার্জ আপনার ঈমান", "নন্দিত নরকে"
            ]
        },
        {
            "id": "discount",
            "title": "🏷️ আকর্ষণীয় অফার ও সর্বোচ্চ ছাড়ের বই (Mega Discount Deals)",
            "subtitle": "২৫% থেকে ৪৫% পর্যন্ত স্পেশাল ডিসকাউন্টে শীর্ষ বইসমূহ",
            "titles": [
                "হতাশা কাটানোর উপায়", "সি দিয়ে কম্পিউটার প্রোগ্রামিং", "হাবলুদের জন্য প্রোগ্রামিং",
                "প্রশান্তি", "জীবনের সাথে লড়াই"
            ]
        },
        {
            "id": "islamic",
            "title": "🕌 সমাদৃত ইসলামিক বই ও তাফসির (Islamic Literature)",
            "subtitle": "দ্বীনি জ্ঞান, আত্মশুদ্ধি ও অনুপ্রেরণামূলক সেরা ইসলামিক বই",
            "titles": [
                "প্যারাডক্সিক্যাল সাজিদ", "বেলা ফুরাবার আগে", "সীরাতুন নবী",
                "আর রাহীকুল মাখতূম", "রিচার্জ আপনার ঈমান"
            ]
        },
        {
            "id": "novels",
            "title": "📚 কালজয়ী কথাসাহিত্য ও উপন্যাস (Classic Literature)",
            "subtitle": "বাংলা সাহিত্যের কালজয়ী ও জনপ্রিয় উপন্যাস সংগ্রহ",
            "titles": [
                "শঙ্খনীল কারাগার", "নন্দিত নরকে", "দেবী", "কালবেলা", "শেষের কবিতা"
            ]
        },
        {
            "id": "career",
            "title": "💡 ক্যারিয়ার, স্কিল ও সেলফ ডেভেলপমেন্ট (Career & Personal Growth)",
            "subtitle": "প্রোগ্রামিং, আত্মউন্নয়ন ও ক্যারিয়ার গঠনের সেরা গাইডবুক",
            "titles": [
                "হাবলুদের জন্য প্রোগ্রামিং", "সি দিয়ে কম্পিউটার প্রোগ্রামিং", "পারমাণবিক অভ্যাস",
                "রিচ ড্যাড পুওর ড্যাড", "ডিপ ওয়ার্ক"
            ]
        }
    ]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    built_shelves = []

    for s in shelves_config:
        shelf_books = []
        for t in s["titles"]:
            norm = normalize_bangla_phonetic(t)
            cur.execute("""
                SELECT book_name, author_name, publisher_name, subject_name, min(price), max(regular_price), url
                FROM master_store_catalog
                WHERE norm_name = ? AND price > 0
                GROUP BY book_name
            """, (norm,))
            row = cur.fetchone()
            if row:
                p = row[4]
                rp = row[5] or int(p * 1.25)
                if rp > p * 2.5:
                    rp = int(p * 1.35)
                disc = int(((rp - p) / rp) * 100) if rp > p else 20
                shelf_books.append({
                    "title": row[0],
                    "author": row[1] or "জনপ্রিয় লেখক",
                    "publisher": row[2] or "সেরা প্রকাশনী",
                    "subject": row[3] or "সাহিত্য",
                    "price": p,
                    "regular_price": rp,
                    "discount_pct": disc,
                    "url": row[6] or "",
                    "in_stock": True
                })
        built_shelves.append({
            "id": s["id"],
            "title": s["title"],
            "subtitle": s["subtitle"],
            "books": shelf_books
        })

    conn.close()
    STORE_SHELVES_CACHE = built_shelves
    return built_shelves


@app.route("/api/book/compare")
def api_book_compare():
    title = request.args.get("title", "").strip()
    if not title:
        return jsonify({"error": "Missing title"}), 400

    try:
        from salesman.banglish_transliterator import is_banglish, transliterate_banglish
        if is_banglish(title):
            title = transliterate_banglish(title)
    except Exception:
        pass

    from salesman.catalog_fts import normalize_bangla_phonetic, DB_PATH
    import sqlite3

    norm = normalize_bangla_phonetic(title)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT book_name, author_name, publisher_name, subject_name
        FROM master_store_catalog
        WHERE norm_name = ?
        LIMIT 1
    """, (norm,))
    meta_row = cur.fetchone()
    if not meta_row:
        cur.execute("""
            SELECT DISTINCT book_name, author_name, publisher_name, subject_name
            FROM master_store_catalog
            WHERE norm_name LIKE ?
            ORDER BY length(norm_name) ASC
            LIMIT 1
        """, (f"%{norm}%",))
        meta_row = cur.fetchone()

    can_title = meta_row[0] if meta_row else title
    author = meta_row[1] if meta_row and meta_row[1] else "অজ্ঞাত লেখক"
    publisher = meta_row[2] if meta_row and meta_row[2] else "অন্যান্য প্রকাশনী"
    subject = meta_row[3] if meta_row and meta_row[3] else "সাধারণ বই"

    norm_can = normalize_bangla_phonetic(can_title)
    cur.execute("""
        SELECT store, price, regular_price, url
        FROM master_store_catalog
        WHERE norm_name = ? AND price > 0
        ORDER BY price ASC
    """, (norm_can,))
    deal_rows = cur.fetchall()
    conn.close()

    deals = []
    seen = set()
    for d in deal_rows:
        if d[0] not in seen:
            seen.add(d[0])
            st = d[0]
            price = d[1]
            reg = d[2] or int(price * 1.25)
            if reg > price * 2.5:
                reg = int(price * 1.35)
            savings = max(0, reg - price)
            deals.append({
                "store": st,
                "store_type": "Islamic" if any(k in st.lower() for k in ["wafi", "ruhama", "ashraf", "kitab", "aladaboi", "bdbooks", "boibitan"]) else "General",
                "price": price,
                "regular_price": reg,
                "savings": savings,
                "url": d[3],
                "in_stock": True,
                "stock_text": "স্টকে আছে"
            })

    top_3 = deals[:3]
    for i, d in enumerate(top_3, start=1):
        d["rank"] = i
        d["badge"] = "🥇 ১ম সর্বনিম্ন দাম!" if i == 1 else ("🥈 ২য় সর্বনিম্ন" if i == 2 else "🥉 ৩য় সর্বনিম্ন")

    return jsonify({
        "title": can_title,
        "author": author,
        "publisher": publisher,
        "subject": subject,
        "top_3": top_3,
        "all_stores": deals,
        "total_stores": len(deals)
    })


@app.route("/")
def home():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "all")

    if not query:
        shelves = get_store_shelves()
        return render_template_string(
            HTML_TEMPLATE,
            query="",
            category=category,
            top_5=[],
            top_3=[],
            all_results=[],
            total_found=0,
            shelves=shelves
        )

    # Banglish Transliteration (e.g. 'shonkhonil karagar' -> 'শঙ্খনীল কারাগার')
    try:
        from salesman.banglish_transliterator import is_banglish, transliterate_banglish
        if is_banglish(query):
            query = transliterate_banglish(query)
    except Exception:
        pass

    cache_key = f"{query.lower()}:{category}"
    cached_data = get_cached(cache_key)

    if cached_data is not None:
        data = cached_data
    else:
        data = compare_books(query, category=category)
        set_cached(cache_key, data)

    data = enrich_book_results(data, query)
    top_deals = data.get("top_5") or data.get("top_3", [])

    return render_template_string(
        HTML_TEMPLATE,
        query=data["query"],
        category=data["category"],
        top_5=top_deals,
        top_3=top_deals,
        all_results=data["all_results"],
        total_found=data["total_found"]
    )


@app.route("/api/compare", methods=["GET"])
def api_compare():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "all")
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    try:
        from salesman.banglish_transliterator import is_banglish, transliterate_banglish
        if is_banglish(query):
            query = transliterate_banglish(query)
    except Exception:
        pass

    cache_key = f"{query.lower()}:{category}"
    cached_data = get_cached(cache_key)

    if cached_data is not None:
        enriched = enrich_book_results(cached_data, query)
        return jsonify({**enriched, "cached": True})

    data = compare_books(query, category=category)
    set_cached(cache_key, data)
    enriched = enrich_book_results(data, query)
    return jsonify({**enriched, "cached": False})


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/salesman")
def salesman_page():
    return render_template_string(SALESMAN_TEMPLATE)


@app.route("/widget.js")
def serve_widget():
    widget_path = os.path.join(os.path.dirname(__file__), "static", "salesman-widget.js")
    if not os.path.exists(widget_path):
        return Response("// widget not found", mimetype="application/javascript")
    with open(widget_path, "r", encoding="utf-8") as f:
        content = f.read()
    response = Response(content, mimetype="application/javascript; charset=utf-8")
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/demo")
def serve_demo():
    demo_path = os.path.join(os.path.dirname(__file__), "demo_widget.html")
    if not os.path.exists(demo_path):
        return "Demo file not found", 404
    with open(demo_path, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, mimetype="text/html; charset=utf-8")


# ==============================================================================
# MERCHANT B2B PORTAL HTML TEMPLATE
# ==============================================================================
MERCHANT_PORTAL_TEMPLATE = """
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>বুকশপ AI সেলসম্যান B2B পোর্টাল | Bookstore AI Merchant Portal</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #059669;
  --primary-dark: #065f46;
  --bg: #f8fafc;
  --card: #ffffff;
  --text: #0f172a;
  --text-muted: #64748b;
  --border: #e2e8f0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Hind Siliguri', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding-bottom: 60px;
}
header {
  background: linear-gradient(135deg, #065f46 0%, #0f172a 100%);
  color: white;
  padding: 40px 20px 30px;
  text-align: center;
}
.header-badge {
  display: inline-block;
  background: rgba(255,255,255,0.15);
  backdrop-filter: blur(4px);
  padding: 4px 14px;
  border-radius: 999px;
  font-size: 13px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #a7f3d0;
}
h1 { font-size: 32px; font-weight: 700; margin-bottom: 8px; }
.subtitle { color: #cbd5e1; font-size: 16px; max-width: 680px; margin: 0 auto; }
.nav-links { margin-top: 18px; display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }
.nav-btn {
  background: rgba(255,255,255,0.15);
  color: white;
  text-decoration: none;
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255,255,255,0.25);
  transition: all 0.2s;
}
.nav-btn:hover { background: rgba(255,255,255,0.25); }

.container {
  max-width: 1060px;
  margin: -20px auto 0;
  padding: 0 16px;
}

/* Pricing Grid */
.pricing-section { margin-bottom: 40px; }
.section-title { font-size: 22px; font-weight: 700; margin-bottom: 16px; color: #0f172a; display: flex; align-items: center; gap: 8px; }
.pricing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}
.pricing-card {
  background: white;
  border-radius: 16px;
  border: 1px solid var(--border);
  padding: 28px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  position: relative;
  display: flex;
  flex-direction: column;
}
.pricing-card.featured {
  border: 2px solid #059669;
  box-shadow: 0 8px 24px rgba(5, 150, 105, 0.12);
}
.featured-badge {
  position: absolute;
  top: -12px;
  right: 20px;
  background: #059669;
  color: white;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
}
.plan-name { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
.plan-price { font-size: 32px; font-weight: 700; color: #059669; margin-bottom: 12px; }
.plan-price span { font-size: 14px; font-weight: 500; color: var(--text-muted); }
.plan-desc { font-size: 14px; color: var(--text-muted); margin-bottom: 20px; }
.plan-features { list-style: none; margin-bottom: 24px; flex: 1; }
.plan-features li { padding: 6px 0; font-size: 14px; display: flex; align-items: center; gap: 8px; }
.plan-features li::before { content: "✓"; color: #059669; font-weight: 700; }
.plan-btn {
  background: #0f172a;
  color: white;
  border: none;
  padding: 12px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  text-align: center;
  font-family: inherit;
  transition: background 0.2s;
}
.pricing-card.featured .plan-btn { background: #059669; }
.pricing-card.featured .plan-btn:hover { background: #047857; }

/* Interactive Simulator */
.simulator-box {
  background: white;
  border-radius: 16px;
  border: 1px solid var(--border);
  padding: 28px;
  box-shadow: 0 6px 16px rgba(0,0,0,0.03);
  margin-bottom: 40px;
}
.store-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 24px;
}
.store-pill {
  padding: 8px 18px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #f1f5f9;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.store-pill.active {
  background: #059669;
  color: white;
  border-color: #059669;
  box-shadow: 0 4px 10px rgba(5, 150, 105, 0.25);
}
.code-box {
  background: #0f172a;
  color: #38bdf8;
  padding: 16px 20px;
  border-radius: 12px;
  font-family: monospace;
  font-size: 13.5px;
  overflow-x: auto;
  margin: 12px 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.copy-btn {
  background: rgba(255,255,255,0.15);
  color: white;
  border: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
}
.copy-btn:hover { background: rgba(255,255,255,0.25); }

.store-preview-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.store-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.store-avatar {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: white;
}
.store-meta h3 { font-size: 17px; font-weight: 700; }
.store-meta p { font-size: 13px; color: var(--text-muted); }
.exclusive-tag {
  display: inline-block;
  background: #dcfce7;
  color: #15803d;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  width: fit-content;
}

/* Facebook Guide */
.guide-box {
  background: white;
  border-radius: 16px;
  border: 1px solid var(--border);
  padding: 28px;
}
.steps-list { list-style: none; counter-reset: step-counter; }
.steps-list li {
  position: relative;
  padding-left: 44px;
  margin-bottom: 20px;
  font-size: 15px;
}
.steps-list li::before {
  counter-increment: step-counter;
  content: counter(step-counter);
  position: absolute;
  left: 0;
  top: 0;
  width: 30px;
  height: 30px;
  background: #059669;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}
</style>
</head>
<body>

<header>
  <div class="header-badge">🚀 B2B Bookstore SaaS Solution</div>
  <h1>বুকশপ AI সেলসম্যান B2B পোর্টাল</h1>
  <p class="subtitle">যেকোনো অনলাইন বুকস্টোর বা ফেসবুক পেজে সেলস বাড়াতে ২৪/৭ স্মার্ট সেলসম্যান। অন্য কোনো কোম্পানি ব্যবহার করলে শুধুমাত্র তাদের দোকানের বই ও স্টক-ই দেখাবে!</p>
  <div class="nav-links">
    <a href="/" class="nav-btn">🔍 লাইভ ১৭ বুকশপ কম্প্যারেটর</a>
    <a href="/salesman" class="nav-btn">💬 বইবন্ধু AI সেলসম্যান</a>
  </div>
</header>

<div class="container">
  <!-- PRICING SECTION -->
  <section class="pricing-section">
    <h2 class="section-title">💎 B2B সাবস্ক্রিপশন প্যাকেজসমূহ (Monthly Pricing)</h2>
    <div class="pricing-grid">
      <!-- Standard Plan -->
      <div class="pricing-card">
        <div class="plan-name">Standard Web Plan</div>
        <div class="plan-price">৳১,৫০০ <span>/ মাস</span></div>
        <div class="plan-desc">অনলাইন বুকশপ ওয়েবসাইটের জন্য স্বয়ংক্রিয় এআই সেলসম্যান উইজেট।</div>
        <ul class="plan-features">
          <li>ওয়েবসাইটে ১ লাইনের চ্যাট উইজেট স্ক্রিপ্ট</li>
          <li><strong>সিঙ্গেল স্টোর এক্সক্লুসিভ মোড</strong> (কোনো প্রতিদ্বন্দ্বী দোকানের লিংক বা তথ্য দেখাবে না)</li>
          <li>বুকস্টোরের লোগো, নাম ও নিজস্ব ব্র্যান্ড কালার</li>
          <li>লাইভ স্টক ভেরিফিকেশন ও ডিরেক্ট "অর্ডার করুন" লিংক</li>
          <li>২,০০০ কাস্টমার কনভারসেশন / মাস</li>
          <li>ইমেইল ও হোয়াটসঅ্যাপ সাপোর্ট</li>
        </ul>
        <button class="plan-btn" onclick="selectStore('ruhama')">রূহামা শপ ডেমো দেখুন</button>
      </div>

      <!-- Pro Plan -->
      <div class="pricing-card featured">
        <div class="featured-badge">সবচেয়ে জনপ্রিয়</div>
        <div class="plan-name">Pro Omni Plan (Web + Facebook)</div>
        <div class="plan-price">৳২,৫০০ <span>/ মাস</span></div>
        <div class="plan-desc">ওয়েবসাইট উইজেট + ফেসবুক পেজ মেসেঞ্জার ইনবক্স অটোমেশন।</div>
        <ul class="plan-features">
          <li>Standard Plan-এর সমস্ত ফিচার অন্তর্ভুক্ত</li>
          <li><strong>ফেসবুক পেজ মেসেঞ্জার বট ইন্টিগ্রেশন</strong> (ইনবক্সে আসা কাস্টমারদের সাথে স্বয়ংক্রিয় সেলস চ্যাট)</li>
          <li>ক্যাশ-অন-ডেলিভারি ডিরেক্ট অর্ডার কালেকশন</li>
          <li>আনলিমিটেড কাস্টমার কনভারসেশন</li>
          <li>কাস্টমার কোন বইগুলো বেশি খুঁজছে তার অ্যানালিটিক্স রিপোর্ট</li>
          <li>২৪/৭ প্রায়োরিটি ভিআইপি টেকনিক্যাল সাপোর্ট</li>
        </ul>
        <button class="plan-btn" onclick="selectStore('baatighar')">বাতিঘর ডেমো দেখুন</button>
      </div>
    </div>
  </section>

  <!-- LIVE SIMULATOR -->
  <section class="simulator-box">
    <h2 class="section-title">🔌 লাইভ ক্লায়েন্ট স্টোর সিমুলেটর (Live Store Demo)</h2>
    <p style="color:var(--text-muted); font-size:14px;">নিচের যেকোনো বুকস্টোরে ক্লিক করুন এবং দেখুন কীভাবে বটটি নিমেষেই ওই নির্দিষ্ট স্টোরের জন্য নিজেকে রূপান্তর করে এবং অন্য সব প্রতিদ্বন্দ্বী দোকানকে সম্পূর্ণ হাইড করে দেয়:</p>

    <div class="store-selector" id="store-selector">
      <button class="store-pill active" data-id="ruhama" onclick="selectStore('ruhama')">🕌 রূহামা শপ (Ruhama)</button>
      <button class="store-pill" data-id="aladaboi" onclick="selectStore('aladaboi')">📖 আলাদা বই (AladaBoi)</button>
      <button class="store-pill" data-id="guardian" onclick="selectStore('guardian')">🛡️ গার্ডিয়ান পাবলিকেশনস (Guardian)</button>
      <button class="store-pill" data-id="oitijjhya" onclick="selectStore('oitijjhya')">🏛️ ঐতিহ্য প্রকাশনী (Oitijjhya)</button>
      <button class="store-pill" data-id="anyaprokash" onclick="selectStore('anyaprokash')">✨ অন্যপ্রকাশ (AnyaProkash)</button>
      <button class="store-pill" data-id="baatighar" onclick="selectStore('baatighar')">🏮 বাতিঘর (Baatighar)</button>
      <button class="store-pill" data-id="wafilife" onclick="selectStore('wafilife')">📚 ওয়াফিলাইফ (Wafilife)</button>
      <button class="store-pill" data-id="prothoma" onclick="selectStore('prothoma')">🔖 প্রথমা প্রকাশন (Prothoma)</button>
      <button class="store-pill" data-id="default" onclick="selectStore('default')">🤖 নিরপেক্ষ কম্প্যারেটর (All 21 Stores)</button>
    </div>

    <!-- Active Store Info -->
    <div class="store-preview-card" id="store-preview-card">
      <div class="store-header">
        <div class="store-avatar" id="sim-avatar" style="background:#059669;">🕌</div>
        <div class="store-meta">
          <h3 id="sim-name">রূহামা শপ AI সেলসম্যান</h3>
          <p id="sim-website">অফিসিয়াল ওয়েবসাইট: <a href="https://www.ruhamashop.com" target="_blank" id="sim-link">ruhamashop.com</a></p>
        </div>
      </div>
      <div class="exclusive-tag" id="sim-exclusive">🔒 Single-Store Exclusive: শুধুমাত্র রূহামা শপের বই ও স্টক দেখাবে</div>
      <p style="font-size:14px; color:#334155;" id="sim-greeting">"সালাম! রূহামা শপ-এর ভার্চুয়াল সেলসম্যানে আপনাকে স্বাগতম। আমাদের বুকস্টোর থেকে আপনার পছন্দের বইটি খুঁজে দিচ্ছি!"</p>

      <div style="margin-top:10px;">
        <span style="font-size:13px; font-weight:700; color:#0f172a;">উক্ত বুকস্টোরের জন্য ১ লাইনের স্ক্রিপ্ট কোড:</span>
        <div class="code-box">
          <code id="script-code">&lt;script src="http://localhost:5000/widget.js" data-merchant="ruhama" async&gt;&lt;/script&gt;</code>
          <button class="copy-btn" onclick="copyScriptCode()">📋 কোড কপি করুন</button>
        </div>
      </div>
    </div>
  </section>

  <!-- FACEBOOK MESSENGER SETUP GUIDE -->
  <section class="guide-box">
    <h2 class="section-title">💬 ফেসবুক পেজ মেসেঞ্জার বট সেটআপ করার নিয়ম (Pro Plan)</h2>
    <p style="color:var(--text-muted); font-size:14px; margin-bottom:20px;">বাংলাদেশে ৮০% এর বেশি বই ফেসবুক পেজের মেসেঞ্জারে বিক্রি হয়। যেকোনো বুকশপের ফেসবুক পেজে এই বট কানেক্ট করার সহজ ৩টি ধাপ:</p>

    <ol class="steps-list">
      <li>
        <strong>Meta for Developers-এ Webhook URL দিন:</strong><br>
        আপনার ক্লায়েন্টের ফেসবুক অ্যাপে গিয়ে নিচের Webhook URL-টি পেস্ট করুন:<br>
        <code style="background:#f1f5f9; padding:4px 8px; border-radius:6px; display:inline-block; margin-top:6px;" id="fb-webhook-url">http://localhost:5000/api/webhook/facebook?merchant=ruhama</code>
      </li>
      <li>
        <strong>Verify Token ভেরিফাই করুন:</strong><br>
        Meta Verify Token হিসেবে দিন: <code style="background:#f1f5f9; padding:2px 6px; border-radius:4px;">boibondhu_webhook_token</code>। সাথে সাথে ফেসবুক পেজটি আপনার সিস্টেমের সাথে ভেরিফাই হয়ে যাবে।
      </li>
      <li>
        <strong>ব্যবসায়ীর ফেসবুক ইনবক্সে সেলস শুরু!</strong><br>
        এখন যেকোনো কাস্টমার যখন ওই বুকশপের ফেসবুক পেজে নক দিয়ে বলবে "বেলা ফুরাবার আগে বইটার দাম কত?" বা "হতাশা কাটানোর ইসলামিক বই দিন"—বট স্বয়ংক্রিয়ভাবে ওই স্টোরের বই, লাইভ স্টক ও অর্ডার লিংক পাঠিয়ে কাস্টমারকে ক্লোজ করবে!
      </li>
    </ol>
  </section>
</div>

<script>
var merchantsData = {
  "ruhama": {
    "name": "রূহামা শপ AI সেলসম্যান",
    "avatar": "🕌",
    "color": "#059669",
    "website": "https://www.ruhamashop.com",
    "webtext": "ruhamashop.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র রূহামা শপের বই, স্টক ও দাম দেখাবে",
    "greeting": "সালাম! রূহামা শপ (ruhamashop.com)-এর ভার্চুয়াল সেলসম্যানে আপনাকে স্বাগতম। আমাদের বুকস্টোর থেকে আপনার পছন্দের বইটি খুঁজে দিচ্ছি!",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="ruhama" async><\\/script>'
  },
  "aladaboi": {
    "name": "আলাদা বই AI সেলসম্যান",
    "avatar": "📖",
    "color": "#2563eb",
    "website": "https://www.aladaboi.com",
    "webtext": "aladaboi.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র আলাদা বই-এর কালেকশন দেখাবে",
    "greeting": "সালাম! আলাদা বই (aladaboi.com)-এর স্মার্ট সেলসম্যান বলছি। আমাদের কালেকশন থেকে কী বই খুঁজছেন?",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="aladaboi" async><\\/script>'
  },
  "baatighar": {
    "name": "বাতিঘর ভার্চুয়াল সেলসম্যান",
    "avatar": "🏮",
    "color": "#d97706",
    "website": "https://baatighar.com",
    "webtext": "baatighar.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র বাতিঘর বুকশপের বই দেখাবে",
    "greeting": "নমস্কার/সালাম! বাতিঘর অনলাইন বুকশপে আপনাকে স্বাগতম। সাহিত্য, ইতিহাস বা গবেষণার কী বই পড়তে চান?",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="baatighar" async><\\/script>'
  },
  "wafilife": {
    "name": "ওয়াফিলাইফ AI সেলসম্যান",
    "avatar": "📚",
    "color": "#0891b2",
    "website": "https://www.wafilife.com",
    "webtext": "wafilife.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র ওয়াফিলাইফের ৬০ হাজার বই থেকে দেখাবে",
    "greeting": "সালাম! ওয়াফিলাইফে আপনাকে স্বাগতম। আমাদের ৬০ হাজার বইয়ের সমৃদ্ধ কালেকশন থেকে আপনার মনের মতো বই বেছে নিন!",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="wafilife" async><\\/script>'
  },
  "prothoma": {
    "name": "প্রথমা প্রকাশন সেলস অ্যাসিস্ট্যান্ট",
    "avatar": "🔖",
    "color": "#dc2626",
    "website": "https://prothoma.com",
    "webtext": "prothoma.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র প্রথমা প্রকাশনের বই দেখাবে",
    "greeting": "প্রথমা প্রকাশনে আপনাকে স্বাগতম। নতুন ও সেরা বইগুলো দেখতে কী বই খুঁজছেন লিখুন।",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="prothoma" async><\\/script>'
  },
  "guardian": {
    "name": "গার্ডিয়ান পাবলিকেশনস AI সেলসম্যান",
    "avatar": "🛡️",
    "color": "#0d9488",
    "website": "https://guardianpubs.com",
    "webtext": "guardianpubs.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র গার্ডিয়ান পাবলিকেশনসের বই ও সরাসরি API দেখাবে",
    "greeting": "সালাম! গার্ডিয়ান পাবলিকেশনসের অফিসিয়াল এআই সেলসম্যানে স্বাগতম। আমাদের প্রকাশিত সেরা বইগুলো খুঁজে দিচ্ছি!",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="guardian" async><\\/script>'
  },
  "oitijjhya": {
    "name": "ঐতিহ্য প্রকাশনী ভার্চুয়াল সেলসম্যান",
    "avatar": "🏛️",
    "color": "#b45309",
    "website": "https://oitijjhya.com",
    "webtext": "oitijjhya.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র ঐতিহ্য প্রকাশনীর বই ও দাম দেখাবে",
    "greeting": "নমস্কার/সালাম! ঐতিহ্য প্রকাশনীতে আপনাকে স্বাগতম। আমাদের সাহিত্যের বই সম্ভার থেকে কী বই খুঁজছেন?",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="oitijjhya" async><\\/script>'
  },
  "anyaprokash": {
    "name": "অন্যপ্রকাশ AI সেলস অ্যাসিস্ট্যান্ট",
    "avatar": "✨",
    "color": "#7c3aed",
    "website": "https://anyaprokash.com",
    "webtext": "anyaprokash.com",
    "exclusive": "🔒 Single-Store Exclusive: শুধুমাত্র অন্যপ্রকাশের বই ও Shopify দাম দেখাবে",
    "greeting": "অন্যপ্রকাশে স্বাগতম! হুমায়ূন আহমেদসহ জনপ্রিয় লেখকদের বইগুলো বেছে নিতে সাহায্য করছি।",
    "script": '<script src="' + window.location.origin + '/widget.js" data-merchant="anyaprokash" async><\\/script>'
  },
  "default": {
    "name": "বইবন্ধু AI (২১+ বুকশপ ও প্রকাশনী প্রাইস ফাইন্ডার)",
    "avatar": "🤖",
    "color": "#1e3a8a",
    "website": "/",
    "webtext": "২১টি অনলাইন বুকশপ ও প্রকাশনী কম্প্যারেটর",
    "exclusive": "⚖️ Neutral Comparator: ২১টি বুকশপ ও প্রকাশনীর মধ্যে সেরা ৩টি সর্বনিম্ন দাম তুলনা করবে",
    "greeting": "সালাম/নমস্কার! আমি বইবন্ধু—বাংলাদেশের ২১টি অনলাইন বুকশপ ও শীর্ষ প্রকাশনী থেকে যাচাই করে সবচেয়ে কম দাম ও সেরা ডিল বের করে দিতে প্রস্তুত।",
    "script": '<script src="' + window.location.origin + '/widget.js" async><\\/script>'
  }
};

function selectStore(id) {
  var d = merchantsData[id] || merchantsData["default"];
  document.querySelectorAll('.store-pill').forEach(function(p) {
    p.classList.toggle('active', p.getAttribute('data-id') === id);
  });
  document.getElementById('sim-avatar').textContent = d.avatar;
  document.getElementById('sim-avatar').style.background = d.color;
  document.getElementById('sim-name').textContent = d.name;
  document.getElementById('sim-link').href = d.website;
  document.getElementById('sim-link').textContent = d.webtext;
  document.getElementById('sim-exclusive').textContent = d.exclusive;
  document.getElementById('sim-greeting').textContent = '"' + d.greeting + '"';
  document.getElementById('script-code').textContent = d.script.replace(/<\\\\\\/script>/, '<\\/script>');
  document.getElementById('fb-webhook-url').textContent = window.location.origin + '/api/webhook/facebook?merchant=' + id;
}

function copyScriptCode() {
  var code = document.getElementById('script-code').textContent;
  navigator.clipboard.writeText(code).then(function() {
    alert('স্ক্রিপ্ট কোড কপি করা হয়েছে! আপনার ক্লায়েন্টের ওয়েবসাইটের </body> ট্যাগের ঠিক আগে বসিয়ে দিন।');
  });
}
</script>

<script src="/widget.js" async></script>
</body>
</html>
"""

# B2B ADMIN ANALYTICS & COD ORDERS DASHBOARD
ADMIN_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>বইবন্ধু AI - B2B অ্যানালিটিক্স ও অর্ডার ড্যাশবোর্ড</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --primary: #4338ca;
    --primary-light: #6366f1;
    --success: #059669;
    --danger: #dc2626;
    --warning: #d97706;
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #64748b;
    --border: #e2e8f0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Hind Siliguri', sans-serif; }
  body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
  .dash-container { max-width: 1200px; margin: 0 auto; }
  .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
  .header h1 { font-size: 24px; font-weight: 700; color: #1e1b4b; display: flex; align-items: center; gap: 8px; }
  .controls { display: flex; gap: 12px; align-items: center; }
  select, button { padding: 9px 14px; border-radius: 8px; border: 1px solid var(--border); font-size: 14px; outline: none; }
  select { background: #fff; cursor: pointer; }
  .btn-primary { background: var(--primary); color: #fff; border: none; cursor: pointer; font-weight: 600; }
  .btn-primary:hover { background: #3730a3; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .kpi-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  .kpi-title { font-size: 13px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-value { font-size: 28px; font-weight: 700; color: #0f172a; margin-top: 6px; }
  .kpi-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .tabs { display: flex; gap: 8px; border-bottom: 2px solid var(--border); margin-bottom: 20px; }
  .tab-btn { padding: 10px 18px; border: none; background: none; font-size: 15px; font-weight: 600; color: var(--muted); cursor: pointer; border-bottom: 3px solid transparent; margin-bottom: -2px; }
  .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .table-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
  th { background: #f1f5f9; padding: 12px 16px; font-weight: 600; color: #475569; }
  td { padding: 12px 16px; border-top: 1px solid var(--border); }
  tr:hover { background: #f8fafc; }
  .badge { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11.5px; font-weight: 600; }
  .badge-success { background: #ecfdf5; color: var(--success); }
  .badge-danger { background: #fef2f2; color: var(--danger); }
  .badge-warning { background: #fffbeb; color: var(--warning); }
  .stream-box { background: #0f172a; color: #f8fafc; border-radius: 12px; padding: 20px; font-family: monospace; font-size: 13px; max-height: 380px; overflow-y: auto; margin-top: 16px; }
</style>
</head>
<body>
<div class="dash-container">
  <div class="header">
    <div>
      <h1>📊 বইবন্ধু AI - B2B SaaS বিজনেস ইন্টেলিজেন্স ড্যাশবোর্ড</h1>
      <p style="color:var(--muted); font-size:13.5px; margin-top:3px;">রিয়েল-টাইম কাস্টমার ডিমান্ড, মিসড সেলস অ্যানালিটিক্স ও ক্যাশ-অন-ডেলিভারি ট্র্যাকিং</p>
    </div>
    <div class="controls">
      <select id="merchantFilter" onchange="loadDashboard()">
        <option value="all">সব মার্চেন্ট (All Stores)</option>
        <option value="neutral">সাধারণ ভিজিটর (Neutral)</option>
        <option value="ruhama">রূহামা শপ (Ruhama Shop)</option>
        <option value="aladaboi">আলাদা বই (AladaBoi)</option>
        <option value="baatighar">বাতিঘর (Baatighar)</option>
        <option value="wafilife">ওয়াফিলাইফ (Wafilife)</option>
      </select>
      <button class="btn-primary" onclick="loadDashboard()">🔄 রিফ্রেশ</button>
      <a href="/demo" target="_blank" style="text-decoration:none;"><button class="btn-primary" style="background:#059669;">🛍️ শপ ডেমো খুলুন</button></a>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-title">💬 মোট অনুসন্ধান ও চ্যাট</div>
      <div class="kpi-value" id="kpiSearches">0</div>
      <div class="kpi-sub" id="kpiChats">কনভারসেশন: 0 টি</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">🛒 মোট ক্যাশ অন ডেলিভারি অর্ডার</div>
      <div class="kpi-value" id="kpiOrders" style="color:var(--primary);">0</div>
      <div class="kpi-sub" id="kpiPending">পেন্ডিং অর্ডার: 0 টি</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">💰 মোট বিক্রয় আয় (GMV)</div>
      <div class="kpi-value" id="kpiRevenue" style="color:var(--success);">৳০</div>
      <div class="kpi-sub">সরাসরি চ্যাট উইজেট থেকে কনভার্শন</div>
    </div>
    <div class="kpi-card" style="border-left:4px solid var(--danger);">
      <div class="kpi-title" style="color:var(--danger);">🚨 হারানো বিক্রির সুযোগ (Lost Sales)</div>
      <div class="kpi-value" id="kpiLost" style="color:var(--danger);">0</div>
      <div class="kpi-sub">কাস্টমার চেয়েছে কিন্তু স্টকে ছিল না</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tabLost')">🚨 হারানো বিক্রির সুযোগ (Lost Sales)</button>
    <button class="tab-btn" onclick="switchTab('tabAffordable')">🏆 শীর্ষ ৫টি কম দামের বুকশপ</button>
    <button class="tab-btn" onclick="switchTab('tabOrders')">🛒 ক্যাশ অন ডেলিভারি অর্ডার (COD Orders)</button>
    <button class="tab-btn" onclick="switchTab('tabDemanded')">📈 সর্বাধিক জনপ্রিয় বই</button>
    <button class="tab-btn" onclick="switchTab('tabStreaming')">⚡ ২১টি শপের লাইভ স্ট্রিমিং টেস্ট (SSE)</button>
  </div>

  <!-- Tab 1: Lost Sales Opportunities -->
  <div id="tabLost" class="tab-content active">
    <div class="table-card">
      <div style="padding:16px; border-bottom:1px solid var(--border); background:#fff5f5;">
        <h3 style="color:#991b1b; font-size:16px;">🚨 শপ মালিকের জন্য জরুরি অ্যালার্ট: হারানো বিক্রির সুযোগ</h3>
        <p style="font-size:13px; color:#7f1d1d; margin-top:2px;">যেসব বই কাস্টমাররা ইনবক্সে চেয়েছে কিন্তু আপনার স্টোরে ছিল না। দ্রুত এই বইগুলো সংগ্রহ করলে এই সেলসগুলো পাওয়া যাবে!</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>বই বা লেখকের নাম</th>
            <th>কাস্টমার রিকোয়েস্ট সংখ্যা</th>
            <th>কারণ (Status)</th>
            <th>অ্যাকশন</th>
          </tr>
        </thead>
        <tbody id="lostSalesBody">
          <tr><td colspan="4" style="text-align:center; color:var(--muted);">লোড হচ্ছে...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab 1b: Top Affordable Bookstores Leaderboard -->
  <div id="tabAffordable" class="tab-content">
    <div class="table-card">
      <div style="padding:16px; border-bottom:1px solid var(--border); background:#f0fdf4;">
        <h3 style="color:#166534; font-size:16px;">🏆 সবচেয়ে কম দাম দেওয়া শীর্ষ ৫টি বুকশপ (Market Price Intelligence)</h3>
        <p style="font-size:13px; color:#14532d; margin-top:2px;">আমাদের লাইভ স্ক্র্যাপিং অ্যালগরিদম ট্র্যাক করছে কোন ৫টি বুকশপ নিয়মিত সবচেয়ে কম দামে বই বিক্রি করে। এদের ডেটা দ্রুত প্রদর্শনের জন্য আলাদাভাবে অপটিমাইজ করা হচ্ছে!</p>
      </div>
      <table>
        <thead>
          <tr>
            <th># রেঙ্ক</th>
            <th>বুকশপের নাম</th>
            <th>১ম সর্বনিম্ন হওয়ার রেকর্ড</th>
            <th>শীর্ষ ৩-এ থাকার হার</th>
            <th>গড় রেঙ্ক</th>
            <th>গড় বিক্রয়মূল্য</th>
            <th>প্রি-ক্যাশ স্ট্যাটাস</th>
          </tr>
        </thead>
        <tbody id="affordableStoresBody">
          <tr><td colspan="7" style="text-align:center; color:var(--muted);">লোড হচ্ছে...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab 2: COD Orders -->
  <div id="tabOrders" class="tab-content">
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>অর্ডার আইডি</th>
            <th>তারিখ ও সময়</th>
            <th>বইয়ের নাম</th>
            <th>গ্রাহকের নাম ও ফোন</th>
            <th>ঠিকানা ও জেলা</th>
            <th>মোট টাকা</th>
            <th>স্ট্যাটাস</th>
          </tr>
        </thead>
        <tbody id="ordersBody">
          <tr><td colspan="7" style="text-align:center; color:var(--muted);">কোনো অর্ডার পাওয়া যায়নি</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab 3: Demanded Books -->
  <div id="tabDemanded" class="tab-content">
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>অনুসন্ধান করা বই / বিষয়</th>
            <th>চাহিদা (সার্চ সংখ্যা)</th>
            <th>ক্যাটাগরি</th>
          </tr>
        </thead>
        <tbody id="demandedBody">
          <tr><td colspan="4" style="text-align:center; color:var(--muted);">লোড হচ্ছে...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab 4: SSE Progressive Streaming Console -->
  <div id="tabStreaming" class="tab-content">
    <div class="table-card" style="padding:20px;">
      <h3 style="margin-bottom:12px;">⚡ ২১টি বুকশপে প্রগ্রেসিভ লাইভ স্ক্র্যাপিং টেস্ট (Server-Sent Events)</h3>
      <div style="display:flex; gap:10px; margin-bottom:16px;">
        <input type="text" id="streamInput" placeholder="বইয়ের নাম লিখুন (যেমন: প্যারাডক্সিক্যাল সাজিদ)" style="flex:1; padding:10px 14px; border:1px solid var(--border); border-radius:8px;" value="প্যারাডক্সিক্যাল সাজিদ">
        <button class="btn-primary" onclick="startStreamTest()">রিয়েল-টাইম স্ক্র্যাপিং শুরু করুন 🚀</button>
      </div>
      <div id="streamProgress" style="font-size:13.5px; font-weight:600; color:var(--primary); margin-bottom:8px;"></div>
      <div class="stream-box" id="streamLog">// লাইভ স্ক্র্যাপিং রেজাল্ট এখানে ক্রমান্বয়ে স্ট্রিম হবে...</div>
    </div>
  </div>
</div>

<script>
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}

async function loadDashboard() {
  const merchant = document.getElementById('merchantFilter').value;
  try {
    const res = await fetch('/api/analytics/summary?merchant_id=' + merchant);
    const data = await res.json();
    
    // KPI Updates
    document.getElementById('kpiSearches').textContent = data.total_searches || 0;
    document.getElementById('kpiChats').textContent = 'কনভারসেশন: ' + (data.total_chats || 0) + ' টি';
    document.getElementById('kpiOrders').textContent = (data.order_stats && data.order_stats.total_orders) || 0;
    document.getElementById('kpiPending').textContent = 'পেন্ডিং অর্ডার: ' + ((data.order_stats && data.order_stats.pending_orders) || 0) + ' টি';
    document.getElementById('kpiRevenue').textContent = '৳' + ((data.order_stats && data.order_stats.total_revenue) || 0).toLocaleString();
    document.getElementById('kpiLost').textContent = (data.lost_sales && data.lost_sales.length) || 0;

    // Lost Sales Table
    const lostTbody = document.getElementById('lostSalesBody');
    if (data.lost_sales && data.lost_sales.length > 0) {
      lostTbody.innerHTML = data.lost_sales.map(ls => `
        <tr>
          <td><strong>${ls.book}</strong></td>
          <td><span class="badge badge-danger">${ls.count} বার খোঁজা হয়েছে</span></td>
          <td>${ls.reason === 'out_of_stock' ? '<span class="badge badge-warning">স্টক শেষ</span>' : '<span class="badge badge-danger">ক্যাটালগে নেই</span>'}</td>
          <td><button class="btn-primary" style="padding:4px 8px; font-size:11px;" onclick="alert('বইটি সংগ্রহের জন্য সাপ্লায়ারকে নোট পাঠানো হয়েছে!')">পণ্য সংগ্রহ করুন 📦</button></td>
        </tr>
      `).join('');
    } else {
      lostTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--muted); padding:20px;">🎉 দারুণ! কোনো মিসড সেলস পাওয়া যায়নি।</td></tr>';
    }

    // Demanded Books Table
    const demTbody = document.getElementById('demandedBody');
    if (data.top_searches && data.top_searches.length > 0) {
      demTbody.innerHTML = data.top_searches.map((s, idx) => `
        <tr>
          <td>#${idx + 1}</td>
          <td><strong>${s.query}</strong></td>
          <td><span class="badge badge-success">${s.count} বার</span></td>
          <td>বই / লেখক অনুসন্ধান</td>
        </tr>
      `).join('');
    } else {
      demTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--muted); padding:20px;">কোনো ডেটা নেই</td></tr>';
    }

    // Top Affordable Stores Leaderboard Table
    const affTbody = document.getElementById('affordableStoresBody');
    if (data.top_affordable_stores && data.top_affordable_stores.length > 0) {
      const medals = ['🥇 ১ম', '🥈 ২য়', '🥉 ৩য়', '🎖️ ৪র্থ', '⭐ ৫ম'];
      affTbody.innerHTML = data.top_affordable_stores.map((st, idx) => `
        <tr>
          <td><strong style="color:var(--primary);">${medals[idx] || '#' + (idx + 1)}</strong></td>
          <td><strong>${st.store_name}</strong></td>
          <td><span class="badge badge-success">${st.rank_1_wins} বার</span></td>
          <td><span class="badge badge-warning">${st.top_3_count} বার</span></td>
          <td>${st.avg_rank}</td>
          <td><strong style="color:#047857;">৳${st.avg_price}</strong></td>
          <td><span class="badge badge-success">✅ প্রি-ক্যাশ ও ফাস্ট-টায়ার</span></td>
        </tr>
      `).join('');
    } else {
      affTbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--muted); padding:20px;">ডেটা লোড হচ্ছে...</td></tr>';
    }

    // Orders Table
    loadOrders(merchant);

  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

async function loadOrders(merchant) {
  try {
    const res = await fetch('/api/salesman/orders?merchant_id=' + merchant);
    const data = await res.json();
    const tbody = document.getElementById('ordersBody');
    if (data.orders && data.orders.length > 0) {
      tbody.innerHTML = data.orders.map(o => `
        <tr>
          <td><strong style="color:var(--primary);">${o.order_id}</strong></td>
          <td style="font-size:12px; color:var(--muted);">${o.created_at}</td>
          <td><strong>${o.book_title}</strong></td>
          <td><div>${o.customer_name}</div><div style="font-size:12px; color:var(--muted);">${o.customer_phone}</div></td>
          <td style="font-size:12.5px;">${o.customer_address}, ${o.district || ''}</td>
          <td><strong style="color:var(--success);">৳${o.total_amount}</strong></td>
          <td><span class="badge badge-warning">${o.status}</span></td>
        </tr>
      `).join('');
    } else {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--muted); padding:20px;">এখনো কোনো ক্যাশ-অন-ডেলিভারি অর্ডার হয়নি। চ্যাট উইজেট থেকে অর্ডার ট্রাই করুন!</td></tr>';
    }
  } catch(e) {
    console.error('Order fetch error:', e);
  }
}

// Real-Time SSE Stream Tester
function startStreamTest() {
  const query = document.getElementById('streamInput').value.trim();
  if (!query) return;

  const logBox = document.getElementById('streamLog');
  const prog = document.getElementById('streamProgress');
  logBox.innerHTML = `[${new Date().toLocaleTimeString()}] স্ক্র্যাপিং কানেকশন শুরু হচ্ছে...\\n`;
  prog.textContent = '২১টি অনলাইন শপে অনুসন্ধান শুরু হয়েছে...';

  const evtSource = new EventSource('/api/compare/stream?query=' + encodeURIComponent(query));
  
  evtSource.addEventListener('store_result', function(e) {
    const data = JSON.parse(e.data);
    const statusText = data.has_match ? `✅ পাওয়া গেছে (${data.items.length} টি বই)` : `○ কোনো রেজাল্ট নেই`;
    logBox.innerHTML += `[${data.completed}/${data.total}] [${data.store}] -> ${statusText}\\n`;
    prog.textContent = `অগ্রগতি: ${data.completed}/${data.total}টি শপ স্ক্র্যাপ সম্পন্ন...`;
    logBox.scrollTop = logBox.scrollHeight;
  });

  evtSource.addEventListener('complete', function(e) {
    const data = JSON.parse(e.data);
    logBox.innerHTML += `\\n🎉 স্ক্র্যাপিং সফলভাবে সম্পন্ন!\\nমোট শপ যাচাই: ${data.stores_searched}টি, মোট বই পাওয়া গেছে: ${data.total_found}টি।\\n`;
    if (data.top_5 && data.top_5.length > 0) {
      logBox.innerHTML += `\\n--- 🥇 শীর্ষ সর্বনিম্ন দামের তালিকা ---\\n`;
      data.top_5.forEach(d => {
        logBox.innerHTML += `* ${d.badge} [${d.store}] -> ৳${d.price} (${d.stock_text})\\n`;
      });
    }
    prog.textContent = `✅ সম্পন্ন! মোট ${data.total_found}টি বই পাওয়া গেছে।`;
    evtSource.close();
  });

  evtSource.onerror = function() {
    logBox.innerHTML += `\\n[কানেকশন বন্ধ হয়েছে]\\n`;
    evtSource.close();
  };
}

// Initial load
window.addEventListener('DOMContentLoaded', loadDashboard);
</script>
</body>
</html>
"""


@app.route("/merchant")
def merchant_portal():
    return render_template_string(MERCHANT_PORTAL_TEMPLATE)


@app.route("/api/merchant/config", methods=["GET"])
def api_merchant_config():
    merchant_id = request.args.get("id") or request.args.get("merchant_id")
    return jsonify(get_merchant(merchant_id))


@app.route("/api/merchant/list", methods=["GET"])
def api_merchant_list():
    return jsonify(list_merchants())


@app.route("/api/webhook/facebook", methods=["GET", "POST"])
def facebook_webhook():
    merchant_id = request.args.get("merchant", "default")
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token in ["boibondhu_webhook_token", "123456"]:
            return challenge or "", 200
        return "Forbidden", 403

    data = request.get_json(silent=True) or {}
    entries = data.get("entry", [])
    for entry in entries:
        messaging = entry.get("messaging", [])
        for msg_event in messaging:
            sender_id = msg_event.get("sender", {}).get("id")
            msg_text = msg_event.get("message", {}).get("text")
            if sender_id and msg_text:
                salesman_agent.chat(msg_text, session_id=f"fb_{sender_id}", merchant_id=merchant_id)
    return "EVENT_RECEIVED", 200


@app.route("/api/compare/stream", methods=["GET"])
def api_compare_stream():
    """
    Server-Sent Events (SSE) progressive streaming endpoint.
    Emits store_result events as each shop scraper finishes (Rokomari/Wafilife in 1-2s).
    """
    query = request.args.get("query", "").strip()
    category = request.args.get("category", "all")
    target_store = request.args.get("store") or request.args.get("merchant")

    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    def event_stream():
        for event in stream_compare_books(query, category=category, target_store=target_store):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.route("/api/salesman/order", methods=["POST", "OPTIONS"])
def api_salesman_order():
    """
    In-Chat Cash-on-Delivery (COD) Order placement API.
    Creates and records order to orders.sqlite3 with instant ID and delivery ETA.
    """
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    book_title = data.get("book_title", "").strip()
    customer_name = data.get("customer_name", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    customer_address = data.get("customer_address", "").strip()
    merchant_id = data.get("merchant_id") or "neutral"
    book_author = data.get("book_author", "")
    price = data.get("price", 0)
    quantity = data.get("quantity", 1)
    district = data.get("district", "ঢাকা")
    notes = data.get("notes", "")

    res = create_order(
        book_title=book_title,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_address=customer_address,
        merchant_id=merchant_id,
        book_author=book_author,
        price=price,
        quantity=quantity,
        district=district,
        notes=notes
    )

    if res.get("status") == "success":
        # Track confirmed sale in analytics
        track_search(f"ORDER: {book_title}", merchant_id=merchant_id, category="Order Placed", books_found=1)
        return jsonify(res), 200
    else:
        return jsonify(res), 400


@app.route("/api/salesman/orders", methods=["GET"])
def api_salesman_orders():
    """Returns order history and statistics for merchant dashboard."""
    merchant_id = request.args.get("merchant_id")
    limit = int(request.args.get("limit", 50))
    orders = get_orders(merchant_id=merchant_id, limit=limit)
    stats = get_order_stats(merchant_id=merchant_id)
    return jsonify({"orders": orders, "stats": stats})


@app.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    """Returns aggregate BI metrics, lost sales, and top search queries."""
    merchant_id = request.args.get("merchant_id")
    summary = get_analytics_summary(merchant_id=merchant_id)
    order_stats = get_order_stats(merchant_id=merchant_id)
    summary["order_stats"] = order_stats
    return jsonify(summary)


@app.route("/admin/analytics")
def admin_analytics_page():
    """Interactive B2B SaaS Merchant Analytics & COD Order Dashboard."""
    return render_template_string(ADMIN_DASHBOARD_HTML)


@app.route("/api/salesman/chat", methods=["POST", "OPTIONS"])
def api_salesman_chat():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id")
    api_key = data.get("api_key")
    merchant_id = data.get("merchant_id") or request.args.get("merchant_id") or "neutral"

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Track message in analytics
    track_chat_message(message, merchant_id=merchant_id, session_id=session_id or "")

    result = salesman_agent.chat(message, session_id=session_id, api_key=api_key, merchant_id=merchant_id)

    # Track search analytics
    books_count = len(result.get("books", []))
    track_search(message, merchant_id=merchant_id, category=result.get("category", ""), books_found=books_count)

    return jsonify(result)


@app.route("/api/salesman/credits", methods=["GET"])
def api_salesman_credits():
    session_id = request.args.get("session_id")
    _, sess = salesman_agent.sessions.get_session(session_id)
    return jsonify({
        "session_id": session_id,
        "credits": sess["credits"]
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
