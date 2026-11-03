"""
Banglish to Bengali (বাংলা) Phonetic Transliterator & Title Matcher
Converts Romanized Bengali (e.g., 'shonkhonil karagar', 'humayun ahmed', 'bela phurabar age')
into proper Bengali Unicode text and maps to the bookstore catalog.
"""

import re
from typing import Optional, Tuple

# Comprehensive dictionary for most searched Bangladeshi books, authors, and genres
BANGLISH_DICTIONARY = {
    # Authors
    "humayun ahmed": "হুমায়ূন আহমেদ",
    "humayun": "হুমায়ূন আহমেদ",
    "humayun ahmed er boi": "হুমায়ূন আহমেদ",
    "arif azad": "আরিফ আজাদ",
    "arif azad er boi": "আরিফ আজাদ",
    "jhankar mahbub": "ঝংকার মাহবুব",
    "jhankar": "ঝংকার মাহবুব",
    "ayman sadiq": "আয়মান সাদিক",
    "sadat hossain": "সাদাত হোসাইন",
    "tamim shahriar subeen": "তামিম শাহরিয়ার সুবিন",
    "subeen": "তামিম শাহরিয়ার সুবিন",
    "rabindranath tagore": "রবীন্দ্রনাথ ঠাকুর",
    "rabindranath": "রবীন্দ্রনাথ ঠাকুর",
    "robindronath": "রবীন্দ্রনাথ ঠাকুর",
    "kazi nazrul islam": "কাজী নজরুল ইসলাম",
    "nazrul": "কাজী নজরুল ইসলাম",
    "sharat chandra": "শরৎচন্দ্র চট্টোপাধ্যায়",
    "shorot chondro": "শরৎচন্দ্র চট্টোপাধ্যায়",
    "bibhutibhushan": "বিভূতিভূষণ বন্দ্যোপাধ্যায়",
    "satyajit ray": "সত্যজিৎ রায়",
    "jafar iqbal": "মুহম্মদ জাফর ইকবাল",
    "muhammad jafar iqbal": "মুহম্মদ জাফর ইকবাল",
    "shamsur rahman": "শামসুর রাহমান",
    "rakib hasan": "রকিব হাসান",
    "sheba prokashoni": "সেবা প্রকাশনী",
    "dale carnegie": "ডেল কার্নেগী",
    "james clear": "জেমস ক্লিয়ার",

    # Popular Books
    "paradoxical sajid": "প্যারাডক্সিক্যাল সাজিদ",
    "paradoxical sajid 1": "প্যারাডক্সিক্যাল সাজিদ ১",
    "paradoxical sajid 2": "প্যারাডক্সিক্যাল সাজিদ ২",
    "paradoxical": "প্যারাডক্সিক্যাল সাজিদ",
    "bela phurabar age": "বেলা ফুরাবার আগে",
    "bela furabar age": "বেলা ফুরাবার আগে",
    "shonkhonil karagar": "শঙ্খনীল কারাগার",
    "shankhanil karagar": "শঙ্খনীল কারাগার",
    "rethink": "রি-থিংক",
    "re-think": "রি-থিংক",
    "al quran": "আল কোরআন",
    "quran sharif": "কোরআন শরীফ",
    "bukhari sharif": "বুখারী শরীফ",
    "seerat": "সীরাত",
    "seerat un nabi": "সীরাতুন নবী",
    "ar raheequl makhtum": "আর রাহীকুল মাখতূম",
    "raheequl makhtum": "আর রাহীকুল মাখতূম",
    "atomic habits": "পারমাণবিক অভ্যাস",
    "paromanobik ovvas": "পারমাণবিক অভ্যাস",
    "paromanik obbhas": "পারমাণবিক অভ্যাস",
    "debi": "দেবী",
    "devi": "দেবী",
    "nishithini": "নিশীথিনী",
    "nisithini": "নিশীথিনী",
    "misir ali": "মিসির আলি",
    "himu": "হিমু",
    "opekkha": "অপেক্ষা",
    "kichukkhon": "কিছুক্ষণ",
    "chander pahar": "চাঁদের পাহাড়",
    "feluda": "ফেলুদা",
    "byomkesh": "ব্যোমকেশ",
    "tin goyenda": "তিন গোয়েন্দা",
    "golpoguccho": "গল্পগুচ্ছ",
    "shesher kobita": "শেষের কবিতা",
    "gitanjali": "গীতাঞ্জলি",
    "agnibeena": "অগ্নিবীণা",
    "sanchita": "সঞ্চিতা",
    "rich dad poor dad": "রিচ ড্যাড পুওর ড্যাড",
    "habits": "অভ্যাস",
    "deep work": "ডিপ ওয়ার্ক",
    "psychology of money": "সাইকোলজি অব মানি",

    # Topics & Keywords
    "hotasha": "হতাশা",
    "depression": "হতাশা",
    "dushchinta": "দুশ্চিন্তা",
    "proshanti": "প্রশান্তি",
    "career": "ক্যারিয়ার",
    "business": "ব্যবসা",
    "uddokta": "উদ্যোক্তা",
    "upannas": "উপন্যাস",
    "novel": "উপন্যাস",
    "thriller": "থ্রিলার",
    "goenda": "গোয়েন্দা",
    "rohossho": "রহস্য",
    "islamic": "ইসলামিক",
    "islamic boi": "ইসলামি বই",
    "programming": "প্রোগ্রামিং",
    "python": "পাইথন",
    "history": "ইতিহাস",
    "science fiction": "সায়েন্স ফিকশন",
    "sci-fi": "সায়েন্স ফিকশন",
    "parenting": "প্যারেন্টিং",
    "biography": "জীবনী",
    "kobita": "কবিতা",
    "natok": "নাটক",

    # Conversational Words & Pronouns
    "amar": "আমার",
    "amader": "আমাদের",
    "mon kharap": "মন খারাপ",
    "mon": "মন",
    "kharap": "খারাপ",
    "kichu": "কিছু",
    "koro": "করো",
    "korun": "করুন",
    "pawa jabe": "পাওয়া যাবে",
    "pawa": "পাওয়া",
    "jabe": "যাবে",
    "kina": "কিনা",
    "lagbe": "লাগবে",
    "ache": "আছে",
    "boita": "বইটা",
    "boiti": "বইটি",
    "boi": "বই",
    "boigulo": "বইগুলো",
    "boi er": "বইয়ের",
    "boiyer": "বইয়ের",
    "katanor": "কাটানোর",
    "katate": "কাটাতে",
    "bhalo": "ভালো",
    "valo": "ভালো",
    "sera": "সেরা",
    "chai": "চাই",
    "dekhao": "দেখাও",
    "suggest": "সাজেস্ট",
    "sugest": "সাজেস্ট",
    "dam": "দাম",
    "dam koto": "দাম কত",
    "price": "দাম",
    "price koto": "দাম কত",
    "koto": "কত",
    "taka": "টাকা",
    "shekhar": "শেখার",
    "shekha": "শেখা",
    "jonno": "জন্য",
    "er": "এর",

    # More Bestselling Titles
    "recharge your iman": "রিচার্জ আপনার ঈমান",
    "recharge your down": "রিচার্জ আপনার ঈমান",
    "habluder jonno programming": "হাবলুদের জন্য প্রোগ্রামিং",
    "hablu": "হাবলু",
    "nondito noroke": "নন্দিত নরকে",
    "jochona o jononir golpo": "জোছনা ও জননীর গল্প",
    "aguner poroshmoni": "আগুনের পরশমণি",
    "ekattorer dinguli": "একাত্তরের দিনগুলি",
    "amar bondhu rashed": "আমার বন্ধু রাশেদ"
}

# Phonetic consonants and clusters
PHONETIC_CLUSTERS = [
    ("kkh", "ক্ষ"),
    ("kkhy", "ক্ষ্য"),
    ("ng", "ঙ"),
    ("shch", "শ্চ"),
    ("chh", "ছ"),
    ("ch", "চ"),
    ("kh", "খ"),
    ("gh", "ঘ"),
    ("th", "থ"),
    ("dh", "ধ"),
    ("ph", "ফ"),
    ("bh", "ভ"),
    ("jh", "ঝ"),
    ("sh", "শ"),
    ("shh", "ষ"),
    ("rh", "ঢ়"),
    ("rr", "ড়"),
    ("tt", "ট"),
    ("th", "থ"),
    ("k", "ক"),
    ("g", "গ"),
    ("t", "ত"),
    ("d", "দ"),
    ("n", "ন"),
    ("p", "প"),
    ("f", "ফ"),
    ("b", "ব"),
    ("v", "ভ"),
    ("m", "ম"),
    ("z", "য"),
    ("j", "জ"),
    ("r", "র"),
    ("l", "ল"),
    ("s", "স"),
    ("h", "হ"),
    ("y", "য়"),
    ("w", "ও")
]

# Vowels (initial vs kars)
INITIAL_VOWELS = {
    "aa": "আ", "a": "অ", "i": "ই", "ee": "ঈ", "u": "উ",
    "oo": "ঊ", "e": "এ", "o": "ও", "oi": "ঐ", "ou": "ঔ"
}

VOWEL_KARS = {
    "aa": "া", "a": "া", "i": "ি", "ee": "ী", "u": "ু",
    "oo": "ূ", "e": "ে", "o": "ো", "oi": "ৈ", "ou": "ৌ"
}


def is_banglish(text: str) -> bool:
    """Checks if text contains English/Latin characters."""
    return bool(re.search(r"[a-zA-Z]", text or ""))


def rule_based_transliterate(word: str) -> str:
    """Avro-inspired rule-based phonetic converter for single Banglish words."""
    w = word.lower().strip()
    if not w:
        return ""

    out = []
    i = 0
    n = len(w)

    while i < n:
        matched_cluster = None
        cluster_val = None

        # Try consonant cluster (up to 4 chars)
        for cl, bn in PHONETIC_CLUSTERS:
            if w.startswith(cl, i):
                matched_cluster = cl
                cluster_val = bn
                break

        if matched_cluster:
            out.append(cluster_val)
            i += len(matched_cluster)

            # Check next vowel
            vowel_kar = None
            for vk in ["aa", "ee", "oo", "oi", "ou", "a", "i", "u", "e", "o"]:
                if w.startswith(vk, i):
                    vowel_kar = VOWEL_KARS[vk]
                    i += len(vk)
                    break
            if vowel_kar:
                if vowel_kar != "া" or not out or out[-1] != "া":
                    out.append(vowel_kar)
            continue

        # Check initial vowel or standalone vowel
        vowel_match = None
        for vk in ["aa", "ee", "oo", "oi", "ou", "a", "i", "u", "e", "o"]:
            if w.startswith(vk, i):
                vowel_match = INITIAL_VOWELS[vk]
                i += len(vk)
                break

        if vowel_match:
            out.append(vowel_match)
            continue

        # Single char fallback
        ch = w[i]
        out.append(ch)
        i += 1

    return "".join(out)


def transliterate_banglish(text: str) -> str:
    """
    Translates Banglish phrase into Bengali.
    First checks dictionary for high-accuracy whole-phrase matches.
    If partial or unknown, transliterates words phonetically.
    """
    if not text or not is_banglish(text):
        return text

    clean = text.strip().lower()
    clean = re.sub(r"\s+", " ", clean)

    # 1. Exact phrase dictionary lookup
    if clean in BANGLISH_DICTIONARY:
        return BANGLISH_DICTIONARY[clean]

    # 2. Check multi-word phrase segments
    for phrase, bn in BANGLISH_DICTIONARY.items():
        if phrase in clean:
            clean = clean.replace(phrase, bn)

    # If already fully in Bengali
    if not is_banglish(clean):
        return clean

    # 3. Word by word transliteration
    words = clean.split()
    converted_words = []
    for w in words:
        if not is_banglish(w):
            converted_words.append(w)
            continue

        # Check word in dictionary
        if w in BANGLISH_DICTIONARY:
            converted_words.append(BANGLISH_DICTIONARY[w])
        else:
            converted_words.append(rule_based_transliterate(w))

    return " ".join(converted_words)


if __name__ == "__main__":
    test_cases = [
        "shonkhonil karagar",
        "paradoxical sajid",
        "humayun ahmed er upannas",
        "bela furabar age",
        "hotasha katanor boi",
        "arif azad",
        "career boi",
        "atomic habits"
    ]
    for tc in test_cases:
        res = transliterate_banglish(tc)
        print(f"Banglish: '{tc}' -> Bangla: '{res}'")
