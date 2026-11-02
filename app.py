import os
import sys
import json
import sqlite3
import time
from flask import Flask, request, jsonify, render_template_string, Response
from comparator_engine import compare_books, STORE_REGISTRY
from salesman.salesman_engine import salesman_agent
from salesman.merchant_registry import get_merchant, list_merchants, register_custom_merchant
from cover_resolver import resolve_book_cover, resolve_covers_for_books, set_cached_image

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

      <!-- ALL STORES COMPARISON TABLE -->
      <section class="table-section">
        <h2 class="section-title">📊 সব বুকশপের পূর্ণাঙ্গ তালিকা ({{ total_found }}টি অপশন পাওয়া গেছে)</h2>
        <div class="table-card">
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


@app.route("/api/salesman/chat", methods=["POST", "OPTIONS"])
def api_salesman_chat():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id")
    api_key = data.get("api_key")
    merchant_id = data.get("merchant_id") or request.args.get("merchant_id")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    result = salesman_agent.chat(message, session_id=session_id, api_key=api_key, merchant_id=merchant_id)
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
