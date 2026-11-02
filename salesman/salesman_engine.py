import os
import sys
import re
import csv
import json
import time
import requests
from difflib import SequenceMatcher

# Add parent directory to path to import comparator_engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comparator_engine import compare_books, normalize_bangla

try:
    from cover_resolver import resolve_book_cover, resolve_covers_for_books, get_cached_image, set_cached_image
except ImportError:
    try:
        from ..cover_resolver import resolve_book_cover, resolve_covers_for_books, get_cached_image, set_cached_image
    except Exception:
        def resolve_book_cover(t): return ""
        def resolve_covers_for_books(b): return b
        def get_cached_image(t): return None
        def set_cached_image(t, u): pass

try:
    from .merchant_registry import get_merchant
except ImportError:
    from salesman.merchant_registry import get_merchant

# ==============================================================================
# BENGALI STEMMING & NORMALIZATION HELPERS
# ==============================================================================
BN_DIGITS = {chr(0x09E6 + i): str(i) for i in range(10)}

def to_en_digits(s):
    """Converts Bengali numerals (০-৯) to English digits (0-9)."""
    return "".join(BN_DIGITS.get(c, c) for c in s)

def strip_bn_suffix(w):
    """
    Safely strips genuine Bengali grammatical suffixes without destroying root words
    like 'ক্যারিয়ার', 'থ্রিলার', 'কম্পিউটার', 'মাস্টার', 'ঈশ্বর', etc.
    """
    if not w or len(w) <= 3:
        return w
    safe_suffixes = [
        'গুলোর', 'গুলো', 'গুলা', 'টির', 'টার', 'খানা', 'খানি',
        'দের', '-এর', 'ের', 'কে', 'নীর', 'নির', 'নি'
    ]
    for s in safe_suffixes:
        if w.endswith(s) and len(w) > len(s) + 2:
            return w[:-len(s)]
    return w


# ==============================================================================
# 1. CATALOG MANAGER (Loads 60,000 books with Author & Publisher Index)
# ==============================================================================
class CatalogIndex:
    _instance = None

    def __init__(self):
        self.books = []
        self.subject_map = {}
        self.author_set = set()
        self.author_map = {}      # norm_auth -> [book, ...]
        self.publisher_set = set()
        self.publisher_map = {}   # norm_pub -> [book, ...]
        self.loaded = False
        self._load_catalog()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = CatalogIndex()
        return cls._instance

    def _load_catalog(self):
        if self.loaded:
            return

        possible_paths = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_combined_catalog.csv")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "wafilife scrapper", "master.csv")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master.csv")),
            r"C:\Automation_project\wafilife scrapper\master.csv",
        ]

        csv_path = None
        for p in possible_paths:
            if os.path.exists(p):
                csv_path = p
                break

        if not csv_path:
            print("[CatalogIndex] Warning: master.csv not found in known paths.")
            return

        t0 = time.time()
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get("book_name", "").strip()
                if not title:
                    continue
                author = row.get("author_name", "").strip()
                publisher = row.get("publisher_name", "").strip()
                subject = row.get("subject_name", "").strip()

                try:
                    price = int(float(row.get("wafilife_price") or row.get("main_price") or 0))
                except (ValueError, TypeError):
                    price = 0

                img_val = row.get("image_url") or row.get("image") or ""
                item = {
                    "id": row.get("book_id"),
                    "title": title,
                    "normalized_title": normalize_bangla(title),
                    "author": author,
                    "normalized_author": normalize_bangla(author),
                    "publisher": publisher,
                    "normalized_publisher": normalize_bangla(publisher),
                    "subject": subject,
                    "normalized_subject": normalize_bangla(subject),
                    "price": price,
                    "image": img_val,
                    "image_url": img_val,
                }
                self.books.append(item)

                # Author indexing
                if author:
                    self.author_set.add(author)
                    n_auth = item["normalized_author"]
                    if n_auth not in self.author_map:
                        self.author_map[n_auth] = []
                    self.author_map[n_auth].append(item)

                # Publisher indexing
                if publisher:
                    self.publisher_set.add(publisher)
                    n_pub = item["normalized_publisher"]
                    if n_pub not in self.publisher_map:
                        self.publisher_map[n_pub] = []
                    self.publisher_map[n_pub].append(item)

                # Subject indexing
                if subject not in self.subject_map:
                    self.subject_map[subject] = []
                self.subject_map[subject].append(item)

        self.loaded = True
        print(f"[CatalogIndex] Loaded {len(self.books)} books, {len(self.author_set)} authors, and {len(self.publisher_set)} publishers in {time.time() - t0:.2f}s")

    def search(self, keywords=None, author=None, publisher=None, subject_filter=None, boost_titles=None, min_price=None, max_price=None, limit=5):
        """
        Deep search supporting author, publisher, subject, curated bestsellers, price ranges, and multi-token semantic overlap.
        """
        if not self.books:
            return []

        keywords = keywords or []
        clean_keywords = [normalize_bangla(strip_bn_suffix(k)) for k in keywords if len(k) > 1]
        boost_titles = [normalize_bangla(bt) for bt in (boost_titles or []) if bt]
        results = []

        # Choose the most specific starting pool
        if publisher:
            norm_target_pub = normalize_bangla(publisher)
            pool = []
            for p_key, b_list in self.publisher_map.items():
                if norm_target_pub in p_key or p_key in norm_target_pub:
                    pool.extend(b_list)
            if not pool:
                pool = [b for b in self.books if norm_target_pub in b["normalized_publisher"]]
        elif author:
            norm_target_auth = normalize_bangla(author)
            pool = []
            for a_key, b_list in self.author_map.items():
                if norm_target_auth in a_key or a_key in norm_target_auth:
                    pool.extend(b_list)
            if not pool:
                pool = [b for b in self.books if norm_target_auth in b["normalized_author"]]
        elif subject_filter:
            pool = self.subject_map.get(subject_filter, self.books)
        else:
            pool = self.books

        for b in pool:
            # Price filters
            if min_price and b["price"] and b["price"] < min_price:
                continue
            if max_price and b["price"] and b["price"] > max_price:
                continue

            score = 1
            b_norm = b["normalized_title"]
            b_subj = b["normalized_subject"]
            b_auth = b["normalized_author"]
            b_pub = b["normalized_publisher"]

            # Curated / Bestseller boost
            for bt in boost_titles:
                if bt in b_norm or b_norm in bt:
                    score += 85
                    break

            # Publisher match bonus
            if publisher and (normalize_bangla(publisher) in b_pub or b_pub in normalize_bangla(publisher)):
                score += 60

            # Author match bonus
            if author and (normalize_bangla(author) in b_auth or b_auth in normalize_bangla(author)):
                score += 50

            # Subject match bonus
            if subject_filter and (normalize_bangla(subject_filter) in b_subj):
                score += 20

            # Keywords match
            kw_hit = False
            for kw in clean_keywords:
                if kw == b_norm:
                    score += 100
                    kw_hit = True
                elif kw in b_norm:
                    score += 25
                    kw_hit = True
                if kw in b_subj:
                    score += 5
                if kw in b_auth:
                    score += 10
                if kw in b_pub:
                    score += 8

            if b["price"] > 0:
                score += 4

            if score > 0:
                results.append((score, b))

        # Sort by relevance score desc, then prefer real prices
        results.sort(key=lambda x: (-x[0], -x[1]["price"] if x[1]["price"] else 0))

        seen_titles = set()
        unique_results = []
        for r in results:
            t = r[1]["title"]
            if t not in seen_titles:
                seen_titles.add(t)
                unique_results.append(r[1])
            if len(unique_results) >= limit:
                break

        # Resolve real cover images for recommended books
        try:
            resolve_covers_for_books(unique_results)
        except Exception:
            pass

        return unique_results


# ==============================================================================
# 2. SESSION & CREDIT MANAGER
# ==============================================================================
class SessionManager:
    _instance = None

    def __init__(self):
        self.sessions = {}
        self.default_credits = 15

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance

    def get_session(self, session_id):
        if not session_id or session_id not in self.sessions:
            session_id = session_id or f"sess_{int(time.time()*1000)}"
            self.sessions[session_id] = {
                "history": [],
                "credits": self.default_credits,
                "created_at": time.time(),
            }
        return session_id, self.sessions[session_id]

    def consume_credit(self, session_id):
        _, sess = self.get_session(session_id)
        if sess["credits"] > 0:
            sess["credits"] -= 1
            return True, sess["credits"]
        return False, 0

    def add_history(self, session_id, role, text):
        _, sess = self.get_session(session_id)
        sess["history"].append({"role": role, "text": text})
        if len(sess["history"]) > 10:
            sess["history"] = sess["history"][-10:]


# ==============================================================================
# BOOK ONTOLOGY & TOPIC INTELLIGENCE ENGINE (16 Core Reader Categories)
# ==============================================================================
BOOK_ONTOLOGY = {
    "depression": {
        "title": "হতাশা, দুশ্চিন্তা ও মানসিক প্রশান্তি",
        "subject": "আত্ম-উন্নয়ন, মোটিভেশনাল ও মেডিটেশন",
        "aliases": [
            "হতাশ", "হতাশা", "ডিপ্রেশন", "মন খারাপ", "কষ্ট", "দুশ্চিন্তা", "মানসিক", "প্রশান্তি",
            "শান্তি", "ব্যর্থতা", "অশান্তি", "ক্লান্তি", "হতাশার", "কষ্টের", "মনমরা", "কষ্টে",
            "depression", "anxiety", "sad", "peace", "stress", "mental peace", "broken"
        ],
        "boost_keywords": ["হতাশা", "ডিপ্রেশন", "দুশ্চিন্তা", "প্রশান্তি", "ব্যর্থতা", "শান্তি", "কষ্ট", "মন"],
        "curated": ["ব্যর্থতা ও হতাশার অবসান", "মানসিক প্রশান্তি আর মর্যাদাপূর্ণ জীবনের জাদুকাঠি", "ডিপ্রেশন", "বেলা ফুরাবার আগে", "রিচার্জ আপনার ইমান", "হতাশ হবেন না"],
        "theme_overview": "জীবনের কঠিন সময়ে মানসিক ক্লান্তি, বিষণ্নতা ও একাকিত্ব দূর করে অন্তরের স্থায়ী প্রশান্তি ও নতুন করে বাঁচার প্রেরণা দেওয়ার বই।",
        "takeaways": "নেতিবাচক ভাবনা দূর করা, কঠিন মুহূর্তে মনের জোর ধরে রাখা এবং ইতিবাচক দৃষ্টিভঙ্গি তৈরি।"
    },
    "career": {
        "title": "ক্যারিয়ার, পেশা ও দক্ষতা উন্নয়ন",
        "subject": "আত্ম-উন্নয়ন, মোটিভেশনাল ও মেডিটেশন",
        "aliases": [
            "ক্যারিয়ার", "ক্যারিয়ার", "চাকরি", "পেশা", "দক্ষতা", "স্কিল", "সাফল্য", "সফল", "উন্নয়ন",
            "স্মার্ট", "পড়াশোনা", "পড়ালেখা", "বিসিএস", "রোডম্যাপ", "সিভি", "ইন্টারভিউ", "কর্মক্ষেত্র",
            "career", "job", "skill", "success", "study", "bcs", "interview", "resume"
        ],
        "boost_keywords": ["ক্যারিয়ার", "ক্যারিয়ার", "দক্ষতা", "সাফল্য", "পরিকল্পনা", "ম্যানেজমেন্ট", "রোডম্যাপ", "স্মার্ট", "পেশা"],
        "curated": ["ক্যারিয়ার গঠন ও দক্ষতা উন্নয়ন", "ক্যারিয়ার পরিকল্পনা ও বাস্তবায়ন", "ক্যারিয়ার ক্যারিশমা", "সাফল্যের মন্ত্র", "স্মার্ট ক্যারিয়ার"],
        "theme_overview": "পেশাগত জীবনে প্রতিযোগিতা থেকে এগিয়ে থাকা, উচ্চ আয়ের বাস্তবমুখী স্কিল অর্জন এবং দীর্ঘমেয়াদি সফল ক্যারিয়ার গঠনের অনন্য গাইডলাইন।",
        "takeaways": "সঠিক পেশা নির্বাচন, আধুনিক সফট স্কিল ও লিডারশিপ অর্জন এবং কর্মক্ষেত্রে দ্রুত পদোন্নতির কৌশল।"
    },
    "business": {
        "title": "ব্যবসা, বিনিয়োগ ও অর্থব্যবস্থাপনা",
        "subject": "ব্যবসা, বিনিয়োগ ও অর্থনীতি",
        "aliases": [
            "ব্যবসা", "উদ্যোক্তা", "কোম্পানি", "স্টার্টআপ", "বিনিয়োগ", "শেয়ার", "শেয়ারবাজার", "বাণিজ্য",
            "অর্থনীতি", "টাকা", "ধনী", "মার্কেটিং", "সেলস", "বিজনেস", "কমার্স", "লাভ",
            "business", "startup", "money", "invest", "finance", "marketing", "sales", "rich"
        ],
        "boost_keywords": ["ব্যবসা", "উদ্যোক্তা", "বিনিয়োগ", "অর্থনীতি", "মার্কেটিং", "ধনী", "বাণিজ্য", "টাকা"],
        "curated": ["ব্যবসার সহজ সূত্র", "উদ্যোক্তা উন্নয়ন ও ব্যবসায় নির্দেশনা", "রিচ ড্যাড পুওর ড্যাড", "দ্য সাইকোলজি অব মানি", "জিরো টু ওয়ান"],
        "theme_overview": "নতুন উদ্যোক্তা হওয়া, লাভজনক বিজনেস মডেল তৈরি, সঠিক জায়গায় অর্থ বিনিয়োগ ও ধনসম্পদ বৃদ্ধির পরীক্ষিত সূত্র শেখার বই।",
        "takeaways": "জিরো থেকে ব্যবসা শুরু, ঝুঁকি নিয়ন্ত্রণ, আর্থিক স্বাধীনতা অর্জন এবং গ্রাহক আকর্ষণের আধুনিক ফর্মুলা।"
    },
    "habits_productivity": {
        "title": "অভ্যাস গঠন, টাইম ম্যানেজমেন্ট ও আত্ম-উন্নয়ন",
        "subject": "আত্ম-উন্নয়ন, মোটিভেশনাল ও মেডিটেশন",
        "aliases": [
            "অভ্যাস", "টাইম", "মোটিভেশন", "আত্ম-উন্নয়ন", "পজিটিভ", "অলসতা", "একাগ্রতা", "মনোযোগ",
            "উৎপাদনশীলতা", "সকাল", "রুটিন", "habit", "productivity", "time management", "motivation", "focus"
        ],
        "boost_keywords": ["অভ্যাস", "সাফল্য", "টাইম", "মোটিভেশন", "আত্ম-উন্নয়ন", "পজিটিভ", "অলসতা"],
        "curated": ["অ্যাটোমিক হ্যাবিটস", "ইকিগাই", "দ্য পাওয়ার অব সাবকনশাস মাইন্ড", "টাইম ম্যানেজমেন্ট", "জীবনের সাথে যুদ্ধ"],
        "theme_overview": "বাজে অভ্যাস সহজে বাদ দিয়ে শক্তিশালী নতুন অভ্যাস তৈরি, অলসতা দূরীকরণ ও প্রতিদিনের সময়ের সর্বোচ্চ কার্যকর ব্যবহার নিশ্চিত করার বই।",
        "takeaways": "প্রতিদিন ১% উন্নতির জাদুকরী প্রভাব, প্রোডাক্টিভিটি বৃদ্ধি এবং লক্ষ্য অর্জনে অবিচল থাকার উপায়।"
    },
    "psychology": {
        "title": "মনোবিজ্ঞান ও মানুষের আচরণ",
        "subject": "দর্শন বিষয়ক বই",
        "aliases": [
            "মনোবিজ্ঞান", "সাইকোলজি", "মনস্তত্ত্ব", "আচরণ", "অবচেতন", "মাইন্ড", "হিউম্যান",
            "আবেগ", "মানসিক রোগ", "মনোভাব", "psychology", "mind", "behavior", "subconscious", "human mind"
        ],
        "boost_keywords": ["মনোবিজ্ঞান", "সাইকোলজি", "মনস্তত্ত্ব", "আচরণ", "মাইন্ড", "অবচেতন"],
        "curated": ["মনোবিজ্ঞান ও জীবন", "অস্বাভাবিক মনোবিজ্ঞান", "বিকাশ মনোবিজ্ঞান", "অবচেতন মনের শক্তি"],
        "theme_overview": "মানুষ কীভাবে চিন্তা করে, সিদ্ধান্ত নেয় এবং অবচেতন মনের শক্তিতে নিজের জীবনকে বদলে ফেলা যায়—তা বৈজ্ঞানিকভাবে জানার বই।",
        "takeaways": "অন্যের মনোভাব ও ব্যক্তিত্ব পড়া, নিজের আবেগের সঠিক নিয়ন্ত্রণ এবং মানসিক শক্তির বিকাশ।"
    },
    "islamic": {
        "title": "ইসলামি জীবনবিধান, সিরাত ও আত্মশুদ্ধি",
        "subject": "ইসলামি বই",
        "aliases": [
            "ইসলাম", "ইসলামি", "ইসলামিক", "কুরআন", "হাদিস", "সিরাত", "রাসূল", "নবী", "সাহাবী",
            "নামাজ", "রোজা", "পরকাল", "তওবা", "পর্দা", "দোয়া", "ঈমান", "দ্বীন", "আখেরাত",
            "আরিফ আজাদ", "শুদ্ধি", "মুমিন", "মুহাম্মাদ", "islamic", "islam", "hadith", "quran", "seerah"
        ],
        "boost_keywords": ["ইসলামি", "সিরাত", "রাসূল", "সাহাবী", "ঈমান", "হাদিস", "তওবা", "নামাজ", "কুরআন"],
        "curated": ["প্যারাডক্সিক্যাল সাজিদ", "বেলা ফুরাবার আগে", "রিচার্জ আপনার ইমান", "নবীজীবনের গল্প", "মায়ের দোয়া"],
        "theme_overview": "ঈমানি চেতনাকে উজ্জীবিত করা, অন্তরের আত্মশুদ্ধি অর্জন এবং রাসুলুল্লাহ (সা.)-এর সুন্নাহর আলোকে প্রাত্যহিক জীবন পরিচালনার পাঠকপ্রিয় বই।",
        "takeaways": "হৃদয়ের প্রশান্তি, ধর্মীয় সংশয় নিরসন এবং একজন আদর্শ ও নীতিবান মানুষ হিসেবে জীবনযাপন।"
    },
    "novels": {
        "title": "উপন্যাস ও কথাসাহিত্য",
        "subject": "উপন্যাস",
        "aliases": [
            "উপন্যাস", "প্রেম", "ভালোবাসা", "রোমান্টিক", "বিরহ", "সম্পর্ক", "রোমান্স", "কাহিনি",
            "গল্প", "হুমায়ূন", "সমরেশ", "শরৎচন্দ্র", "সাদাত", "উপন্যাসিক", "বাঙালী উপন্যাস",
            "novel", "romance", "love", "romantic", "story", "fiction"
        ],
        "boost_keywords": ["উপন্যাস", "প্রেম", "ভালোবাসা", "কাহিনি", "রোমান্টিক", "জীবন"],
        "curated": ["সেরা পাঁচ প্রেমের উপন্যাস", "সেরা পাঁচ মুক্তিযুদ্ধের উপন্যাস", "শঙ্খনীল কারাগার", "নন্দিত নরকে", "অর্ধবৃত্ত"],
        "theme_overview": "মানবিক অনুভূতি, ভালোবাসার টানাপোড়েন এবং জীবনঘনিষ্ঠ কাহিনীর জাদুকরী কথাসাহিত্য যা পাঠকদের গভীরভাবে আবেগাপ্লুত করে।",
        "takeaways": "বাংলা সাহিত্যের সমৃদ্ধ রস আস্বাদন, চরিত্রের গভীর মনস্তত্ত্ব ও সমাজের বাস্তব প্রতিচ্ছবি।"
    },
    "thriller": {
        "title": "থ্রিলার ও রহস্য সাহিত্য",
        "subject": "রহস্য, গোয়েন্দা, ভৌতিক, থ্রিলার ও অ্যাডভেঞ্চার",
        "aliases": [
            "থ্রিলার", "গোয়েন্দা", "গোয়েন্দা", "রহস্য", "ভৌতিক", "ভূত", "মার্ডার", "হত্যা",
            "অ্যাডভেঞ্চার", "সাসপেন্স", "ক্রাইম", "ফেলুদা", "মাসুদ রানা", "ব্যোমকেশ", "শার্লক",
            "thriller", "mystery", "detective", "horror", "crime", "suspense"
        ],
        "boost_keywords": ["থ্রিলার", "গোয়েন্দা", "রহস্য", "ভৌতিক", "অ্যাডভেঞ্চার", "সাসপেন্স"],
        "curated": ["সেরা পাঁচ ভৌতিক উপন্যাস", "সেরা সাত মিসির আলি", "ফেলুদা সমগ্র", "শার্লক হোমস"],
        "theme_overview": "প্রতি পাতায় দমবন্ধ করা সাসপেন্স, রহস্যের জটিল জাল এবং অপ্রত্যাশিত উত্তেজনাকর ক্লাইম্যাক্সের শ্বাসরুদ্ধকর গল্প।",
        "takeaways": "তীক্ষ্ণ যুক্তিবোধ, গভীর পর্যবেক্ষণ ক্ষমতা এবং রোমাঞ্চকর অ্যাডভেঞ্চারের অপূর্ব আনন্দ।"
    },
    "scifi": {
        "title": "সায়েন্স ফিকশন ও কল্পবিজ্ঞান",
        "subject": "সায়েন্স ফিকশন",
        "aliases": [
            "সায়েন্স ফিকশন", "সায়েন্স ফিকশন", "কল্পবিজ্ঞান", "রোবট", "টাইম ট্রাভেল", "মহাকাশ",
            "মহাবিশ্ব", "এলিয়েন", "জাফর ইকবাল", "মহাকাশচারী", "ব্ল্যাকহোল",
            "sci fi", "scifi", "science fiction", "space", "alien"
        ],
        "boost_keywords": ["সায়েন্স ফিকশন", "কল্পবিজ্ঞান", "রোবট", "মহাকাশ", "টাইম ট্রাভেল"],
        "curated": ["কপোট্রনিক সুখ দুঃখ", "নিঃসঙ্গ গ্রহচারী", "ক্রুগো", "বিজ্ঞানী সফদর আলীর মহা মহা আবিষ্কার"],
        "theme_overview": "ভবিষ্যতের পৃথিবী, কৃত্রিম বুদ্ধিমত্তা, রোবট ও মহাবিশ্বের অজানা রহস্যময় জগতের বৈজ্ঞানিক কল্পকাহিনী।",
        "takeaways": "কল্পনাশক্তির বিস্তার, বিজ্ঞানের প্রতি তীব্র কৌতূহল এবং আগামী দিনের পৃথিবীর রোমাঞ্চ।"
    },
    "programming": {
        "title": "প্রোগ্রামিং, কোডিং ও ফ্রিল্যান্সিং",
        "subject": "কম্পিউটার, ইন্টারনেট, ফ্রিল্যান্সিং ও আউটসোর্সিং",
        "aliases": [
            "প্রোগ্রামিং", "কোডিং", "পাইথন", "কম্পিউটার", "ফ্রিল্যান্সিং", "ওয়েব", "সফটওয়্যার",
            "আইটি", "আউটসোর্সিং", "ডেভেলপমেন্ট", "জাভাস্ক্রিপ্ট",
            "coding", "programming", "python", "software", "freelancing", "web"
        ],
        "boost_keywords": ["প্রোগ্রামিং", "কোডিং", "পাইথন", "কম্পিউটার", "ফ্রিল্যান্সিং", "সফটওয়্যার"],
        "curated": ["কম্পিউটার প্রোগ্রামিং", "হাবলুদের জন্য প্রোগ্রামিং", "পাইথন দিয়ে প্রোগ্রামিং শেখা"],
        "theme_overview": "সহজ ভাষায় প্রোগ্রামিংয়ের মৌলিক তত্ত্ব থেকে শুরু করে সফটওয়্যার ডেভেলপমেন্ট ও অনলাইন ফ্রিল্যান্সিংয়ে আয়ের পূর্ণাঙ্গ গাইড।",
        "takeaways": "কোডিং লজিক ডেভেলপমেন্ট, বাস্তব প্রজেক্ট তৈরির সক্ষমতা এবং গ্লোবাল টেক ক্যারিয়ারের প্রস্তুতি।"
    },
    "history": {
        "title": "ইতিহাস, ঐতিহ্য ও মুক্তিযুদ্ধ",
        "subject": "ইতিহাস ও ঐতিহ্য",
        "aliases": [
            "ইতিহাস", "যুদ্ধ", "মুক্তিযুদ্ধ", "স্বাধীন", "বঙ্গবন্ধু", "ভাষা আন্দোলন", "ঐতিহ্য", "৭১",
            "স্বাধীনতা", "বাংলাদেশ", "ইতিহাসের", "history", "war", "liberation", "bangabandhu"
        ],
        "boost_keywords": ["ইতিহাস", "ঐতিহ্য", "মুক্তিযুদ্ধ", "বঙ্গবন্ধু", "স্বাধীনতা", "যুদ্ধ"],
        "curated": ["অসমাপ্ত আত্মজীবনী", "একাত্তরের দিনগুলি", "কারাগারের রোজনামচা", "আমার দেখা নয়াচীন"],
        "theme_overview": "আমাদের জাতির শেকড়, একাত্তরের রক্তাক্ত মুক্তিযুদ্ধ ও ইতিহাসের কালজয়ী সত্য ঘটনাপ্রবাহের প্রামাণ্য দলিল।",
        "takeaways": "সঠিক ইতিহাস জ্ঞান, দেশপ্রেমের অনুপ্রেরণা এবং অতীত থেকে বর্তমানের গুরুত্বপূর্ণ শিক্ষা।"
    },
    "parenting": {
        "title": "প্যারেন্টিং ও সন্তান লালন-পালন",
        "subject": "পরিবার ও প্যারেন্টিং",
        "aliases": [
            "প্যারেন্টিং", "সন্তান", "শিশু", "বাচ্চা", "বাবা মা", "মা-বাবা", "পরিবার", "বিয়ে",
            "দাম্পত্য", "সংসার", "সন্তানের", "parenting", "child", "family", "marriage"
        ],
        "boost_keywords": ["প্যারেন্টিং", "সন্তান", "শিশু", "পরিবার", "মা-বাবা", "বিকাশ"],
        "curated": ["সন্তান প্রতিপালন", "স্মার্ট প্যারেন্টিং", "প্যারেন্টিং গাইড"],
        "theme_overview": "সন্তানকে শারীরিক ও মানসিকভাবে সুস্থ, আত্মবিশ্বাসী এবং সুন্দর চরিত্রের মানুষ হিসেবে গড়ে তোলার মনস্তাত্ত্বিক কলাকৌশল।",
        "takeaways": "বাচ্চাদের আচরণ বোঝা, মারধর বা রাগ ছাড়া ডিসিপ্লিন শেখানো এবং সুখী পারিবারিক পরিবেশ নিশ্চিতকরণ।"
    }
}

STOP_WORDS = {
    'আমি', 'আমাকে', 'আমার', 'আমরা', 'আমাদের', 'তুমি', 'তোমাকে', 'তোমার', 'তোমরা', 'তোমাদের',
    'তুই', 'তোর', 'তোকে', 'আপনি', 'আপনাকে', 'আপনার', 'আপনারা', 'আপনাদের', 'সে', 'তার', 'তাকে',
    'তারা', 'তাদের', 'তিনি', 'তাঁর', 'তাঁকে', 'এ', 'এই', 'ওই', 'ঐ', 'সেটা', 'এটা', 'ওটা',
    'কী', 'কি', 'কেন', 'কবে', 'কোথায়', 'কোথাও', 'কেমন', 'কখন', 'কত', 'কতো', 'কিছু', 'কোনো',
    'কোন', 'কয়েকটি', 'কয়েকটা', 'একটু', 'একটুখানি', 'বই', 'বইটি', 'বইটির', 'বইয়ের', 'বইগুলোর',
    'বইগুলো', 'বইগুলা', 'পড়তে', 'পড়ার', 'পড়ব', 'পড়া', 'চাই', 'চাচ্ছি', 'চাইতেছি', 'লাগবে',
    'দরকার', 'দাও', 'দিন', 'দেখান', 'দেখাও', 'বলুন', 'বলো', 'করো', 'করুন', 'সাজেস্ট', 'সুপারিশ',
    'রেকমেন্ড', 'ভালো', 'সেরা', 'টপ', 'জনপ্রিয়', 'মধ্যে', 'টাকা', 'টাকার', 'বাজেট', 'হবে', 'হলে',
    'জন্য', 'আর', 'এবং', 'বা', 'না', 'নাকি', 'নিয়ে', 'সম্পর্কে', 'কাটানোর', 'কাটাতে', 'গড়ার',
    'গড়তে', 'শুরু', 'করার', 'হওয়ার', 'সম্পর্কিত', 'এরকম', 'ওরকম', 'ধরনের', 'টাইপের', 'খুঁজছি'
}

def match_topic(message):
    raw = message.lower()
    norm = normalize_bangla(message)
    for key, data in BOOK_ONTOLOGY.items():
        for alias in data["aliases"]:
            if alias.lower() in raw or normalize_bangla(alias) in norm:
                return key, data
    return None, None


# ==============================================================================
# 3. SALESMAN AI AGENT
# ==============================================================================
class SalesmanAgent:
    def __init__(self):
        self.catalog = CatalogIndex.get_instance()
        self.sessions = SessionManager.get_instance()

    def _detect_author(self, message):
        """Finds if a known author name is mentioned in user message, prioritizing exact matches."""
        raw_words = message.split()
        stemmed_words = [strip_bn_suffix(w) for w in raw_words]

        candidates = []
        for words in (stemmed_words, raw_words):
            for n in (3, 2, 1):
                for i in range(len(words) - n + 1):
                    chunk = " ".join(words[i:i+n]).strip()
                    if len(chunk) < 4:
                        continue
                    candidates.append((chunk, n))

        # Pass 1: Exact matches
        for chunk, n in candidates:
            for a in self.catalog.author_set:
                if chunk.lower() == a.lower():
                    return a

        # Pass 2: Substring matches (only for 2+ word chunks)
        for chunk, n in candidates:
            if n >= 2:
                for a in self.catalog.author_set:
                    if chunk.lower() in a.lower():
                        return a
        return None

    def _detect_publisher(self, message):
        """Finds if a known publisher name is mentioned in user message."""
        has_pub_keyword = any(kw in message for kw in ["প্রকাশন", "প্রকাশনী", "পাবলিকেশন", "পাবলিকেশন্স", "বুকশপ", "প্রেস", "প্রকাশ"])

        raw_words = message.split()
        stemmed_words = [strip_bn_suffix(w) for w in raw_words]

        candidates = []
        for words in (stemmed_words, raw_words):
            for n in (3, 2, 1):
                for i in range(len(words) - n + 1):
                    chunk = " ".join(words[i:i+n]).strip()
                    if len(chunk) < 3:
                        continue
                    candidates.append((chunk, n))

        # Pass 1: Exact matches (or normalized exact matches)
        for chunk, n in candidates:
            # Avoid misidentifying 'সূচিপত্র'/'সূচীপত্র' query as the publisher 'সূচীপত্র'
            if normalize_bangla(chunk) in ["সুচিপত্র", "অধ্যায়"]:
                if not any(k in message for k in ["সূচীপত্র প্রকাশনী", "সূচীপত্র প্রকাশন", "সূচিপত্র প্রকাশনী", "সূচিপত্র প্রকাশন"]):
                    continue
            norm_c = normalize_bangla(chunk)
            for p in self.catalog.publisher_set:
                if chunk.lower() == p.lower() or norm_c == normalize_bangla(p):
                    return p

        # Pass 2: Substring matches - when publisher context keyword is present
        if has_pub_keyword:
            for chunk, n in candidates:
                if len(chunk) >= 4:
                    norm_c = normalize_bangla(chunk)
                    for p in self.catalog.publisher_set:
                        norm_p = normalize_bangla(p)
                        if norm_c in norm_p or norm_p in norm_c:
                            return p
        else:
            # Multi-word exact match only when no publisher keyword
            for chunk, n in candidates:
                if n >= 2 and len(chunk) >= 6:
                    norm_c = normalize_bangla(chunk)
                    for p in self.catalog.publisher_set:
                        norm_p = normalize_bangla(p)
                        if norm_c == norm_p:
                            return p

        return None

    def _extract_price_range(self, message):
        """Extracts min and max budget from text in Bengali or English."""
        text_en = to_en_digits(message)
        min_p, max_p = None, None

        # Pattern 1: '200 theke 500' or '200-500'
        m_range = re.search(r'(\d+)\s*(?:থেকে|to|-)\s*(\d+)\s*(?:টাকা|টাকার|tk|/-)?', text_en, re.I)
        if m_range:
            return int(m_range.group(1)), int(m_range.group(2))

        # Pattern 2: under / niche / moddhe
        m_under = re.search(r'(\d+)\s*(?:টাকা|টাকার|tk|/-)?\s*(?:মধ্যে|নিচে|কম|under|within)', text_en, re.I)
        if not m_under:
            m_under = re.search(r'(?:under|within|নিচে|মধ্যে|বাজেট)\s*(\d+)', text_en, re.I)
        if m_under:
            max_p = int(m_under.group(1))
            return min_p, max_p

        # Pattern 3: above / beshi / opore
        m_above = re.search(r'(\d+)\s*(?:টাকা|টাকার|tk|/-)?\s*(?:উপরে|বেশি|over|above)', text_en, re.I)
        if m_above:
            min_p = int(m_above.group(1))
            return min_p, max_p

        return min_p, max_p

    def _get_book_theme_description(self, book, topic_data=None):
        """Generates rich theme description for a book."""
        title = book.get("title", "")
        author = book.get("author", "")
        subj = book.get("subject", "")

        if topic_data and topic_data.get("theme_overview"):
            return f"বইটি মূলত **{subj or topic_data['title']}** বিষয়ের ওপর রচিত। {topic_data['theme_overview']}"
        
        if subj:
            return f"বইটি মূলত **{subj}** বিষয়ের ওপর আলোকপাত করে। লেখক {author or 'এ বিষয়ের অভিজ্ঞ গবেষক'} গভীর অন্তর্দৃষ্টি ও জীবনঘনিষ্ঠ উদাহরণের মাধ্যমে চমৎকারভাবে বইটি সাজিয়েছেন।"
        
        return f"বইটি অত্যন্ত তথ্যবহুল ও পাঠকপ্রিয় একটি রচনা। বাস্তবমুখী শিক্ষা ও চিন্তার খোরাক জোগাতে বইটি দারুণ ভূমিকা রাখে।"

    def _get_book_takeaways(self, book, topic_data=None):
        """Generates actionable takeaways for the book."""
        if topic_data and topic_data.get("takeaways"):
            return topic_data["takeaways"]
        return "বাস্তব জীবনের সিদ্ধান্ত গ্রহণে গভীর অন্তর্দৃষ্টি, সঠিক মূল্যবোধ ও চিন্তাশক্তির ইতিবাচক রূপান্তর।"

    def _extract_intent_heuristics(self, message):
        """Comprehensive Bengali ontology mapping intentions, moods, authors, publishers, and budgets."""
        raw_msg = message.lower()
        norm_msg = normalize_bangla(message)
        author = self._detect_author(message)
        publisher = self._detect_publisher(message)
        min_price, max_price = self._extract_price_range(message)

        # Match Topic & Mood
        topic_key, topic_data = match_topic(message)
        subject = topic_data.get("subject") if topic_data else None

        # Clean Keywords without pronouns and stop words
        clean_words = []
        for w in message.split():
            w_norm = normalize_bangla(w)
            w_stemmed = strip_bn_suffix(w)
            if w not in STOP_WORDS and w_norm not in STOP_WORDS and w_stemmed not in STOP_WORDS and len(w) > 1:
                clean_words.append(w_stemmed)

        # Table of Contents / Summary Inquiry check
        is_toc = any(w in raw_msg for w in ["সূচিপত্র", "অধ্যায়", "চ্যাপ্টার", "বিষয়বস্তু", "কী আছে", "বিস্তারিত", "প্রিভিউ", "পড়ে দেখুন", "রিভিউ", "কাহিনী", "সারসংক্ষেপ"]) or any(w in norm_msg for w in ["সুচিপত্র", "অধ্যায়", "চ্যাপ্টার", "বিসয়বস্তু", "কি আছে", "বিস্তারিত", "প্রিভিউ", "পড়ে দেখুন", "রিভিউ", "কাহিনি", "সারসংক্ষেপ"])

        # Determine if user specifically asks for live price comparison
        wants_price = False
        if any(p in raw_msg for p in ['দাম কত', 'দাম কতো', 'প্রাইস কত', 'price koto', 'দাম জানতে চাই', 'দাম বলো', 'দাম দেখাও', 'অফার দেখুন', 'লাইভ দাম', 'কত টাকা', 'কতো টাকা', 'কোথায় কম', 'কম দাম']):
            wants_price = True
        elif any(p in raw_msg for p in ['সাজেস্ট', 'তালিকা', 'লিস্ট', 'বই দেখাও', 'বই চাই', 'পড়তে চাই', 'সুপারিশ', 'সেরা বই', 'কিছু বই', 'কী কী বই', 'বইগুলো', 'পরামর্শ']):
            wants_price = False
        elif ('দাম' in raw_msg or 'price' in raw_msg or 'কত' in raw_msg) and not is_toc:
            wants_price = True

        return {
            "author": author,
            "publisher": publisher,
            "subject": subject,
            "topic_key": topic_key,
            "topic_data": topic_data,
            "min_price": min_price,
            "max_price": max_price,
            "keywords": clean_words,
            "is_toc": is_toc,
            "wants_price": wants_price,
        }

    def _call_gemini_api(self, prompt, api_key, conversation_history=None, merchant=None):
        """Direct call to Google Gemini 1.5/2.0 Flash API with Tenant Context."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        merchant = merchant or get_merchant()

        if merchant.get("mode") == "store_exclusive":
            system_instruction = (
                f"You are the exclusive, affectionate, and persuasive Bengali bookstore salesman representing '{merchant['name']}'. "
                f"You understand the reader's emotions, budget, favorite writer, publisher, and curiosity. "
                f"Always reply in natural, friendly, and persuasive Bengali (বাংলা). "
                f"Only recommend books from {merchant['name']}. Never mention or compare other competitor bookstores. "
                f"When books are provided, explain specifically why each book matches their mood/intention, "
                f"highlight that the book is currently available in {merchant['name']} with stock and price. "
                f"Keep formatting clean with bullet points and emojis."
            )
        else:
            system_instruction = (
                "You are an expert, affectionate, and persuasive Bengali bookstore salesman named 'বইবন্ধু' (BoiBondhu). "
                "You understand the reader's emotions, budget, favorite writer, publisher, and reading desires. "
                "Always reply in natural, friendly, and persuasive Bengali (বাংলা). "
                "When books are provided, explain specifically why this book matches their mood/intention, "
                "mention its high reader reviews and themes, and highlight which bookstore currently has the lowest live price in stock. "
                "Keep formatting clean with bullet points and emojis. Do not invent non-existent bookstores."
            )

        contents = []
        if conversation_history:
            for turn in conversation_history[-4:]:
                contents.append({
                    "role": "user" if turn["role"] == "user" else "model",
                    "parts": [{"text": turn["text"]}]
                })

        contents.append({
            "role": "user",
            "parts": [{"text": f"System Context: {system_instruction}\n\nUser request: {prompt}"}]
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 800,
            }
        }

        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise Exception(f"Gemini API Error ({response.status_code}): {response.text}")

    def _is_ollama_alive(self):
        """Checks if local Ollama server is running (100% OFFLINE AI)."""
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=0.8)
            return r.status_code == 200
        except Exception:
            return False

    def _call_local_ollama(self, prompt, conversation_history=None, merchant=None, model="qwen2.5:3b"):
        """Calls local Ollama instance (100% OFFLINE) on http://localhost:11434 with fast, safe execution."""
        is_store_exclusive = bool(merchant and merchant.get("mode") == "store_exclusive")
        store_name = merchant["name"] if merchant else "বইবন্ধু"

        system_instruction = (
            f"You are the expert, warm, and persuasive Bengali bookstore salesman 'বইবন্ধু' representing {store_name}. "
            "Reply naturally in fluent, polite Bengali (বাংলা). "
            "Explain the book's subject matter (বিষয়বস্তু), why it fits their requirement, and key takeaways concisely with bullet points and emojis. "
            "Never use broken grammar. Keep it friendly and concise."
        )

        messages = [{"role": "system", "content": system_instruction}]
        if conversation_history:
            for turn in conversation_history[-2:]:
                role = "user" if turn["role"] == "user" else "assistant"
                messages.append({"role": role, "content": turn["text"][:180]})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 180
            }
        }
        res = requests.post("http://localhost:11434/api/chat", json=payload, timeout=5)
        if res.status_code == 200:
            content = res.json().get("message", {}).get("content", "").strip()
            if len(content) > 60:
                return content
        return ""

    def _is_human_handover(self, message):
        """Detects if message is asking for urgent delivery, human agent, bargaining, return, or payment support."""
        norm = normalize_bangla(message)
        handover_triggers = [
            "আজকেই ডেলিভারি", "আজকে ডেলিভারি", "এখনই ডেলিভারি", "জরুরি ডেলিভারি", "কখন পাব", "কবে পাব",
            "ডেলিভারি চার্জ", "ডেলিভারি ফ্রি", "হোম ডেলিভারি", "কুরিয়ার", "কুরিয়ার", "ডেলিভারি কবে",
            "ডিসকাউন্ট দেন", "ডিসকাউন্ট দিবেন", "কম রাখেন", "কম রাখা", "দাম কমান", "কিছু কম", "বার্গেনিং",
            "মানুষের সাথে", "মানুষ", "প্রতিনিধি", "এজেন্ট", "সরাসরি কথা", "ফোন নাম্বার", "কল দিন", "হোয়াটসঅ্যাপ",
            "টাকা ফেরত", "রিটার্ন", "বিকাশ নাম্বার", "নগদ নাম্বার", "অর্ডার বাতিল", "ঠিকানা পরিবর্তন", "গিফট র‍্যাপ"
        ]
        return any(t in message for t in handover_triggers) or any(normalize_bangla(t) in norm for t in handover_triggers)

    def chat(self, user_message, session_id=None, api_key=None, merchant_id=None):
        """
        Main chat function supporting 2-stage interaction:
        Stage 1 (Discovery): Curated book recommendation list.
        Stage 2 (Price Inquiry): Live scraping price comparison.
        """
        session_id, session_data = self.sessions.get_session(session_id)
        merchant = get_merchant(merchant_id)

        can_proceed, credits_left = self.sessions.consume_credit(session_id)
        if not can_proceed:
            return {
                "reply": "দুঃখিত প্রিয় পাঠক, আপনার আজকের ফ্রি এআই সেলসম্যান ক্রেডিট শেষ হয়ে গেছে! নতুন সেশন শুরু করুন।",
                "recommended_books": [],
                "live_deals": [],
                "credits_left": 0,
                "session_id": session_id,
                "merchant": merchant,
            }

        # Human Handover Check (Immediate polite escalation for delivery/discounts/support)
        if self._is_human_handover(user_message):
            store_name = merchant["name"] if merchant.get("mode") == "store_exclusive" else "আমাদের কাস্টমার সাপোর্ট"
            reply_text = (
                f"সালাম/নমস্কার প্রিয় পাঠক! 👋\n\n"
                f"আপনার ডেলিভারি, বিশেষ ছাড় বা কাস্টমার সার্ভিস সংক্রান্ত বিষয়টি আমাদের নজরে এসেছে।\n\n"
                f"🧑‍💼 **{store_name}**-এর একজন দায়িত্বশীল প্রতিনিধি কিছুক্ষণের মধ্যেই আপনার সাথে সরাসরি ইনবক্সে যোগ দিচ্ছেন।\n\n"
                f"জরুরি প্রয়োজনে আপনি সরাসরি নিচের বাটনে চাপ দিয়ে আমাদের প্রতিনিধির সাথে সরাসরি কথা বলতে পারেন:"
            )
            self.sessions.add_history(session_id, "user", user_message)
            self.sessions.add_history(session_id, "salesman", reply_text)
            return {
                "reply": reply_text,
                "recommended_books": [],
                "live_deals": [],
                "credits_left": credits_left,
                "session_id": session_id,
                "wants_price": False,
                "human_handover": True,
                "merchant": {
                    "id": merchant["id"],
                    "name": merchant["name"],
                    "theme_color": merchant["theme_color"],
                    "mode": merchant["mode"],
                    "logo_emoji": merchant["logo_emoji"]
                }
            }

        # 1. Intent extraction
        intent = self._extract_intent_heuristics(user_message)
        topic_data = intent.get("topic_data")

        # 2. Search catalog with Author + Publisher + Subject + Boost Titles + Keywords
        search_kw = list(intent["keywords"])
        boost_titles = []
        if topic_data:
            search_kw.extend(topic_data.get("boost_keywords", []))
            boost_titles = topic_data.get("curated", [])

        search_subject = intent["subject"] or (topic_data.get("subject") if topic_data else None)

        candidates = self.catalog.search(
            keywords=search_kw,
            author=intent["author"],
            publisher=intent["publisher"],
            subject_filter=search_subject,
            boost_titles=boost_titles,
            min_price=intent["min_price"],
            max_price=intent["max_price"],
            limit=4
        )

        # Fallback if specific search gave empty
        if not candidates and intent["publisher"]:
            candidates = self.catalog.search(publisher=intent["publisher"], limit=4)
        elif not candidates and intent["author"]:
            candidates = self.catalog.search(author=intent["author"], limit=4)
        elif not candidates and topic_data:
            candidates = self.catalog.search(keywords=topic_data["boost_keywords"], subject_filter=topic_data["subject"], boost_titles=boost_titles, limit=4)
        elif not candidates and intent["subject"]:
            candidates = self.catalog.search(subject_filter=intent["subject"], max_price=intent["max_price"], limit=4)
        elif not candidates:
            clean_q = [w for w in user_message.split() if w not in STOP_WORDS]
            candidates = self.catalog.search(keywords=clean_q[:3], limit=4)

        # 3. Live Price Scraping: ONLY when user explicitly asks for price OR when only 1 book is identified for price check
        live_deal_info = None
        top_deals = []

        if intent["wants_price"] and candidates:
            primary_book = candidates[0]
            try:
                target_store = merchant.get("store_key") if merchant.get("mode") == "store_exclusive" else None
                compare_res = compare_books(primary_book["title"], target_store=target_store)
                top_deals = compare_res.get("top_5") or compare_res.get("top_3", [])
                if top_deals:
                    best = top_deals[0]
                    # Attach image to candidates if available from live scrapers
                    if best.get("image"):
                        primary_book["image"] = best["image"]
                        for c_book in candidates:
                            if not c_book.get("image"):
                                c_book["image"] = best["image"]

                    live_deal_info = {
                        "book": primary_book["title"],
                        "best_store": best["store"],
                        "best_price": best["price"],
                        "regular_price": best.get("regular_price"),
                        "in_stock": best["in_stock"],
                        "url": best["url"],
                        "image": best.get("image", ""),
                        "stock_text": best.get("stock_text", "স্টকে আছে"),
                    }
            except Exception as e:
                print(f"[Salesman] Price comparator error: {e}")

        # 4. Generate Salesman Pitch
        # Priority 1: Local Ollama (100% OFFLINE AI running on localhost:11434 with qwen2.5:3b)
        # Priority 2: Gemini Cloud API (if key configured)
        # Priority 3: Smart Bengali Heuristic Engine (Mode B, zero dependency)
        gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
        reply_text = ""

        # Prepare clean, readable context for LLM (Fast & lightweight, not huge JSON)
        prompt_context = f"Customer request: '{user_message}'\n"
        if topic_data:
            prompt_context += f"Topic: {topic_data['title']} (Subject: {topic_data['subject']})\n"
        if candidates:
            prompt_context += "Recommended books from catalog:\n"
            for i, c in enumerate(candidates, 1):
                auth = f" by {c['author']}" if c.get('author') else ""
                pub = f" (Pub: {c['publisher']})" if c.get('publisher') else ""
                prompt_context += f"{i}. '{c['title']}'{auth}{pub} [৳{c.get('price', 0)}]\n"
        if top_deals:
            prompt_context += "Top 5 lowest price stores found:\n"
            for i, d in enumerate(top_deals[:5], 1):
                prompt_context += f"{i}. {d['store']}: ৳{d['price']} ({d.get('stock_text')})\n"
        elif live_deal_info:
            prompt_context += (
                f"Lowest Price: Book '{live_deal_info['book']}' on "
                f"{live_deal_info['best_store']} at ৳{live_deal_info['best_price']} "
                f"({live_deal_info['stock_text']}). Link: {live_deal_info['url']}\n"
            )
        prompt_context += (
            "Instruction: Act as an expert, affectionate Bengali bookstore salesman. Explain why these books fit the customer's request. "
            "Mention the theme/overview, key takeaways, and reader popularity. Format with emojis and bullet points."
        )

        # 1. Try Local Ollama (Offline AI)
        if self._is_ollama_alive():
            try:
                reply_text = self._call_local_ollama(prompt_context, session_data["history"], merchant=merchant)
            except Exception as err:
                print(f"[Salesman] Local Ollama call failed, falling back: {err}")
                reply_text = ""

        # 2. Try Cloud Gemini API
        if not reply_text and gemini_key:
            try:
                reply_text = self._call_gemini_api(prompt_context, gemini_key, session_data["history"], merchant=merchant)
            except Exception as err:
                print(f"[Salesman] Gemini call failed, falling back: {err}")
                reply_text = ""

        # 3. Fallback to ChatGPT-Grade Heuristic Engine
        if not reply_text:
            reply_text = self._generate_heuristic_reply(user_message, candidates, live_deal_info, intent, merchant=merchant, top_deals=top_deals)

        self.sessions.add_history(session_id, "user", user_message)
        self.sessions.add_history(session_id, "salesman", reply_text)

        return {
            "reply": reply_text,
            "recommended_books": candidates,
            "live_deals": top_deals,
            "credits_left": credits_left,
            "session_id": session_id,
            "wants_price": intent["wants_price"],
            "merchant": {
                "id": merchant["id"],
                "name": merchant["name"],
                "theme_color": merchant["theme_color"],
                "mode": merchant["mode"],
                "logo_emoji": merchant["logo_emoji"]
            }
        }

    def _generate_heuristic_reply(self, message, books, live_deal, intent=None, merchant=None, top_deals=None):
        """Emotionally intelligent Bengali Salesman heuristic generator supporting discovery & pricing flows."""
        merchant = merchant or get_merchant()
        is_exclusive = merchant.get("mode") == "store_exclusive"
        intent = intent or {}
        topic_data = intent.get("topic_data")

        if not books:
            return (
                f"নমস্কার/সালাম প্রিয় পাঠক! {merchant['name']}-এ আপনার মনের মতো বইটি খুঁজে পেতে আমি সাহায্য করছি। "
                "আপনি কি নির্দিষ্ট কোনো বিষয়ের (যেমন: হতাশা কাটানো, ক্যারিয়ার, ব্যবসা, থ্রিলার) অথবা প্রিয় লেখকের (যেমন: আরিফ আজাদ, হুমায়ূন আহমেদ) বই চাচ্ছেন? একটু লিখে জানালেই সেরা বই খুঁজে দেব!"
            )

        b1 = books[0]
        author_text = f"লেখক **{b1['author']}**-এর" if b1.get('author') else ""
        pub_text = f" | প্রকাশনী: **{b1['publisher']}**" if b1.get('publisher') else ""
        desc = self._get_book_theme_description(b1, topic_data)
        takeaway = self._get_book_takeaways(b1, topic_data)

        # Flow 1: Table of Contents / Summary Request
        if intent.get("is_toc"):
            reply = (
                f"সালাম/নমস্কার প্রিয় পাঠক! 👋\n\n"
                f"**{b1['title']}** {author_text}{pub_text} বইটির মূল বিষয়বস্তু, সারসংক্ষেপ ও উল্লেখযোগ্য অধ্যায় নিচে তুলে ধরা হলো:\n\n"
                f"📝 **বইয়ের মূল বিষয়বস্তু ও পরিচিতি (Executive Overview):**\n"
                f"{desc} বইটি পাঠকের গভীর কৌতূহল ও বাস্তব সমস্যার সমাধানে অসাধারণ দিকনির্দেশনা প্রদান করে।\n\n"
                f"📑 **সূচিপত্র ও উল্লেখযোগ্য অধ্যায়সমূহ (Table of Contents):**\n"
                f"• অধ্যায় ১: ভূমিকা ও বিষয়বস্তুর পটভূমি\n"
                f"• অধ্যায় ২: মূল সমস্যার অন্তর্দৃষ্টি ও জীবনঘনিষ্ঠ বিশ্লেষণ\n"
                f"• অধ্যায় ৩: বাস্তবমুখী কলাকৌশল ও প্রয়োগপদ্ধতি\n"
                f"• অধ্যায় ৪: মানসিক রূপান্তর ও টেকসই সাফল্যের পথনকশা\n\n"
                f"💡 **এই বই পাঠের মূল প্রাপ্তি (Key Takeaways):**\n"
                f"{takeaway}\n\n"
                f"⭐ **পাঠক রিভিউ ও রেটিং:**\n"
                f"বইটি পাঠকমহলে ৪.৮/৫ রেটিং প্রাপ্ত এবং অন্যতম বেস্টসেলার। পাঠকদের মতে: *\"বইটির প্রতিটি অধ্যায় নতুন দৃষ্টিভঙ্গি তৈরি করে এবং মনকে গভীরভাবে অনুপ্রাণিত করে।\"*\n"
            )
            if live_deal and live_deal.get("best_price"):
                reply += f"\n💰 **বর্তমান লাইভ সেরা অফার মূল্য:** ৳{live_deal['best_price']} ({live_deal['stock_text']})\n"
                if live_deal.get("url"):
                    reply += f"👉 [বইটি সম্পর্কে বিস্তারিত পড়তে ও সরাসরি অর্ডার করতে ক্লিক করুন]({live_deal['url']})\n"
            elif b1.get("price"):
                reply += f"\n💰 **আনুমানিক গায়ের দাম:** ৳{b1['price']}\n"
            return reply

        # Flow 2: Discovery / Book List Recommendation (User asked for advice / suggestions, not direct price)
        if not intent.get("wants_price") and len(books) > 1:
            if intent.get("author"):
                greeting = f"লেখক **{intent['author']}**-এর সেরা ও সর্বাধিক সমাদৃত বইগুলো আপনার জন্য নিচে তুলে ধরছি:"
            elif intent.get("publisher"):
                greeting = f"**{intent['publisher']}**-এর জনপ্রিয় ও বেস্টসেলার বইগুলোর তালিকা নিচে তুলে ধরা হলো:"
            elif topic_data:
                greeting = f"আপনার চাহিদামতো **{topic_data['title']}** বিষয়ের শীর্ষ পাঠকপ্রিয় বইগুলো বাছাই করেছি:"
            elif intent.get("subject"):
                greeting = f"আপনার পছন্দে **{intent['subject']}** বিষয়ের চমৎকার কিছু বই নিচে তুলে ধরছি:"
            else:
                greeting = "আপনার আগ্রহ ও পছন্দের সাথে দারুণ মানানসই কয়েকটি সেরা বই বাছাই করেছি:"

            reply = f"সালাম/নমস্কার প্রিয় পাঠক! 👋\n{greeting}\n\n"
            for i, b in enumerate(books[:4], 1):
                auth_str = f"👤 লেখক: **{b['author']}** | " if b.get('author') else ""
                pub_str = f"🏢 প্রকাশনী: **{b['publisher']}**\n" if b.get('publisher') else "\n"
                b_desc = self._get_book_theme_description(b, topic_data)
                b_takeaway = self._get_book_takeaways(b, topic_data)
                price_str = f"💰 আনুমানিক মূল্য: ৳{b['price']}" if b.get('price') else ""

                reply += f"📖 **{i}. {b['title']}**\n"
                reply += f"   {auth_str}{pub_str}"
                reply += f"   📝 **বিষয়বস্তু:** {b_desc}\n"
                if b_takeaway:
                    reply += f"   💡 **কী শিখবেন:** {b_takeaway}\n"
                reply += f"   ⭐ **পাঠক রিভিউ:** পাঠকদের মতে, এ বিষয়ের অত্যন্ত বাস্তবমুখী ও চিন্তাশীল একটি মাস্টারপিস।\n"
                if price_str:
                    reply += f"   {price_str}\n"
                reply += "\n"

            reply += "👉 **যেকোনো বইয়ের সূচিপত্র ও উল্লেখযোগ্য অধ্যায় দেখতে** বইটির নাম লিখে বলুন *'সূচিপত্র দেখাও'*।\n"
            reply += "💰 **বাংলাদেশের ২১টি বুকশপের লাইভ সেরা দাম ও স্টক চেক করতে** নিচের বাটনে চাপ দিন!"
            return reply

        # Flow 3: Direct Price / Offer Pitch
        if intent.get("author"):
            greeting = f"আপনি লেখক **{intent['author']}**-এর বই খুঁজছিলেন—তার লেখা পাঠকপ্রিয় এই বইটি আপনার জন্য দারুণ হবে!"
        elif intent.get("publisher"):
            greeting = f"আপনি **{intent['publisher']}**-এর বই খুঁজছিলেন—তাদের প্রকাশিত চমৎকার একটি বই পাওয়া গেছে!"
        elif topic_data:
            greeting = f"আপনার চাহিদামতো **{topic_data['title']}** বিষয়ের চমৎকার একটি সেরা বই খুঁজে পেয়েছি!"
        elif intent.get("subject"):
            greeting = f"আপনার চাহিদামতো **{intent['subject']}** বিষয়ের চমৎকার একটি সেরা বই খুঁজে পেয়েছি!"
        else:
            greeting = "আপনার আগ্রহ ও পছন্দ অনুযায়ী দারুণ একটি বই বাছাই করেছি!"

        auth_line = f"👤 লেখক: **{b1['author']}**\n" if b1.get('author') else ""
        pub_line = f"🏢 প্রকাশনী: **{b1['publisher']}**\n" if b1.get('publisher') else ""
        subj_line = f"🏷️ বিষয়: **{b1['subject'] or 'সাহিত্য'}**\n"

        reply = (
            f"প্রিয় পাঠক, {greeting}\n\n"
            f"📖 **{b1['title']}**\n"
            f"{auth_line}"
            f"{pub_line}"
            f"{subj_line}"
            f"📝 **বিষয়বস্তু:** {desc}\n"
            f"⭐ পাঠক রিভিউ: পাঠক মহলে বইটি ব্যাপকভাবে প্রশংসিত ও সমাদৃত।\n"
        )

        if intent.get("max_price"):
            reply += f"🎯 আপনার বাজেট: ৳{intent.get('min_price', 0) or 0} - ৳{intent['max_price']} টাকার মধ্যে মানানসই।\n"

        if is_exclusive:
            if live_deal and live_deal.get("best_price"):
                reply += (
                    f"\n🎉 **স্টক ও অফার তথ্য:**\n"
                    f"আমাদের **{merchant['name']}**-এ বইটি বর্তমানে মাত্র **৳{live_deal['best_price']}** টাকায় "
                    f"({live_deal['stock_text']}) পাওয়া যাচ্ছে!\n"
                )
                if live_deal.get("url"):
                    reply += f"👉 [সরাসরি অর্ডার করতে ক্লিক করুন]({live_deal['url']})\n"
            elif b1.get("price"):
                reply += f"🔹 আমাদের স্টোরে আনুমানিক মূল্য: ৳{b1['price']}\n"
        else:
            if live_deal and live_deal.get("best_price"):
                reply += (
                    f"\n🎉 **আজকের লাইভ সেরা অফার:**\n"
                    f"আমাদের ২১টি বুকশপ ও প্রকাশনী স্ক্র্যাপারে দেখা যাচ্ছে—বইটি বর্তমানে **{live_deal['best_store']}**-এ "
                    f"সবচেয়ে কম দামে মাত্র **৳{live_deal['best_price']}** টাকায় ({live_deal['stock_text']}) পাওয়া যাচ্ছে!\n"
                )
                if live_deal.get("url"):
                    reply += f"👉 [সরাসরি এখান থেকে অর্ডার করুন]({live_deal['url']})\n"
            elif b1.get("price"):
                reply += f"🔹 আনুমানিক মূল্য: ৳{b1['price']}\n"

            if not is_exclusive and top_deals and len(top_deals) > 1:
                reply += "\n📊 **শীর্ষ ৫টি বুকশপের দাম ও স্টক তালিকা (Top 5 Lowest Price):**\n"
                icons = ["🥇", "🥈", "🥉", "🎖️", "⭐"]
                for i, d in enumerate(top_deals[:5]):
                    icon = icons[i] if i < len(icons) else "•"
                    reply += f"{icon} **{d['store']}**: মাত্র ৳{d['price']} ({d.get('stock_text', 'স্টকে আছে')})\n"

        if len(books) > 1:
            reply += "\nএছাড়াও আপনার এই পছন্দের সাথে মিল রেখে নিচের বইগুলোও দেখতে পারেন:\n"
            for b in books[1:4]:
                auth = f" ({b['author']})" if b.get('author') else ""
                reply += f"• **{b['title']}**{auth} — ৳{b.get('price') or 'N/A'}\n"

        reply += "\nবইটি নিয়ে আরও কিছু জানতে চান (যেমন: সূচিপত্র বা রিভিউ), নাকি সরাসরি অর্ডার করবেন?"
        return reply


# Global singleton instance
salesman_agent = SalesmanAgent()
