"""
B2B Multi-Tenant Merchant Registry for Bookstore SaaS
------------------------------------------------------
Manages client bookstores who subscribe to the AI Salesman service (৳1,500 - ৳2,500/month).
In 'store_exclusive' mode, the bot ONLY displays and recommends books from the subscribing store,
completely hiding competitor stores and prices.
"""

MERCHANTS = {
    "ruhama": {
        "id": "ruhama",
        "name": "রূহামা শপ AI সেলসম্যান",
        "store_key": "Ruhama Shop",
        "theme_color": "#059669",
        "theme_gradient": "linear-gradient(135deg, #065f46 0%, #059669 100%)",
        "logo_emoji": "🕌",
        "greeting": "সালাম! রূহামা শপ (ruhamashop.com)-এর ভার্চুয়াল সেলসম্যানে আপনাকে স্বাগতম। আমাদের বুকস্টোর থেকে আপনার পছন্দের বইটি খুঁজে দিচ্ছি!",
        "mode": "store_exclusive",
        "plan": "Standard B2B (৳১,৫০০/মাস)",
        "website": "https://www.ruhamashop.com",
        "monthly_fee": 1500,
        "features": ["ওয়েবসাইট চ্যাট উইজেট", "রূহামা এক্সক্লুসিভ বুক ফিল্টারিং", "২,০০০ কনভারসেশন/মাস"],
    },
    "aladaboi": {
        "id": "aladaboi",
        "name": "আলাদা বই AI সেলসম্যান",
        "store_key": "AladaBoi",
        "theme_color": "#2563eb",
        "theme_gradient": "linear-gradient(135deg, #1e40af 0%, #2563eb 100%)",
        "logo_emoji": "📖",
        "greeting": "সালাম! আলাদা বই (aladaboi.com)-এর স্মার্ট সেলসম্যান বলছি। আমাদের কালেকশন থেকে কী বই খুঁজছেন?",
        "mode": "store_exclusive",
        "plan": "Standard B2B (৳১,৫০০/মাস)",
        "website": "https://www.aladaboi.com",
        "monthly_fee": 1500,
        "features": ["ওয়েবসাইট চ্যাট উইজেট", "আলাদা বই এক্সক্লুসিভ ফিল্টারিং", "২,০০০ কনভারসেশন/মাস"],
    },
    "baatighar": {
        "id": "baatighar",
        "name": "বাতিঘর ভার্চুয়াল সেলসম্যান",
        "store_key": "Baatighar",
        "theme_color": "#d97706",
        "theme_gradient": "linear-gradient(135deg, #b45309 0%, #d97706 100%)",
        "logo_emoji": "🏮",
        "greeting": "নমস্কার/সালাম! বাতিঘর অনলাইন বুকশপে আপনাকে স্বাগতম। সাহিত্য, ইতিহাস বা গবেষণার কী বই পড়তে চান?",
        "mode": "store_exclusive",
        "plan": "Pro B2B (৳২,৫০০/মাস)",
        "website": "https://baatighar.com",
        "monthly_fee": 2500,
        "features": ["ওয়েবসাইট উইজেট + ফেসবুক মেসেঞ্জার", "বাতিঘর এক্সক্লুসিভ ফিল্টারিং", "আনলিমিটেড কনভারসেশন"],
    },
    "wafilife": {
        "id": "wafilife",
        "name": "ওয়াফিলাইফ AI সেলসম্যান",
        "store_key": "Wafilife",
        "theme_color": "#0891b2",
        "theme_gradient": "linear-gradient(135deg, #0e7490 0%, #0891b2 100%)",
        "logo_emoji": "📚",
        "greeting": "সালাম! ওয়াফিলাইফে আপনাকে স্বাগতম। আমাদের ৬০ হাজার বইয়ের সমৃদ্ধ কালেকশন থেকে আপনার মনের মতো বই বেছে নিন!",
        "mode": "store_exclusive",
        "plan": "Pro B2B (৳২,৫০০/মাস)",
        "website": "https://www.wafilife.com",
        "monthly_fee": 2500,
        "features": ["ওয়েবসাইট উইজেট + ফেসবুক মেসেঞ্জার", "৬০k ক্যাটালগ সার্চ", "আনলিমিটেড কনভারসেশন"],
    },
    "prothoma": {
        "id": "prothoma",
        "name": "প্রথমা প্রকাশন সেলস অ্যাসিস্ট্যান্ট",
        "store_key": "Prothoma",
        "theme_color": "#dc2626",
        "theme_gradient": "linear-gradient(135deg, #991b1b 0%, #dc2626 100%)",
        "logo_emoji": "🔖",
        "greeting": "প্রথমা প্রকাশনে আপনাকে স্বাগতম। নতুন ও সেরা বইগুলো দেখতে কী বই খুঁজছেন লিখুন।",
        "mode": "store_exclusive",
        "plan": "Standard B2B (৳১,৫০০/মাস)",
        "website": "https://prothoma.com",
        "monthly_fee": 1500,
        "features": ["ওয়েবসাইট উইজেট", "প্রথমা এক্সক্লুসিভ ফিল্টারিং", "২,০০০ কনভারসেশন/মাস"],
    },
    "guardian": {
        "id": "guardian",
        "name": "গার্ডিয়ান পাবলিকেশনস AI সেলসম্যান",
        "store_key": "Guardian Publications",
        "theme_color": "#0d9488",
        "theme_gradient": "linear-gradient(135deg, #115e59 0%, #0d9488 100%)",
        "logo_emoji": "🛡️",
        "greeting": "সালাম! গার্ডিয়ান পাবলিকেশনস (guardianpubs.com)-এর অফিসিয়াল এআই সেলসম্যানে স্বাগতম। আমাদের প্রকাশিত সেরা বইগুলো খুঁজে দিচ্ছি!",
        "mode": "store_exclusive",
        "plan": "Pro B2B (৳২,৫০০/মাস)",
        "website": "https://guardianpubs.com",
        "monthly_fee": 2500,
        "features": ["ওয়েবসাইট উইজেট + ফেসবুক পেজ", "গার্ডিয়ান ডিরেক্ট API ফিল্টারিং", "আনলিমিটেড কনভারসেশন"],
    },
    "oitijjhya": {
        "id": "oitijjhya",
        "name": "ঐতিহ্য প্রকাশনী ভার্চুয়াল সেলসম্যান",
        "store_key": "Oitijjhya",
        "theme_color": "#b45309",
        "theme_gradient": "linear-gradient(135deg, #78350f 0%, #b45309 100%)",
        "logo_emoji": "🏛️",
        "greeting": "নমস্কার/সালাম! ঐতিহ্য প্রকাশনীতে আপনাকে স্বাগতম। আমাদের সমৃদ্ধ সাহিত্যের বই সম্ভার থেকে কী বই খুঁজছেন?",
        "mode": "store_exclusive",
        "plan": "Pro B2B (৳২,৫০০/মাস)",
        "website": "https://oitijjhya.com",
        "monthly_fee": 2500,
        "features": ["ওয়েবসাইট উইজেট + ফেসবুক পেজ", "ঐতিহ্য ক্যাটালগ ফিল্টারিং", "আনলিমিটেড কনভারসেশন"],
    },
    "anyaprokash": {
        "id": "anyaprokash",
        "name": "অন্যপ্রকাশ AI সেলস অ্যাসিস্ট্যান্ট",
        "store_key": "AnyaProkash",
        "theme_color": "#7c3aed",
        "theme_gradient": "linear-gradient(135deg, #5b21b6 0%, #7c3aed 100%)",
        "logo_emoji": "✨",
        "greeting": "অন্যপ্রকাশে স্বাগতম! হুমায়ূন আহমেদসহ জনপ্রিয় লেখকদের নতুন ও সেরা বইগুলো বেছে নিতে সাহায্য করছি।",
        "mode": "store_exclusive",
        "plan": "Pro B2B (৳২,৫০০/মাস)",
        "website": "https://anyaprokash.com",
        "monthly_fee": 2500,
        "features": ["Shopify ডিরেক্ট ইন্টিগ্রেশন", "অন্যপ্রকাশ এক্সক্লুসিভ বুক ফিল্টারিং", "আনলিমিটেড কনভারসেশন"],
    },
    "default": {
        "id": "default",
        "name": "বইবন্ধু AI (২১+ বুকশপ ও প্রকাশনী প্রাইস ফাইন্ডার)",
        "store_key": None,
        "theme_color": "#1e3a8a",
        "theme_gradient": "linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)",
        "logo_emoji": "🤖",
        "greeting": "সালাম/নমস্কার! আমি বইবন্ধু—বাংলাদেশের ২১টি অনলাইন বুকশপ ও শীর্ষ প্রকাশনী থেকে যাচাই করে সবচেয়ে কম দাম ও সেরা ডিল বের করে দিতে প্রস্তুত।",
        "mode": "neutral_comparator",
        "plan": "Public Comparator",
        "website": "/",
        "monthly_fee": 0,
        "features": ["২১টি অনলাইন বুকশপ ও প্রকাশনীতে লাইভ দাম তুলনা", "টপ ৩ সর্বনিম্ন দাম কার্ড", "সরাসরি ক্রয়ের লিংক"],
    }
}


def get_merchant(merchant_id=None):
    """Retrieves tenant config by id; defaults to 'default'."""
    if not merchant_id:
        return MERCHANTS["default"]
    m_id = str(merchant_id).lower().strip()
    return MERCHANTS.get(m_id, MERCHANTS["default"])


def list_merchants():
    """Lists all registered bookstore merchants."""
    return [m for k, m in MERCHANTS.items() if k != "default"]


def register_custom_merchant(m_id, name, store_key, theme_color="#1e3a8a", greeting=None, mode="store_exclusive"):
    """Allows dynamic registration of a new bookstore client."""
    m_id = m_id.lower().strip()
    MERCHANTS[m_id] = {
        "id": m_id,
        "name": name,
        "store_key": store_key,
        "theme_color": theme_color,
        "theme_gradient": f"linear-gradient(135deg, {theme_color} 0%, #2563eb 100%)",
        "logo_emoji": "📖",
        "greeting": greeting or f"স্বাগতম! {name}-এর ভার্চুয়াল সেলসম্যান আপনার সেবায় প্রস্তুত।",
        "mode": mode,
        "plan": "Custom B2B (৳১,৫০০ - ৳২,৫০০/মাস)",
        "website": "",
        "monthly_fee": 1500,
        "features": ["কাস্টম স্টোর উইজেট", "এক্সক্লুসিভ কালেকশন", "মেসেঞ্জার ও ওয়েব সাপোর্ট"],
    }
    return MERCHANTS[m_id]
