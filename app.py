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
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>বইয়ের লাইভ দাম তুলনা | Real-time Book Price Comparator</title>
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #1e3a8a;
  --primary-light: #3b82f6;
  --gold: #f59e0b;
  --silver: #94a3b8;
  --bronze: #d97706;
  --green: #10b981;
  --red: #ef4444;
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --text: #1e293b;
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
  background: linear-gradient(135deg, #1e3a8a, #0f172a);
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
  font-weight: 500;
}
h1 { font-size: 32px; font-weight: 700; margin-bottom: 8px; }
.subtitle { color: #cbd5e1; font-size: 16px; max-width: 600px; margin: 0 auto; }

.container {
  max-width: 1100px;
  margin: -25px auto 0;
  padding: 0 16px;
}
.search-box {
  background: white;
  padding: 16px;
  border-radius: 16px;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.08);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.search-form {
  display: flex;
  gap: 10px;
}
.search-input {
  flex: 1;
  padding: 14px 20px;
  font-size: 16px;
  border: 1.5px solid var(--border);
  border-radius: 10px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}
.search-input:focus { border-color: var(--primary-light); }
.search-btn {
  background: var(--primary);
  color: white;
  border: none;
  padding: 0 28px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 10px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.2s;
}
.search-btn:hover { background: #172554; }

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 14px;
}
.filter-label { color: var(--text-muted); font-weight: 500; }
.filter-btn {
  background: #f1f5f9;
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  color: var(--text);
  font-weight: 500;
  transition: all 0.2s;
  text-decoration: none;
}
.filter-btn.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
  font-size: 13px;
}
.tag-item {
  background: #e2e8f0;
  color: #334155;
  padding: 3px 10px;
  border-radius: 6px;
  text-decoration: none;
}
.tag-item:hover { background: #cbd5e1; }

/* Top 3 Showcase Section */
.top-section {
  margin-top: 36px;
}
.section-title {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.top-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
  gap: 16px;
}
.deal-card {
  background: white;
  border-radius: 14px;
  padding: 20px;
  border: 2px solid var(--border);
  position: relative;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  transition: transform 0.2s, box-shadow 0.2s;
}
.deal-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 20px rgba(0,0,0,0.06);
}
.deal-card.rank-1 { border-color: var(--gold); background: linear-gradient(180deg, #fffbeb, #ffffff); }
.deal-card.rank-2 { border-color: var(--silver); background: linear-gradient(180deg, #f8fafc, #ffffff); }
.deal-card.rank-3 { border-color: var(--bronze); background: linear-gradient(180deg, #fef3c7, #ffffff); }
.deal-card.rank-4 { border-color: #3b82f6; background: linear-gradient(180deg, #eff6ff, #ffffff); }
.deal-card.rank-5 { border-color: #8b5cf6; background: linear-gradient(180deg, #f5f3ff, #ffffff); }
.deal-card.all-card { border-color: var(--border); background: #ffffff; }
.deal-card.all-card.is-in-stock { border-top: 3px solid #10b981; }
.deal-card.all-card.is-out-of-stock { border-top: 3px solid #ef4444; opacity: 0.92; }
.all-card .rank-badge { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

.rank-badge {
  position: absolute;
  top: -12px;
  left: 16px;
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
.rank-1 .rank-badge { background: var(--gold); color: #78350f; }
.rank-2 .rank-badge { background: var(--silver); color: #1e293b; }
.rank-3 .rank-badge { background: var(--bronze); color: white; }
.rank-4 .rank-badge { background: #3b82f6; color: white; }
.rank-5 .rank-badge { background: #8b5cf6; color: white; }

.deal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-top: 6px;
  margin-bottom: 10px;
}
.store-tag {
  background: #f1f5f9;
  color: var(--primary);
  font-size: 12px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
}
.store-type {
  font-size: 11px;
  color: var(--text-muted);
}
.deal-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.deal-author {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.price-area {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.current-price {
  font-size: 26px;
  font-weight: 800;
  color: #047857;
}
.reg-price {
  font-size: 14px;
  color: var(--text-muted);
  text-decoration: line-through;
}
.stock-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  display: inline-block;
  margin-bottom: 10px;
}
.in-stock { background: #dcfce7; color: #15803d; }
.out-of-stock { background: #fee2e2; color: #b91c1c; }

.buy-btn {
  display: block;
  text-align: center;
  background: var(--primary);
  color: white;
  padding: 10px;
  border-radius: 8px;
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  margin-top: 12px;
  transition: opacity 0.2s;
}
.buy-btn:hover { opacity: 0.9; }

/* Table View */
.table-section { margin-top: 40px; }
.table-card {
  background: white;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: 0 4px 6px rgba(0,0,0,0.02);
}
table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
th {
  background: #f8fafc;
  padding: 14px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  vertical-align: middle;
}
tr:hover td { background: #fdfefe; }
.table-link {
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
}
.table-link:hover { text-decoration: underline; }

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-icon { font-size: 48px; margin-bottom: 10px; }

@media (max-width: 600px) {
  .search-form { flex-direction: column; }
  .search-btn { padding: 12px; }
  table { display: block; overflow-x: auto; }
}
</style>
</head>
<body>

<header>
  <div class="header-badge">🇧🇩 ২১টি জনপ্রিয় অনলাইন বুকশপ ও প্রকাশনীতে লাইভ দাম পরীক্ষা</div>
  <h1>বইয়ের লাইভ দাম তুলনা</h1>
  <p class="subtitle">Rokomari, Wafilife, Guardian Publications, Oitijjhya, AnyaProkash, Anindya, PBS, Baatighar, Prothoma, Adarsha, Ruhama, AladaBoi, BDBooks, Kitabghor, Maktabatul Ashraf, BoiBitan, Bengal Publications সহ ২১টি শপ থেকে একই সাথে লাইভ দাম ও স্টক চেক করুন।</p>
  <div style="margin-top: 18px;">
    <a href="/salesman" style="display: inline-flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.2); color: white; padding: 10px 22px; border-radius: 999px; text-decoration: none; font-weight: 600; font-size: 15px; backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.35); box-shadow: 0 4px 12px rgba(0,0,0,0.15); transition: all 0.2s;">
      🤖 বইবন্ধু AI সেলসম্যান-এর সাথে কথা বলুন ↗
    </a>
    <a href="/merchant" style="display: inline-flex; align-items: center; gap: 8px; background: #059669; color: white; padding: 10px 20px; border-radius: 999px; text-decoration: none; font-weight: 600; font-size: 15px; box-shadow: 0 4px 12px rgba(5,150,105,0.3); transition: all 0.2s; margin-left: 8px;">
      💼 বুকশপ B2B SaaS পোর্টাল ↗
    </a>
    <a href="/demo" style="display: inline-flex; align-items: center; gap: 8px; background: #2563eb; color: white; padding: 10px 20px; border-radius: 999px; text-decoration: none; font-weight: 600; font-size: 15px; box-shadow: 0 4px 12px rgba(37,99,235,0.3); transition: all 0.2s; margin-left: 8px;">
      🎯 লাইভ স্টোর সুইচার ডেমো ↗
    </a>
  </div>
</header>

<div class="container">
  <div class="search-box">
    <form class="search-form" method="GET" action="/">
      <input type="text" name="q" class="search-input" placeholder="বইয়ের নাম লিখুন (যেমন: বেলা ফুরাবার আগে, প্যারাডক্সিক্যাল সাজিদ, সীরাত, অপেক্ষা...)" value="{{ query }}" required>
      <input type="hidden" name="category" value="{{ category }}">
      <button type="submit" class="search-btn">🔍 দাম খুঁজুন</button>
    </form>
    
    <div class="filters">
      <span class="filter-label">ফিল্টার:</span>
      <a href="/?q={{ query }}&category=all" class="filter-btn {{ 'active' if category == 'all' else '' }}">সব শপ ও প্রকাশনী (২১টি)</a>
      <a href="/?q={{ query }}&category=islamic" class="filter-btn {{ 'active' if category == 'islamic' else '' }}">🕌 ইসলামিক ও প্রকাশনী (৮টি)</a>
      <a href="/?q={{ query }}&category=general" class="filter-btn {{ 'active' if category == 'general' else '' }}">📚 জেনারেল, সাহিত্য ও প্রকাশনী (১৩টি)</a>
    </div>

    <div class="tags">
      <span class="filter-label">পপুলার বই:</span>
      <a href="/?q=বেলা ফুরাবার আগে&category={{ category }}" class="tag-item">বেলা ফুরাবার আগে</a>
      <a href="/?q=প্যারাডক্সিক্যাল সাজিদ&category={{ category }}" class="tag-item">প্যারাডক্সিক্যাল সাজিদ</a>
      <a href="/?q=রি-থিংক&category={{ category }}" class="tag-item">রি-থিংক</a>
      <a href="/?q=অপেক্ষা&category={{ category }}" class="tag-item">অপেক্ষা</a>
      <a href="/?q=সীরাত&category={{ category }}" class="tag-item">সীরাত</a>
    </div>
  </div>

  {% if query %}
    {% if total_found > 0 %}
      <!-- TOP 5 LOWEST PRICES -->
      <section class="top-section">
        <h2 class="section-title">🏆 স্টকে থাকা সেরা ৫টি কম দাম (Top 5 Lowest Prices)</h2>
        <div class="top-grid">
          {% for deal in top_5 %}
            <div class="deal-card rank-{{ deal.rank }}">
              <div class="rank-badge">{{ deal.badge }}</div>
              <div class="deal-header">
                <div>
                  <span class="store-tag">{{ deal.store }}</span>
                  <span class="store-type">• {{ deal.store_type }}</span>
                </div>
                <span class="stock-pill {{ 'in-stock' if deal.in_stock else 'out-of-stock' }}">
                  {{ deal.stock_text }}
                </span>
              </div>

              <!-- BOOK PROFILE: COVER IMG + WRITER + PUBLICATION + TOPIC -->
              <div style="display:flex; gap:12px; margin-bottom:12px; align-items:flex-start;">
                {% if deal.image %}
                  <img src="{{ deal.image }}" alt="{{ deal.title }}" style="width:64px; height:92px; object-fit:cover; border-radius:6px; box-shadow:0 3px 8px rgba(0,0,0,0.12); flex-shrink:0;" onerror="this.style.display='none'">
                {% else %}
                  <div style="width:64px; height:92px; background:#eff6ff; color:#1d4ed8; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:28px; flex-shrink:0;">📖</div>
                {% endif %}
                <div style="flex:1; min-width:0;">
                  <div class="deal-title" title="{{ deal.title }}">{{ deal.title }}</div>
                  {% if deal.author %}<div class="deal-author" style="margin-bottom:3px;">👤 <strong>লেখক:</strong> {{ deal.author }}</div>{% endif %}
                  {% if deal.publisher %}<div style="font-size:12px; color:var(--text-muted); margin-bottom:3px;">🏢 <strong>প্রকাশনী:</strong> {{ deal.publisher }}</div>{% endif %}
                  {% if deal.subject %}<div style="font-size:11px; color:#2563eb; background:#eff6ff; display:inline-block; padding:1px 8px; border-radius:4px; margin-top:2px;">🏷️ {{ deal.subject }}</div>{% endif %}
                </div>
              </div>

              <div class="price-area">
                <div>
                  {% if deal.regular_price and deal.regular_price > deal.price %}
                    <div class="reg-price">৳{{ deal.regular_price }}</div>
                  {% endif %}
                  <div class="current-price">৳{{ deal.price if deal.price else 'তথ্য নেই' }}</div>
                </div>
                <a href="{{ deal.url }}" target="_blank" rel="noopener noreferrer" class="buy-btn">ওয়েবসাইটে যান ↗</a>
              </div>
            </div>
          {% endfor %}
        </div>
      </section>

      <!-- ALL STORES FULL LIST: CARD GRID VIEW (MATCHING TOP 5) & TABLE VIEW TOGGLE -->
      <section class="table-section">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:18px;">
          <h2 class="section-title" style="margin-bottom:0;">📊 সব বুকশপের পূর্ণাঙ্গ তালিকা ({{ total_found }}টি অপশন পাওয়া গেছে)</h2>
          <div style="display:flex; gap:6px; background:#e2e8f0; padding:3px; border-radius:8px;">
            <button id="btnGridView" onclick="switchFullListView('grid')" style="padding:6px 14px; border:none; border-radius:6px; font-size:13px; font-weight:700; cursor:pointer; background:#ffffff; color:#1e1b4b; box-shadow:0 1px 3px rgba(0,0,0,0.1);">🎴 কার্ড ভিউ (Grid)</button>
            <button id="btnTableView" onclick="switchFullListView('table')" style="padding:6px 14px; border:none; border-radius:6px; font-size:13px; font-weight:600; cursor:pointer; background:transparent; color:#64748b;">📋 টেবিল ভিউ (Table)</button>
          </div>
        </div>

        <!-- 1. FULL LIST CARD GRID VIEW (IDENTICAL TO TOP 5 CARDS) -->
        <div id="allCardsView" class="top-grid">
          {% for item in all_results %}
            <div class="deal-card all-card {{ 'is-in-stock' if item.in_stock else 'is-out-of-stock' }}">
              <div class="rank-badge">#{{ loop.index }}</div>
              <div class="deal-header">
                <div>
                  <span class="store-tag">{{ item.store }}</span>
                  <span class="store-type">• {{ item.store_type }}</span>
                </div>
                <span class="stock-pill {{ 'in-stock' if item.in_stock else 'out-of-stock' }}">
                  {{ item.stock_text }}
                </span>
              </div>

              <!-- BOOK PROFILE: COVER IMG + WRITER + PUBLICATION + TOPIC -->
              <div style="display:flex; gap:12px; margin-bottom:12px; align-items:flex-start;">
                {% if item.image %}
                  <img src="{{ item.image }}" alt="{{ item.title }}" style="width:64px; height:92px; object-fit:cover; border-radius:6px; box-shadow:0 3px 8px rgba(0,0,0,0.12); flex-shrink:0;" onerror="this.style.display='none'">
                {% else %}
                  <div style="width:64px; height:92px; background:#eff6ff; color:#1d4ed8; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:28px; flex-shrink:0;">📖</div>
                {% endif %}
                <div style="flex:1; min-width:0;">
                  <div class="deal-title" title="{{ item.title }}">{{ item.title }}</div>
                  {% if item.author %}<div class="deal-author" style="margin-bottom:3px;">👤 <strong>লেখক:</strong> {{ item.author }}</div>{% endif %}
                  {% if item.publisher %}<div style="font-size:12px; color:var(--text-muted); margin-bottom:3px;">🏢 <strong>প্রকাশনী:</strong> {{ item.publisher }}</div>{% endif %}
                  {% if item.subject %}<div style="font-size:11px; color:#2563eb; background:#eff6ff; display:inline-block; padding:1px 8px; border-radius:4px; margin-top:2px;">🏷️ {{ item.subject }}</div>{% endif %}
                </div>
              </div>

              <div class="price-area">
                <div>
                  {% if item.regular_price and item.regular_price > item.price %}
                    <div class="reg-price">৳{{ item.regular_price }}</div>
                  {% endif %}
                  <div class="current-price">৳{{ item.price if item.price else 'তথ্য নেই' }}</div>
                </div>
                <div style="display:flex; gap:6px;">
                  {% if item.url %}
                    <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="buy-btn">ওয়েবসাইটে যান ↗</a>
                  {% endif %}
                  <button type="button" class="buy-btn bb-order-trigger-btn" style="background:#059669; border:none; cursor:pointer;" data-book="{{ item.title | urlencode }}" data-price="{{ item.price or 0 }}" data-author="{{ item.author or item.store | urlencode }}">🛒 COD</button>
                </div>
              </div>
            </div>
          {% endfor %}
        </div>

        <!-- 2. FULL LIST SPREADSHEET TABLE VIEW (TOGGLEABLE) -->
        <div id="allTableView" class="table-card" style="display:none; margin-top:16px;">
          <table>
            <thead>
              <tr>
                <th style="width:65px;">ছবি</th>
                <th>বুকশপ ও প্রকাশনী</th>
                <th>বইয়ের নাম, লেখক ও বিষয়</th>
                <th>দাম</th>
                <th>স্টক স্ট্যাটাস</th>
                <th>অ্যাকশন</th>
              </tr>
            </thead>
            <tbody>
              {% for item in all_results %}
                <tr>
                  <td>
                    {% if item.image %}
                      <img src="{{ item.image }}" alt="{{ item.title }}" style="width:48px; height:68px; object-fit:cover; border-radius:4px; box-shadow:0 2px 5px rgba(0,0,0,0.1);" onerror="this.style.display='none'">
                    {% else %}
                      <div style="width:48px; height:68px; background:#f1f5f9; border-radius:4px; display:flex; align-items:center; justify-content:center; font-size:20px;">📖</div>
                    {% endif %}
                  </td>
                  <td>
                    <strong>{{ item.store }}</strong><br>
                    {% if item.publisher %}<span style="font-size:12px; color:#475569;">🏢 {{ item.publisher }}</span><br>{% endif %}
                    <small style="color:var(--text-muted)">{{ item.store_type }}</small>
                  </td>
                  <td>
                    <strong>{{ item.title }}</strong>
                    {% if item.author %}<br><small style="color:var(--text-muted)">👤 লেখক: {{ item.author }}</small>{% endif %}
                    {% if item.subject %}<br><span style="font-size:11px; color:#2563eb; background:#eff6ff; padding:1px 6px; border-radius:3px; display:inline-block; margin-top:3px;">🏷️ {{ item.subject }}</span>{% endif %}
                  </td>
                  <td>
                    <strong style="color: #047857; font-size: 16px;">৳{{ item.price if item.price else 'N/A' }}</strong>
                    {% if item.regular_price and item.regular_price > item.price %}
                      <br><small style="text-decoration:line-through; color:var(--text-muted)">৳{{ item.regular_price }}</small>
                    {% endif %}
                  </td>
                  <td>
                    <span class="stock-pill {{ 'in-stock' if item.in_stock else 'out-of-stock' }}">
                      {{ item.stock_text }}
                    </span>
                  </td>
                  <td>
                    <a href="{{ item.url }}" target="_blank" rel="noopener noreferrer" class="table-link">কিনুন ↗</a>
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <script>
        function switchFullListView(view) {
          var cards = document.getElementById('allCardsView');
          var table = document.getElementById('allTableView');
          var btnGrid = document.getElementById('btnGridView');
          var btnTable = document.getElementById('btnTableView');
          if (view === 'grid') {
            cards.style.display = 'grid';
            table.style.display = 'none';
            btnGrid.style.background = '#ffffff';
            btnGrid.style.color = '#1e1b4b';
            btnGrid.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
            btnTable.style.background = 'transparent';
            btnTable.style.color = '#64748b';
            btnTable.style.boxShadow = 'none';
          } else {
            cards.style.display = 'none';
            table.style.display = 'block';
            btnTable.style.background = '#ffffff';
            btnTable.style.color = '#1e1b4b';
            btnTable.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
            btnGrid.style.background = 'transparent';
            btnGrid.style.color = '#64748b';
            btnGrid.style.boxShadow = 'none';
          }
        }
        </script>
      </section>
    {% else %}
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>“{{ query }}” এর জন্য কোনো ফলাফল পাওয়া যায়নি</h3>
        <p>বইয়ের সঠিক নাম লিখে পুনরায় চেষ্টা করুন।</p>
      </div>
    {% endif %}
  {% else %}
    <div class="empty-state">
      <div class="empty-icon">📖</div>
      <h3>যে কোনো বইয়ের নাম লিখে সার্চ করুন</h3>
      <p>আমরা ১৭টি অনলাইন বুকশপ থেকে সরাসরি রিয়েল-টাইম স্ক্র্যাপ করে সবচেয়ে কম দাম খুঁজে দেব।</p>
    </div>
  {% endif %}
</div>

<script src="/widget.js" async></script>
</body>
</html>
"""


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
@app.route("/")
def home():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "all")

    if not query:
        return render_template_string(
            HTML_TEMPLATE,
            query="",
            category=category,
            top_5=[],
            top_3=[],
            all_results=[],
            total_found=0
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
