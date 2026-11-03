import re
import time
import requests
from difflib import SequenceMatcher
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
}

TIMEOUT = 9


BN_DIGITS = {chr(0x09E6 + i): str(i) for i in range(10)}

def to_en_digits(s):
    if not s:
        return ""
    return "".join(BN_DIGITS.get(c, c) for c in str(s))

def extract_prices(val):
    """
    Extracts all numeric prices from any price string, properly handling:
    - Currency prefixes like Tk., Tk, ৳, BDT
    - Comma thousand separators: 1,250 -> 1250
    - Decimal cents/paisa: .00 or .50 -> truncated to integer (prevents Tk. 395.00 becoming 39500)
    - Bengali digits: ৩৯৫.০০ -> 395
    - Multiple prices (e.g. 'Tk. 225Tk. 198' or '৳ 300.00 ৳ 225.00') -> [225, 198]
    """
    if not val:
        return []
    s = to_en_digits(val)
    s = re.sub(r'(?i)\b(tk|bdt)\.', ' ', s)
    s = re.sub(r'(?i)\b(tk|bdt)\b', ' ', s)
    s = s.replace('৳', ' ').replace('/-', ' ')
    matches = re.findall(r'(\d[\d,]*)(?:\.\d+)?', s)
    prices = []
    for m in matches:
        clean_num = m.replace(',', '')
        if clean_num:
            try:
                p = int(clean_num)
                if p > 0:
                    prices.append(p)
            except ValueError:
                pass
    return prices

def to_int_price(val):
    prices = extract_prices(val)
    # If multiple prices present in a single string, the last one is the sale price
    return prices[-1] if prices else None


def normalize_bangla(val):
    if not val:
        return ""
    val = val.lower().strip()
    val = val.replace("ী", "ি").replace("ূ", "ু").replace("ণ", "ন").replace("শ", "স").replace("ষ", "স")
    val = re.sub(r"[^\w\s\u0980-\u09FF]", " ", val)
    return " ".join(val.split())


def title_similarity(query, title):
    nq = normalize_bangla(query)
    nt = normalize_bangla(title)
    if not nq or not nt:
        return 0.0
    if nq == nt:
        return 1.0

    q_words = set(nq.split())
    t_words = set(nt.split())
    if not q_words or not t_words:
        return 0.0

    overlap = len(q_words & t_words) / len(q_words)
    if len(q_words) >= 2 and overlap < 0.50:
        return 0.0

    if nq in nt:
        contain_ratio = len(nq) / len(nt)
        return max(0.88, contain_ratio)

    seq_ratio = SequenceMatcher(None, nq, nt).ratio()
    return (0.60 * overlap) + (0.40 * seq_ratio)


# ==============================================================================
# 1. ALADABOI (Islamic)
# ==============================================================================
def search_aladaboi(query):
    results = []
    try:
        r_home = requests.get('https://www.aladaboi.com', headers=HEADERS, timeout=TIMEOUT)
        js_match = re.search(r'src=["\'](/assets/index-[^"\']+\.js)["\']', r_home.text)
        if not js_match:
            return results
        r_js = requests.get(f'https://www.aladaboi.com{js_match.group(1)}', headers=HEADERS, timeout=TIMEOUT)
        token_match = re.search(r'eyJ[a-zA-Z0-9_\-\.]+', r_js.text)
        if not token_match:
            return results
        token = token_match.group(0)

        url = (
            f"https://dbms.aladaboi.com/rest/v1/products"
            f"?select=id,name,slug,price,original_price,stock,image_url,thumbnail_url,is_active"
            f"&name=ilike.*{quote(query)}*&limit=12"
        )
        r = requests.get(url, headers={
            'apikey': token,
            'Authorization': f'Bearer {token}'
        }, timeout=TIMEOUT)

        if r.status_code == 200:
            for item in r.json():
                title = item.get('name', '').strip()
                price = int(item.get('price')) if item.get('price') else None
                reg_price = int(item.get('original_price')) if item.get('original_price') else price
                stock = item.get('stock', 0)
                is_active = item.get('is_active', True)
                in_stock = bool(stock > 0 and is_active)
                slug = item.get('slug', '')

                results.append({
                    'store': 'AladaBoi',
                    'store_type': 'Islamic',
                    'title': title,
                    'author': '',
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': f'{stock} কপি স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': f'https://www.aladaboi.com/product/{slug}',
                    'image': item.get('thumbnail_url') or item.get('image_url') or '',
                })
    except Exception as exc:
        print(f"[Scraper] AladaBoi error: {exc}")
    return results


# ==============================================================================
# 2. RUHAMA SHOP (Islamic)
# ==============================================================================
def search_ruhama(query):
    results = []
    try:
        url = f"https://www.ruhamashop.com/?s={quote(query)}&post_type=product"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for p in soup.select('.product-small'):
                title_el = p.select_one('.woocommerce-loop-product__title, h2, h3, .name')
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                card_strings = list(p.stripped_strings)
                author = ""
                for s in card_strings:
                    if s != title and '৳' not in s and '%' not in s and s not in ['+', 'অর্ডার করুন']:
                        author = s
                        break

                ins = p.select_one('.price ins')
                del_el = p.select_one('.price del')
                amount = p.select_one('.price')

                price = to_int_price(ins.get_text()) if ins else to_int_price(amount.get_text() if amount else "")
                reg_price = to_int_price(del_el.get_text()) if del_el else price

                classes = p.get('class', [])
                in_stock = 'instock' in classes
                link_el = p.select_one('a')
                link = link_el.get('href') if link_el else ""
                img_el = p.select_one('img')
                img = img_el.get('data-src') or img_el.get('src') if img_el else ""

                results.append({
                    'store': 'Ruhama Shop',
                    'store_type': 'Islamic',
                    'title': title,
                    'author': author,
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img,
                })
    except Exception as exc:
        print(f"[Scraper] Ruhama error: {exc}")
    return results


# ==============================================================================
# 3. BDBOOKS (Islamic & General)
# ==============================================================================
def search_bdbooks(query):
    results = []
    try:
        url = f"https://bdbooks.net/products/{quote(query)}"
        r = requests.get(url, headers={
            **HEADERS,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
        }, timeout=TIMEOUT)

        if r.status_code == 200:
            html = r.json().get('html', '')
            soup = BeautifulSoup(html, 'html.parser')
            for c in soup.select('.product__items'):
                title_el = c.select_one('.product__items--content__title a')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get('href', '')
                author_el = c.select_one('.product__Author_name')
                author = author_el.get_text(strip=True) if author_el else ""

                price_el = c.select_one('.book-price')
                old_price_el = c.select_one('del.old_price')
                price = to_int_price(price_el.get_text()) if price_el else None
                reg_price = to_int_price(old_price_el.get_text()) if old_price_el else price

                btn = c.select_one('.add__to--cart')
                btn_text = btn.get_text(strip=True) if btn else ""
                in_stock = bool(btn and 'স্টক আউট' not in btn_text and 'out of stock' not in btn_text.lower())

                img_el = c.select_one('img')
                img = img_el.get('data-src') or img_el.get('src') if img_el else ""

                results.append({
                    'store': 'BDBooks',
                    'store_type': 'Islamic',
                    'title': title,
                    'author': author,
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img,
                })
    except Exception as exc:
        print(f"[Scraper] BDBooks error: {exc}")
    return results


# ==============================================================================
# 4. WAFILIFE (Islamic)
# ==============================================================================
def search_wafilife(query):
    results = []
    try:
        url = f"https://www.wafilife.com/api/search?keyword={quote(query)}"
        r = requests.get(url, headers={**HEADERS, 'Referer': 'https://www.wafilife.com/'}, timeout=TIMEOUT)
        if r.status_code == 200:
            for it in r.json().get('items', []):
                item_id = str(it.get('id', ''))
                if item_id.startswith(('wri_', 'pub_', 'sub_')) or not it.get('name'):
                    continue
                title = it.get('name', '').strip()
                author = ", ".join(it.get('authors', [])).strip()
                price_field = it.get('sale_price')
                if isinstance(price_field, list) and price_field:
                    price_val = price_field[0]
                else:
                    price_val = it.get('price')

                price = int(price_val) if price_val else None
                reg_price = int(it.get('price')) if it.get('price') else price
                slug = it.get('slug', '')
                url_link = f"https://www.wafilife.com/{slug}/pd/{item_id}" if slug and item_id else ""
                img = it.get('image', {}).get('original') or it.get('image', {}).get('thumbnail') or ""
                stock_status = it.get('stock_status', '')
                in_stock = stock_status != 'outofstock' and bool(price)

                results.append({
                    'store': 'Wafilife',
                    'store_type': 'Islamic',
                    'title': title,
                    'author': author,
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': url_link,
                    'image': img,
                })
    except Exception as exc:
        print(f"[Scraper] Wafilife error: {exc}")
    return results


# ==============================================================================
# 5. KITABGHOR (Islamic)
# ==============================================================================
def search_kitabghor(query):
    results = []
    try:
        url = f"https://kitabghor.com/products/search?query={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for p in soup.select('.productMain'):
                link_el = p.find('a', href=lambda h: h and '/products/details/' in h)
                if not link_el:
                    continue
                link = urljoin("https://kitabghor.com", link_el['href'])
                strings = list(p.stripped_strings)

                taka_vals = [to_int_price(s) for s in strings if '৳' in s]
                price = taka_vals[0] if taka_vals else None
                reg_price = taka_vals[1] if len(taka_vals) > 1 else price

                non_price = [
                    s for s in strings
                    if '৳' not in s and 'ছাড়' not in s and '%' not in s
                    and s not in ['এখনই কিনুন', 'স্টক নেই', 'কার্ট']
                ]
                title = non_price[0] if non_price else ""
                author = non_price[1] if len(non_price) > 1 else ""

                in_stock = not any('স্টক নেই' in s for s in strings)
                img_el = p.find('img')
                img = urljoin("https://kitabghor.com", img_el['src']) if img_el and img_el.get('src') else ""

                if title:
                    results.append({
                        'store': 'Kitabghor',
                        'store_type': 'Islamic',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                        'url': link,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Kitabghor error: {exc}")
    return results


# ==============================================================================
# 6. MAKTABATUL ASHRAF (Islamic)
# ==============================================================================
def search_maktabatulashraf(query):
    results = []
    try:
        url = f"https://maktabatulashraf.com/index.php?route=product/search&search={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for card in soup.select('.product-thumb, .product-layout'):
                title_el = card.select_one('h4 a, .caption h4 a')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get('href', '')

                price_new = card.select_one('.price-new')
                price_old = card.select_one('.price-old')
                price_general = card.select_one('.price')

                price = to_int_price(price_new.get_text()) if price_new else to_int_price(price_general.get_text() if price_general else "")
                reg_price = to_int_price(price_old.get_text()) if price_old else price

                img_el = card.select_one('img')
                img = img_el.get('src', '') if img_el else ""

                btn = card.select_one('button[onclick*="cart.add"]')
                in_stock = bool(btn and price)

                results.append({
                    'store': 'Maktabatul Ashraf',
                    'store_type': 'Islamic',
                    'title': title,
                    'author': '',
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img
                })
    except Exception as exc:
        print(f"[Scraper] Maktabatul Ashraf error: {exc}")
    return results


# ==============================================================================
# 7. BOIBITAN (Islamic & General)
# ==============================================================================
def search_boibitan(query):
    results = []
    try:
        url = f"https://boibitan.com/search?keyword={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for c in soup.select('.product, .product-item, .card, [class*="product"]'):
                link_el = c.find('a', href=lambda h: h and '/product/' in h)
                if not link_el:
                    continue
                link = link_el.get('href', '')
                strings = list(c.stripped_strings)
                taka_vals = [to_int_price(s) for s in strings if '৳' in s]
                price = taka_vals[-1] if taka_vals else None
                reg_price = taka_vals[0] if len(taka_vals) > 1 else price

                title_author = [s for s in strings if '৳' not in s and '%' not in s and 'কার্ট' not in s]
                title = title_author[0] if title_author else ""
                author = title_author[1] if len(title_author) > 1 else ""

                img_el = c.find('img')
                img = img_el.get('data-src') or img_el.get('src') if img_el else ""
                in_stock = bool(price)

                if title:
                    results.append({
                        'store': 'BoiBitan',
                        'store_type': 'Islamic',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                        'url': link,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] BoiBitan error: {exc}")
    return results


# ==============================================================================
# 8. BAATIGHAR (General)
# ==============================================================================
def search_baatighar(query):
    results = []
    try:
        url = f"https://baatighar.com/shop?search={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for c in soup.select('.card'):
                link_el = c.find('a', href=lambda h: h and '/shop/' in h)
                if not link_el:
                    continue
                link = urljoin("https://baatighar.com", link_el['href'])
                strings = list(c.stripped_strings)

                # Price from oe_currency_value or strings
                price_els = c.select('.oe_currency_value')
                if price_els:
                    price = to_int_price(price_els[0].get_text().split('.')[0])
                    reg_price = to_int_price(price_els[1].get_text().split('.')[0]) if len(price_els) > 1 else price
                else:
                    taka_vals = [to_int_price(s) for s in strings if '৳' in s]
                    price = taka_vals[0] if taka_vals else None
                    reg_price = taka_vals[1] if len(taka_vals) > 1 else price

                title_author = [s for s in strings if '৳' not in s and 'ছাড়' not in s and '%' not in s and 'OFF' not in s and 'cart' not in s.lower()]
                title = title_author[0] if title_author else ""
                author = title_author[1] if len(title_author) > 1 else ""

                img_el = c.find('img')
                img = urljoin("https://baatighar.com", img_el['src']) if img_el and img_el.get('src') else ""
                in_stock = not any('স্টক নেই' in s or 'out of stock' in s.lower() for s in strings)

                if title:
                    results.append({
                        'store': 'Baatighar',
                        'store_type': 'General',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                        'url': link,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Baatighar error: {exc}")
    return results


# ==============================================================================
# 9. BOIBARI (General & Academic)
# ==============================================================================
def search_boibari(query):
    results = []
    try:
        url = f"https://boibari.com/search?keyword={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for c in soup.select('.aiz-card-box'):
                link_el = c.find('a', href=lambda h: h and '/product/' in h)
                if not link_el:
                    continue
                link = link_el.get('href', '')
                strings = list(c.stripped_strings)
                taka_vals = [to_int_price(s) for s in strings if '৳' in s]
                price = taka_vals[-1] if taka_vals else None
                reg_price = taka_vals[0] if len(taka_vals) > 1 else price

                title_author = [
                    s for s in strings
                    if '৳' not in s and 'ছাড়' not in s and '%' not in s
                    and 'যুক্ত' not in s and 'কার্ট' not in s
                ]
                title = title_author[0] if title_author else ""
                author = title_author[1] if len(title_author) > 1 else ""

                img_el = c.find('img')
                img = img_el.get('data-src') or img_el.get('src') if img_el else ""
                in_stock = any('যুক্ত' in s or 'add' in s.lower() for s in strings)

                if title:
                    results.append({
                        'store': 'Boibari',
                        'store_type': 'General',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                        'url': link,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Boibari error: {exc}")
    return results


# ==============================================================================
# 10. EBOIGHAR (General & Academic)
# ==============================================================================
def search_eboighar(query):
    results = []
    try:
        url = f"https://eboighar.com/search?term={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.select('a.list-items-container'):
                title_el = a.select_one('.list-item-title')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = a.get('href', '')

                price_el = a.select_one('.list-item-price')
                price_str = price_el.get_text(strip=True) if price_el else ""
                prices = extract_prices(price_str)
                price = prices[-1] if prices else None
                reg_price = prices[0] if len(prices) > 1 else price
                in_stock = bool(price and 'call' not in price_str.lower())

                img_el = a.select_one('img')
                img = img_el.get('data-src') or img_el.get('src') if img_el else ""

                results.append({
                    'store': 'eBoighar',
                    'store_type': 'General',
                    'title': title,
                    'author': '',
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img
                })
    except Exception as exc:
        print(f"[Scraper] eBoighar error: {exc}")
    return results


# ==============================================================================
# 11. ADARSHA (General & Contemporary)
# ==============================================================================
def search_adarsha(query):
    results = []
    try:
        url = f"https://adarsha.com.bd/shop?search={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            links = soup.select('a[href*="/book/"]')
            seen_links = set()
            for a in links:
                link = urljoin("https://adarsha.com.bd", a.get('href', ''))
                if link in seen_links:
                    continue
                seen_links.add(link)

                card = a.find_parent('div', class_=lambda c: c and any(w in c for w in ['card', 'product', 'item', 'col', 'ui_container']))
                if not card:
                    card = a.find_parent('div')
                if not card:
                    continue

                strings = list(card.stripped_strings)
                taka_vals = []
                for s in strings:
                    val = to_int_price(s)
                    if val and 10 <= val <= 25000:
                        taka_vals.append(val)

                price = taka_vals[0] if taka_vals else None
                reg_price = taka_vals[1] if len(taka_vals) > 1 else price

                title = a.get_text(strip=True)
                if not title and len(strings) > 0:
                    title = strings[0]

                in_stock = not any('stock out' in s.lower() or 'স্টক আউট' in s for s in strings)
                img_el = card.find('img')
                img = urljoin("https://adarsha.com.bd", img_el['src']) if img_el and img_el.get('src') else ""

                if title:
                    results.append({
                        'store': 'Adarsha',
                        'store_type': 'General',
                        'title': title,
                        'author': '',
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                        'url': link,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Adarsha error: {exc}")
    return results


# ==============================================================================
# 12. BOOKTANKBD (General & Novels)
# ==============================================================================
def search_booktankbd(query):
    results = []
    try:
        url = f"https://booktankbd.com/search/suggest.json?q={quote(query)}&resources[type]=product"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            for item in r.json().get('resources', {}).get('results', {}).get('products', []):
                title = item.get('title', '').strip()
                price = int(float(item.get('price', 0))) if item.get('price') else None
                reg_price = int(float(item.get('compare_at_price_min', 0))) if item.get('compare_at_price_min') else price
                in_stock = bool(item.get('available', True))
                url_link = urljoin("https://booktankbd.com", item.get('url', ''))
                img = item.get('image', '')

                results.append({
                    'store': 'BookTankBD',
                    'store_type': 'General',
                    'title': title,
                    'author': item.get('vendor', ''),
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': url_link,
                    'image': img
                })
    except Exception as exc:
        print(f"[Scraper] BookTankBD error: {exc}")
    return results


# ==============================================================================
# 13. BOOKOCEANBD (General & Classics)
# ==============================================================================
_bookocean_cache = None
def search_bookocean(query):
    global _bookocean_cache
    results = []
    try:
        if _bookocean_cache is None:
            r = requests.get("https://book-ocean-bd-server.vercel.app/books", headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                _bookocean_cache = r.json()
            else:
                _bookocean_cache = []

        q_lower = query.lower()
        for item in _bookocean_cache:
            name = item.get('name', '')
            author = item.get('author', '')
            if q_lower in name.lower() or q_lower in author.lower():
                price = int(item.get('price', 0)) if item.get('price') else None
                img = item.get('image', '')
                results.append({
                    'store': 'BookOceanBD',
                    'store_type': 'General',
                    'title': name,
                    'author': author,
                    'price': price,
                    'regular_price': price,
                    'in_stock': True,
                    'stock_text': 'স্টকে আছে',
                    'url': 'https://bookoceanbd.com',
                    'image': img
                })
    except Exception as exc:
        print(f"[Scraper] BookOceanBD error: {exc}")
    return results


# ==============================================================================
# 14. BENGAL PUBLICATIONS (General & Literature)
# ==============================================================================
def search_bengalpublications(query):
    results = []
    try:
        url = f"https://www.bengalpublications.com/?s={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for c in soup.select('div.card.mb-3'):
                title_el = c.select_one('.card-title')
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link_el = c.find('a', href=lambda h: h and h.startswith('http'))
                link = link_el.get('href', '') if link_el else ""
                img_el = c.find('img')
                img = img_el.get('src', '') if img_el else ""

                results.append({
                    'store': 'Bengal Publications',
                    'store_type': 'General',
                    'title': title,
                    'author': '',
                    'price': None,
                    'regular_price': None,
                    'in_stock': True,
                    'stock_text': 'উপলব্ধ',
                    'url': link,
                    'image': img
                })
    except Exception as exc:
        print(f"[Scraper] Bengal Publications error: {exc}")
    return results


# ==============================================================================
# 15. PBS (General)
# ==============================================================================
def search_pbs(query):
    results = []
    try:
        url = f"https://pbs.com.bd/search?term={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            grid = soup.find('div', class_=lambda c: c and 'grid' in c and 'grid-cols-4' in c)
            if grid:
                for card in grid.find_all('div', recursive=False):
                    strings = list(card.stripped_strings)
                    link_el = card.find('a', href=lambda h: h and h.startswith('/book/'))
                    if not link_el:
                        continue
                    link = urljoin("https://pbs.com.bd", link_el['href'])

                    taka_vals = [to_int_price(s) for s in strings if '৳' in s]
                    price = taka_vals[-1] if taka_vals else None
                    reg_price = taka_vals[0] if len(taka_vals) > 1 else price

                    non_price = [
                        s for s in strings
                        if '৳' not in s and 'ছাড়' not in s and 'cart' not in s.lower() and 'stock' not in s.lower()
                    ]
                    title = non_price[0] if non_price else ""
                    author = non_price[1] if len(non_price) > 1 else ""

                    in_stock = any('add to cart' in s.lower() for s in strings)
                    img_el = card.find('img')
                    img = urljoin("https://pbs.com.bd", img_el['src']) if img_el and img_el.get('src') else ""

                    if title:
                        results.append({
                            'store': 'PBS',
                            'store_type': 'General',
                            'title': title,
                            'author': author,
                            'price': price,
                            'regular_price': reg_price,
                            'in_stock': in_stock,
                            'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                            'url': link,
                            'image': img,
                        })
    except Exception as exc:
        print(f"[Scraper] PBS error: {exc}")
    return results


# ==============================================================================
# 16. PROTHOMA (General)
# ==============================================================================
def search_prothoma(query):
    results = []
    try:
        url = f"https://prothoma.com/shop?search={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for p in soup.select('.oe_product'):
                title_el = p.select_one('h6 a, h5 a, .o_wsale_products_item_title a, a[href*="/shop/"]')
                title = title_el.get_text(strip=True) if title_el else ""
                link = urljoin("https://prothoma.com", title_el['href']) if title_el and title_el.get('href') else ""
                if not title or not link:
                    continue

                strings = list(p.stripped_strings)
                prices = []
                for s in strings:
                    val = to_int_price(s)
                    if val and 10 <= val <= 20000:
                        prices.append(val)
                price = prices[0] if prices else None
                reg_price = prices[1] if len(prices) > 1 else price

                in_stock = not any('স্টক নেই' in s or 'out of stock' in s.lower() for s in strings)
                img_el = p.select_one('img')
                img = urljoin("https://prothoma.com", img_el['src']) if img_el and img_el.get('src') else ""

                results.append({
                    'store': 'Prothoma',
                    'store_type': 'General',
                    'title': title,
                    'author': '',
                    'price': price,
                    'regular_price': reg_price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img,
                })
    except Exception as exc:
        print(f"[Scraper] Prothoma error: {exc}")
    return results


# ==============================================================================
# 17. ROKOMARI (General)
# ==============================================================================
def search_rokomari(query):
    results = []
    try:
        url = f"https://www.rokomari.com/search?term={quote(query)}&search_type=ALL"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all(lambda tag: tag.name == 'div' and any('productGridItem' in c for c in tag.get('class', [])))
            for card in cards:
                t_el = card.find('p', class_=lambda c: c and 'productTitle' in c)
                a_el = card.find('p', class_=lambda c: c and 'productAuthor' in c)
                p_el = card.find('p', class_=lambda c: c and 'productPrice' in c)
                l_el = card.find('a', href=lambda h: h and '/book/' in h)
                i_el = card.find('img')

                title = t_el.text.strip() if t_el else ""
                if not title or not l_el:
                    continue

                link = urljoin("https://www.rokomari.com", l_el['href'])
                price = to_int_price(p_el.text) if p_el else None
                author = a_el.text.strip() if a_el else ""
                img = i_el.get('data-src') or i_el.get('src') or "" if i_el else ""

                card_text = card.get_text()
                in_stock = 'Product in stock' in card_text or 'In stock' in card_text or 'স্টকে আছে' in card_text

                results.append({
                    'store': 'Rokomari',
                    'store_type': 'General',
                    'title': title,
                    'author': author,
                    'price': price,
                    'regular_price': price,
                    'in_stock': in_stock,
                    'stock_text': 'স্টকে আছে' if in_stock else 'স্টক নেই',
                    'url': link,
                    'image': img,
                })
    except Exception as exc:
        print(f"[Scraper] Rokomari error: {exc}")
    return results


# ==============================================================================
# 18. GUARDIAN PUBLICATIONS (Official Publisher API)
# ==============================================================================
def search_guardianpubs(query):
    results = []
    try:
        url = f"https://api.guardianpubs.com/api/product/get-all/?q={quote(query)}"
        payload = {
            "pagination": {"pageSize": 10, "currentPage": 0},
            "filter": {"status": "publish"},
            "select": {
                "name": 1, "nameEn": 1, "salePrice": 1, "costPrice": 1,
                "discountAmount": 1, "discountType": 1, "slug": 1, "quantity": 1, "trackQuantity": 1,
                "images": 1, "author": 1
            },
            "sort": {"createdAt": -1}
        }
        r = requests.post(
            url,
            headers={
                **HEADERS,
                'Content-Type': 'application/json',
                'Origin': 'https://guardianpubs.com',
                'Referer': 'https://guardianpubs.com/'
            },
            json=payload,
            timeout=TIMEOUT
        )
        if r.status_code in [200, 201]:
            data = r.json().get('data', [])
            for b in data:
                title = b.get('name', '').strip()
                price = b.get('salePrice')
                qty = b.get('quantity', 1)
                in_stock = bool(qty > 0)
                slug = b.get('slug', '')
                disc = b.get('discountAmount', 0)
                disc_type = b.get('discountType', 1)
                reg_price = price
                if disc and disc_type == 1 and price:
                    reg_price = round(price / (1 - (disc / 100.0)))
                elif disc and price:
                    reg_price = price + disc

                imgs = b.get('images', [])
                img = imgs[0] if imgs else ""
                authors = b.get('author', [])
                author = authors[0].get('name', '') if authors and isinstance(authors[0], dict) else ""

                if title and price:
                    results.append({
                        'store': 'Guardian Publications (অফিসিয়াল)',
                        'store_type': 'Islamic',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': in_stock,
                        'stock_text': 'স্টকে আছে' if in_stock else 'স্টক আউট',
                        'url': f"https://guardianpubs.com/product-details/{slug}" if slug else "https://guardianpubs.com",
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Guardian Publications error: {exc}")
    return results


# ==============================================================================
# 19. OITIJJHYA (ঐতিহ্য প্রকাশনী অফিসিয়াল স্টোর)
# ==============================================================================
def search_oitijjhya(query):
    results = []
    try:
        url = f"https://oitijjhya.com/search?keyword={quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.select('.aiz-card-box')
            for c in cards[:8]:
                h3 = c.select_one('h3') or c.select_one('.text-truncate-2')
                link = c.select_one('a[href*="/book/"]')
                actual_p = c.select_one('.actual__price')
                del_p = c.select_one('.delete__price')

                title = h3.get_text(strip=True) if h3 else ''
                price = to_int_price(actual_p.get_text()) if actual_p else None
                reg_price = to_int_price(del_p.get_text()) if del_p else price
                prod_url = link.get('href') if link else ''

                img_el = c.select_one('img')
                img = img_el.get('data-src') or img_el.get('src') or "" if img_el else ""

                if title and price:
                    results.append({
                        'store': 'Oitijjhya (ঐতিহ্য অফিসিয়াল)',
                        'store_type': 'General',
                        'title': title,
                        'author': '',
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': True,
                        'stock_text': 'স্টকে আছে',
                        'url': prod_url,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Oitijjhya error: {exc}")
    return results


# ==============================================================================
# 20. ANYAPROKASH (অন্যপ্রকাশ অফিসিয়াল স্টোর - Shopify API)
# ==============================================================================
def search_anyaprokash(query):
    results = []
    try:
        url = f"https://anyaprokash.com/search/suggest.json?q={quote(query)}&resources[type]=product"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            products = data.get('resources', {}).get('results', {}).get('products', [])
            for p in products[:8]:
                title = p.get('title', '').strip()
                raw_price = p.get('price')
                price = int(float(raw_price)) if raw_price else None
                available = p.get('available', True)
                p_url = p.get('url', '')
                full_url = f"https://anyaprokash.com{p_url}" if p_url.startswith('/') else p_url

                img = p.get('image') or (p.get('featured_image', {}).get('url') if isinstance(p.get('featured_image'), dict) else "") or ""
                author = p.get('vendor') or ""

                if title and price:
                    results.append({
                        'store': 'AnyaProkash (অন্যপ্রকাশ অফিসিয়াল)',
                        'store_type': 'General',
                        'title': title,
                        'author': author,
                        'price': price,
                        'regular_price': price,
                        'in_stock': bool(available),
                        'stock_text': 'স্টকে আছে' if available else 'স্টক শেষ',
                        'url': full_url,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] AnyaProkash error: {exc}")
    return results


# ==============================================================================
# 21. ANINDYA PROKASH (অনিন্দ্য প্রকাশ অফিসিয়াল স্টোর)
# ==============================================================================
def search_anindyaprokash(query):
    results = []
    try:
        url = f"https://anindyaprokash.com/?s={quote(query)}&post_type=product"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            products = soup.select('.product')
            for p in products[:8]:
                title_tag = p.select_one('.product-name a') or p.select_one('h3 a') or p.select_one('h2 a')
                price_box = p.select_one('.price')
                if not title_tag or not price_box:
                    continue

                title = title_tag.get_text(strip=True)
                p_url = title_tag.get('href', '')

                prices = extract_prices(price_box.get_text())
                price = prices[-1] if prices else None
                reg_price = prices[0] if len(prices) > 1 else price

                is_in_stock = 'outofstock' not in p.get('class', [])

                img_el = p.select_one('img')
                img = img_el.get('data-src') or img_el.get('src') or "" if img_el else ""

                if title and price:
                    results.append({
                        'store': 'Anindya Prokash (অনিন্দ্য প্রকাশ)',
                        'store_type': 'General',
                        'title': title,
                        'author': '',
                        'price': price,
                        'regular_price': reg_price,
                        'in_stock': is_in_stock,
                        'stock_text': 'স্টকে আছে' if is_in_stock else 'স্টক আউট',
                        'url': p_url,
                        'image': img
                    })
    except Exception as exc:
        print(f"[Scraper] Anindya error: {exc}")
    return results


# ==============================================================================
# STORE REGISTRY (21 BOOKSTORES & OFFICIAL PUBLISHERS)
# ==============================================================================
STORE_REGISTRY = [
    # 8 Islamic Bookstores & Official Publishers
    ("AladaBoi", "Islamic", search_aladaboi),
    ("Ruhama Shop", "Islamic", search_ruhama),
    ("BDBooks", "Islamic", search_bdbooks),
    ("Wafilife", "Islamic", search_wafilife),
    ("Kitabghor", "Islamic", search_kitabghor),
    ("Maktabatul Ashraf", "Islamic", search_maktabatulashraf),
    ("BoiBitan", "Islamic", search_boibitan),
    ("Guardian Publications", "Islamic", search_guardianpubs),

    # 13 General / Academic / Literary Bookstores & Official Publishers
    ("Baatighar", "General", search_baatighar),
    ("Boibari", "General", search_boibari),
    ("eBoighar", "General", search_eboighar),
    ("Adarsha", "General", search_adarsha),
    ("BookTankBD", "General", search_booktankbd),
    ("BookOceanBD", "General", search_bookocean),
    ("Bengal Publications", "General", search_bengalpublications),
    ("PBS", "General", search_pbs),
    ("Prothoma", "General", search_prothoma),
    ("Rokomari", "General", search_rokomari),
    ("Oitijjhya", "General", search_oitijjhya),
    ("AnyaProkash", "General", search_anyaprokash),
    ("Anindya Prokash", "General", search_anindyaprokash),
]


def compare_books(query, category="all", target_store=None, min_similarity=0.60):
    """
    Search across bookstores, filter by relevance,
    and rank based on stock availability and price (Top 3 Lowest Price).
    If target_store is specified, queries ONLY that store (Single-Store Exclusive Mode for B2B SaaS).
    """
    query = query.strip()
    if not query:
        return {"query": "", "top_3": [], "all_results": [], "total_found": 0, "stores_searched": 0}

    scrapers = STORE_REGISTRY
    if target_store:
        target_norm = target_store.lower().replace(" ", "")
        scrapers = [s for s in STORE_REGISTRY if target_norm in s[0].lower().replace(" ", "")]
        min_similarity = min(min_similarity, 0.40)
    elif category == "islamic":
        scrapers = [s for s in STORE_REGISTRY if s[1] == "Islamic"]
    elif category == "general":
        scrapers = [s for s in STORE_REGISTRY if s[1] == "General"]

    raw_items = []
    errors = {}

    with ThreadPoolExecutor(max_workers=min(len(scrapers), 24)) as pool:
        future_map = {pool.submit(fn, query): (name, stype) for name, stype, fn in scrapers}
        for future in as_completed(future_map):
            name, stype = future_map[future]
            try:
                items = future.result()
                raw_items.extend(items)
            except Exception as e:
                errors[name] = str(e)

    # Filter items matching the query title
    matched_items = []
    for it in raw_items:
        score = title_similarity(query, it['title'])
        if score >= min_similarity:
            it['match_score'] = round(score * 100)
            matched_items.append(it)

    # Cross-item metadata enrichment: share cover image & author across results
    best_cover_image = ""
    for it in matched_items:
        img_val = it.get('image') or ""
        if img_val and ('http://' in img_val or 'https://' in img_val):
            best_cover_image = img_val
            try:
                from cover_resolver import set_cached_image
                set_cached_image(query, best_cover_image)
            except Exception:
                pass
            break

    best_author = ""
    for it in matched_items:
        auth_val = it.get('author') or ""
        if auth_val and len(auth_val.strip()) > 1 and auth_val.strip() not in ['-', 'N/A']:
            best_author = auth_val.strip()
            break

    for it in matched_items:
        if not it.get('image') and best_cover_image:
            it['image'] = best_cover_image
        if not it.get('author') and best_author:
            it['author'] = best_author

    # Sort all matched items:
    # 1. In-stock items first
    # 2. Lowest price first
    matched_items.sort(
        key=lambda x: (
            not x['in_stock'],
            x['price'] if x['price'] is not None else 999999,
            -x['match_score']
        )
    )

    # Calculate Top 3 Lowest Prices (Prioritizing In-Stock)
    store_best = {}
    for item in matched_items:
        st = item['store']
        if st not in store_best:
            store_best[st] = item
        else:
            if not store_best[st]['in_stock'] and item['in_stock']:
                store_best[st] = item
            elif store_best[st]['in_stock'] == item['in_stock']:
                if item['price'] and (not store_best[st]['price'] or item['price'] < store_best[st]['price']):
                    store_best[st] = item

    unique_store_items = list(store_best.values())
    unique_store_items.sort(
        key=lambda x: (
            not x['in_stock'],
            x['price'] if x['price'] is not None else 999999
        )
    )

    # Extract Top 5 Deals
    top_5 = []
    badges = [
        "🥇 সেরা অফার (১ম সর্বনিম্ন)",
        "🥈 ২য় সর্বনিম্ন",
        "🥉 ৩য় সর্বনিম্ন",
        "🎖️ ৪র্থ সর্বনিম্ন",
        "⭐ ৫ম সর্বনিম্ন"
    ]
    in_stock_candidates = [it for it in unique_store_items if it['in_stock'] and it['price']]

    for i, it in enumerate(in_stock_candidates[:5]):
        it_copy = dict(it)
        it_copy['rank'] = i + 1
        it_copy['badge'] = badges[i]
        top_5.append(it_copy)

    if len(top_5) < 5:
        out_of_stock = [it for it in unique_store_items if not it['in_stock'] and it['price']]
        for it in out_of_stock[: 5 - len(top_5)]:
            it_copy = dict(it)
            it_copy['rank'] = len(top_5) + 1
            it_copy['badge'] = f"{badges[len(top_5)]} (স্টক শেষ)"
            top_5.append(it_copy)

    return {
        "query": query,
        "category": category,
        "top_5": top_5,
        "top_3": top_5,  # backwards-compatible alias
        "all_results": matched_items,
        "total_found": len(matched_items),
        "stores_searched": len(scrapers),
        "errors": errors
    }


def stream_compare_books(query, category="all", target_store=None, min_similarity=0.60):
    """
    Progressive real-time generator: yields results via Server-Sent Events (SSE)
    as each individual bookstore scraper finishes.
    Rokomari and Wafilife arrive in 1-2s, with other stores streaming in successively.
    """
    query = query.strip()
    if not query:
        yield {"event": "complete", "data": {"query": "", "top_5": [], "all_results": [], "total_found": 0, "stores_searched": 0}}
        return

    scrapers = STORE_REGISTRY
    if target_store:
        target_norm = target_store.lower().replace(" ", "")
        scrapers = [s for s in STORE_REGISTRY if target_norm in s[0].lower().replace(" ", "")]
        min_similarity = min(min_similarity, 0.40)
    elif category == "islamic":
        scrapers = [s for s in STORE_REGISTRY if s[1] == "Islamic"]
    elif category == "general":
        scrapers = [s for s in STORE_REGISTRY if s[1] == "General"]

    total_stores = len(scrapers)
    all_matched = []
    completed_count = 0
    best_cover_image = ""
    best_author = ""

    with ThreadPoolExecutor(max_workers=min(total_stores, 24)) as pool:
        future_map = {pool.submit(fn, query): (name, stype) for name, stype, fn in scrapers}
        for future in as_completed(future_map):
            name, stype = future_map[future]
            completed_count += 1
            store_items = []
            try:
                raw = future.result()
                for it in raw:
                    score = title_similarity(query, it['title'])
                    if score >= min_similarity:
                        it['match_score'] = round(score * 100)
                        store_items.append(it)
                        all_matched.append(it)

                        # Update best cover and author
                        img_val = it.get('image') or ""
                        if not best_cover_image and img_val and ('http://' in img_val or 'https://' in img_val):
                            best_cover_image = img_val
                        auth_val = it.get('author') or ""
                        if not best_author and auth_val and len(auth_val.strip()) > 1 and auth_val.strip() not in ['-', 'N/A']:
                            best_author = auth_val.strip()
            except Exception as e:
                pass

            # Enrich this store's items if image or author became available
            for it in store_items:
                if not it.get('image') and best_cover_image:
                    it['image'] = best_cover_image
                if not it.get('author') and best_author:
                    it['author'] = best_author

            yield {
                "event": "store_result",
                "data": {
                    "store": name,
                    "type": stype,
                    "items": store_items,
                    "has_match": len(store_items) > 0,
                    "completed": completed_count,
                    "total": total_stores,
                    "is_fast_tier": name in ["Rokomari", "Wafilife"]
                }
            }

    # Final ranking calculation
    all_matched.sort(
        key=lambda x: (
            not x['in_stock'],
            x['price'] if x['price'] is not None else 999999,
            -x['match_score']
        )
    )

    store_best = {}
    for item in all_matched:
        st = item['store']
        if st not in store_best:
            store_best[st] = item
        else:
            if not store_best[st]['in_stock'] and item['in_stock']:
                store_best[st] = item
            elif store_best[st]['in_stock'] == item['in_stock']:
                if item['price'] and (not store_best[st]['price'] or item['price'] < store_best[st]['price']):
                    store_best[st] = item

    unique_store_items = list(store_best.values())
    unique_store_items.sort(
        key=lambda x: (
            not x['in_stock'],
            x['price'] if x['price'] is not None else 999999,
            -x['match_score']
        )
    )

    badges = ["🥇 সেরা অফার (১ম সর্বনিম্ন)", "🥈 ২য় সর্বনিম্ন", "🥉 ৩য় সর্বনিম্ন", "🎖️ ৪র্থ সর্বনিম্ন", "⭐ ৫ম সর্বনিম্ন"]
    top_5 = []
    in_stock_candidates = [it for it in unique_store_items if it['in_stock'] and it['price']]
    for i, it in enumerate(in_stock_candidates[:5]):
        it_copy = dict(it)
        it_copy['rank'] = i + 1
        it_copy['badge'] = badges[i]
        top_5.append(it_copy)

    if len(top_5) < 5:
        out_of_stock = [it for it in unique_store_items if not it['in_stock'] and it['price']]
        for it in out_of_stock[: 5 - len(top_5)]:
            it_copy = dict(it)
            it_copy['rank'] = len(top_5) + 1
            it_copy['badge'] = f"{badges[len(top_5)]} (স্টক শেষ)"
            top_5.append(it_copy)

    yield {
        "event": "complete",
        "data": {
            "query": query,
            "top_5": top_5,
            "all_results": all_matched,
            "total_found": len(all_matched),
            "stores_searched": total_stores
        }
    }

