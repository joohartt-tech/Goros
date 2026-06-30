import asyncio
import json
import os
import re
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, time as dtime

import cloudscraper
import requests
import pytz
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ──────────────────────────────────────────────────────────────────
#  DUMMY WEB SERVER (keeps Render free-tier Web Service alive)
# ──────────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# ──────────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────────
BOT_TOKEN = "8517153660:AAExRG-RKm2SeeZ7xF7JTp8dBWwc0jOYh4U"
SOLD_HISTORY_FILE = "sold_history.json"
WATCHLIST_FILE = "watchlist.json"
RINKAN_URL = "https://www.rinkan-goros.com/"
DELTAONE_URL = "https://www.deltaone.jp/collections/%E5%85%A8%E5%95%86%E5%93%81?sort_by=created-descending"

RINKAN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.rinkan-goros.com/",
}

CURRENCY_COUNTRY = {
    "SGD": "Singapore",       "JPY": "Japan",          "CNY": "China",
    "MYR": "Malaysia",        "USD": "United States",  "EUR": "Eurozone",
    "GBP": "United Kingdom",  "AUD": "Australia",      "NZD": "New Zealand",
    "HKD": "Hong Kong",       "KRW": "South Korea",    "THB": "Thailand",
    "IDR": "Indonesia",       "PHP": "Philippines",    "INR": "India",
    "CAD": "Canada",          "CHF": "Switzerland",
}

CURRENCY_FLAG = {
    "SGD": "🇸🇬", "JPY": "🇯🇵", "CNY": "🇨🇳", "MYR": "🇲🇾",
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "AUD": "🇦🇺",
    "NZD": "🇳🇿", "HKD": "🇭🇰", "KRW": "🇰🇷", "THB": "🇹🇭",
    "IDR": "🇮🇩", "PHP": "🇵🇭", "INR": "🇮🇳", "CAD": "🇨🇦",
    "CHF": "🇨🇭",
}

CATEGORY_KEYWORDS = {
    "feather":      ["feather", "Feather", "フェザー"],
    "largefeather": ["extra large feather", "Extra large feather", "Extra-large feather", "特大フェザー"],
    "wheel":        ["wheel", "Wheel", "ホイール"],
    "hook":         ["hook", "Hook", "フック"],
    "sunmetal":     ["sun metal", "Sun metal", "Sun Metal", "太陽メタル"],
    "eagle":        ["eagle", "Eagle", "イーグル"],
    "ring":         ["ring", "Ring", "リング"],
    "brace":        ["bracelet", "Bracelet", "brace", "Brace", "ブレス"],
    "chain":        ["chain", "Chain", "チェーン"],
    "metal":        ["metal", "Metal", "メタル"],
    "cross":        ["cross", "Cross", "クロス"],
    "belt":         ["belt", "Belt", "ベルト"],
    "concho":       ["concho", "Concho", "コンチョ"],
    "gold":         ["gold", "Gold", "ゴールド", "金"],
}

ECO_CATEGORY_URLS = {
    "wheel":        "https://www.eaglecapitalone.com/購入/ホイール/",
    "feather":      "https://www.eaglecapitalone.com/購入/新品特大フェザー/",
    "heartfeather": "https://www.eaglecapitalone.com/購入/ハートホイールフェザー/",
    "plainfeather": "https://www.eaglecapitalone.com/その他フェザー/",
    "usedfeather":  "https://www.eaglecapitalone.com/ショップ/",
    "hook":         "https://www.eaglecapitalone.com/チェーン-ホイール通販一覧/",
    "eagle":        "https://www.eaglecapitalone.com/イーグル通販一覧/",
    "metal":        "https://www.eaglecapitalone.com/メタル通販一覧/",
    "brace":        "https://www.eaglecapitalone.com/ブレス通販一覧/",
    "ring":         "https://www.eaglecapitalone.com/リング通販一覧/",
    "concho":       "https://www.eaglecapitalone.com/コンチョ-ビーズ-ピアス通販一覧/",
    "cross":        "https://www.eaglecapitalone.com/他トップ通販一覧/",
    "belt":         "https://www.eaglecapitalone.com/ベルト-財布-カバン-革製品通販一覧/",
    "spoon":        "https://www.eaglecapitalone.com/購入/スプーン/",
}

RINKAN_CATEGORY_URLS = {
    "feather":      "https://www.rinkan-goros.com/category/110300",
    "largefeather": "https://www.rinkan-goros.com/category/110200",
    "newfeather":   "https://www.rinkan-goros.com/category/1103002",
    "usedfeather":  "https://www.rinkan-goros.com/category/1102001",
    "ring":         "https://www.rinkan-goros.com/category/220500",
    "necklace":     "https://www.rinkan-goros.com/category/220200",
    "bracelet":     "https://www.rinkan-goros.com/category/220300",
    "leatherbrace": "https://www.rinkan-goros.com/category/220400",
    "pendanttop":   "https://www.rinkan-goros.com/category/220100",
    "belt":         "https://www.rinkan-goros.com/category/220600",
    "concho":       "https://www.rinkan-goros.com/category/110700",
    "wallet":       "https://www.rinkan-goros.com/category/220900",
    "bag":          "https://www.rinkan-goros.com/category/220900",
    "metal":        "https://www.rinkan-goros.com/category/110600",
}

DELTAONE_CATEGORY_URLS = {
    "largefeather":  "https://www.deltaone.jp/collections/all/%E3%83%95%E3%82%A7%E3%82%B6%E3%83%BC%EF%BC%88XL%EF%BC%89?sort_by=created-descending",
    "feather":       "https://www.deltaone.jp/collections/all/%E3%83%95%E3%82%A7%E3%82%B6%E3%83%BC%EF%BC%88S%2FM%2FL%EF%BC%89?sort_by=created-descending",
    "eagle":         "https://www.deltaone.jp/collections/all/%E3%82%A4%E3%83%BC%E3%82%B0%E3%83%AB?sort_by=created-descending",
    "bracelet":      "https://www.deltaone.jp/collections/all/%E3%83%96%E3%83%AC%E3%82%B9%EF%BC%88%E5%B9%B3%E6%89%93%EF%BC%89?sort_by=created-descending",
    "facebracelet":  "https://www.deltaone.jp/collections/all/%E3%83%96%E3%83%AC%E3%82%B9%EF%BC%88%E9%A1%94%EF%BC%89?sort_by=created-descending",
    "leatherbrace":  "https://www.deltaone.jp/collections/all/%E3%83%96%E3%83%AC%E3%82%B9%EF%BC%88%E9%9D%A9%EF%BC%89?sort_by=created-descending",
    "chain":         "https://www.deltaone.jp/collections/all/%E3%83%81%E3%82%A7%E3%83%BC%E3%83%B3%2F%E7%B4%90%EF%BC%88%E3%83%81%E3%82%A7%E3%83%BC%E3%83%B3%EF%BC%89?sort_by=created-descending",
    "wheel":         "https://www.deltaone.jp/collections/all/%E3%83%81%E3%82%A7%E3%83%BC%E3%83%B3%2F%E7%B4%90%EF%BC%88%E3%83%9B%E3%82%A4%E3%83%BC%E3%83%AB%EF%BC%89?sort_by=created-descending",
    "leathercord":   "https://www.deltaone.jp/collections/all/%E3%83%81%E3%82%A7%E3%83%BC%E3%83%B3%2F%E7%B4%90%EF%BC%88%E9%9D%A9%E7%B4%90%EF%BC%89?sort_by=created-descending",
    "metal":         "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%83%A1%E3%82%BF%E3%83%AB%EF%BC%89?sort_by=created-descending",
    "sunmetal":      "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E5%A4%AA%E9%99%BD%E3%83%A1%E3%82%BF%E3%83%AB%EF%BC%89?sort_by=created-descending",
    "cross":         "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%82%AF%E3%83%AD%E3%82%B9%EF%BC%89?sort_by=created-descending",
    "spoon":         "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%82%B9%E3%83%97%E3%83%BC%E3%83%B3%EF%BC%89?sort_by=created-descending",
    "topeagle":      "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%82%A4%E3%83%BC%E3%82%B0%E3%83%AB%EF%BC%89?sort_by=created-descending",
    "concho":        "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%82%B3%E3%83%B3%E3%83%81%E3%83%A7%EF%BC%89?sort_by=created-descending",
    "heart":         "https://www.deltaone.jp/collections/all/%E3%83%88%E3%83%83%E3%83%97%EF%BC%88%E3%83%8F%E3%83%BC%E3%83%88%EF%BC%89?sort_by=created-descending",
    "ring":          "https://www.deltaone.jp/collections/all/%E3%83%AA%E3%83%B3%E3%82%B0%EF%BC%88%E5%B9%B3%E6%89%93%EF%BC%89?sort_by=created-descending",
    "ringfeather":   "https://www.deltaone.jp/collections/all/%E3%83%AA%E3%83%B3%E3%82%B0%EF%BC%88%E3%83%95%E3%82%A7%E3%82%B6%E3%83%BC%EF%BC%89?sort_by=created-descending",
    "ringeagle":     "https://www.deltaone.jp/collections/all/%E3%83%AA%E3%83%B3%E3%82%B0%EF%BC%88%E3%82%A4%E3%83%BC%E3%82%B0%E3%83%AB%EF%BC%89?sort_by=created-descending",
    "belt":          "https://www.deltaone.jp/collections/all/%E3%83%AC%E3%82%B6%E3%83%BC%EF%BC%88%E3%83%99%E3%83%AB%E3%83%88%EF%BC%89?sort_by=created-descending",
    "bag":           "https://www.deltaone.jp/collections/all/%E3%83%AC%E3%82%B6%E3%83%BC%EF%BC%88%E3%83%90%E3%83%83%E3%82%B0%EF%BC%89?sort_by=created-descending",
    "wallet":        "https://www.deltaone.jp/collections/all/%E3%83%AC%E3%82%B6%E3%83%BC%EF%BC%88%E8%B2%A1%E5%B8%83%EF%BC%89?sort_by=created-descending",
    "beads":         "https://www.deltaone.jp/collections/all/%E3%81%9D%E3%81%AE%E4%BB%96%EF%BC%88%E3%83%93%E3%83%BC%E3%82%BA%EF%BC%89?sort_by=created-descending",
    "earring":       "https://www.deltaone.jp/collections/all/%E3%81%9D%E3%81%AE%E4%BB%96%EF%BC%88%E3%83%94%E3%82%A2%E3%82%B9%EF%BC%89?sort_by=created-descending",
    "old":           "https://www.deltaone.jp/collections/all/OLD?sort_by=created-descending",
    "rare":          "https://www.deltaone.jp/collections/all/%E5%B8%8C%E5%B0%91?sort_by=created-descending",
    "veryrare":      "https://www.deltaone.jp/collections/all/%E8%B6%85%E5%B8%8C%E5%B0%91?sort_by=created-descending",
    "custom":        "https://www.deltaone.jp/collections/all/%E7%89%B9%E6%B3%A8?sort_by=created-descending",
    "current":       "https://www.deltaone.jp/collections/all/%E7%8F%BE%E8%A1%8C?sort_by=created-descending",
    "sale":          "https://www.deltaone.jp/collections/all/SALE?sort_by=created-descending",
}

# NOTE on persistence: SOLD_HISTORY_FILE / WATCHLIST_FILE live on Render's
# local disk and are WIPED on every redeploy.

# ──────────────────────────────────────────────────────────────────
#  GLOBAL STATE / CACHE / CONCURRENCY LIMITS
# ──────────────────────────────────────────────────────────────────
price_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600

new_arrivals_cache = {"eco": {"data": None, "date": None, "timestamp": 0},
                       "rinkan": {"data": None, "timestamp": 0}}
NEW_ARRIVALS_CACHE_DURATION = 600  # 10 minutes

translation_cache = {}
last_known_update = {"date": ""}
paused_chats = set()

ECO_SEMAPHORE = None
RINKAN_SEMAPHORE = None
DELTA_SEMAPHORE = None

def init_semaphores():
    """Must be called inside the running event loop (in main())."""
    global ECO_SEMAPHORE, RINKAN_SEMAPHORE, DELTA_SEMAPHORE
    ECO_SEMAPHORE = asyncio.Semaphore(4)
    RINKAN_SEMAPHORE = asyncio.Semaphore(3)
    DELTA_SEMAPHORE = asyncio.Semaphore(5)


# ════════════════════════════════════════════════════════════════
#  PAUSE / RESUME
# ════════════════════════════════════════════════════════════════
def is_paused(chat_id):
    return chat_id in paused_chats

async def check_not_paused(update: Update) -> bool:
    chat_id = update.effective_chat.id
    if is_paused(chat_id):
        await update.message.reply_text("⏸️ Bot is paused. Type /resume to continue.")
        return False
    return True

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    paused_chats.add(update.effective_chat.id)
    await update.message.reply_text(
        "⏸️ Search commands paused for this chat.\nType /resume to enable them again."
    )

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    paused_chats.discard(update.effective_chat.id)
    await update.message.reply_text("▶️ Search commands resumed.")


# ════════════════════════════════════════════════════════════════
#  SOLD HISTORY
# ════════════════════════════════════════════════════════════════
def load_sold_history():
    if os.path.exists(SOLD_HISTORY_FILE):
        try:
            with open(SOLD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_sold_history(history):
    with open(SOLD_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def record_sold_price(name_en, name_jp, price, sold_date):
    history = load_sold_history()
    key = name_en[:40].lower().strip()
    history.setdefault(key, [])
    sold_date_only = sold_date[:10]
    for existing in history[key]:
        if existing["sold_date"][:10] == sold_date_only and existing["price"] == price:
            return
    history[key].insert(0, {"name_en": name_en, "name_jp": name_jp, "price": price, "sold_date": sold_date})
    history[key] = history[key][:5]
    save_sold_history(history)
    print(f"Recorded sold: {name_en} @ {price} on {sold_date}")

def get_sold_history_list(name_en):
    history = load_sold_history()
    return history.get(name_en[:40].lower().strip(), [])


# ════════════════════════════════════════════════════════════════
#  WATCHLIST
# ════════════════════════════════════════════════════════════════
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_watchlist(wl):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

def add_watch(chat_id, keyword, max_price):
    wl = load_watchlist()
    key = str(chat_id)
    wl.setdefault(key, [])
    wl[key] = [w for w in wl[key] if w["keyword"].lower() != keyword.lower()]
    wl[key].append({"keyword": keyword, "max_price": max_price})
    save_watchlist(wl)

def remove_watch(chat_id, keyword):
    wl = load_watchlist()
    key = str(chat_id)
    if key not in wl:
        return False
    before = len(wl[key])
    wl[key] = [w for w in wl[key] if w["keyword"].lower() != keyword.lower()]
    save_watchlist(wl)
    return len(wl[key]) < before

def get_watches(chat_id):
    wl = load_watchlist()
    return wl.get(str(chat_id), [])

def item_matches_watch(item, watch):
    name_combined = (item.get("name_en", "") + " " + item.get("name_jp", "")).lower()
    if watch["keyword"].lower() not in name_combined:
        return False
    if watch.get("max_price"):
        price_num = parse_price_number(item.get("price", ""))
        if price_num is None or price_num > watch["max_price"]:
            return False
    return True


# ════════════════════════════════════════════════════════════════
#  PRICE HELPERS
# ════════════════════════════════════════════════════════════════
def parse_price_number(price_str):
    try:
        return float(price_str.replace("￥", "").replace("¥", "").replace(",", "").replace("円", "").strip())
    except Exception:
        return None

def format_price(price_str, sgd_rate):
    numeric = parse_price_number(price_str)
    if numeric is None:
        return price_str
    if sgd_rate:
        return f"💴 {price_str} ≈ 💵 SGD {numeric * sgd_rate:,.2f}"
    return price_str

def check_price_trend_vs_similar(current_price_str, similar_items, threshold_percent=15, always_show=False):
    current = parse_price_number(current_price_str)
    prices = [parse_price_number(s["price"]) for s in similar_items if parse_price_number(s["price"]) is not None]
    if current is None or not prices:
        return None
    avg = sum(prices) / len(prices)
    if avg == 0:
        return None
    pct = ((current - avg) / avg) * 100
    if not always_show and abs(pct) < threshold_percent:
        return None
    if pct > 0:
        return f"📈 Price UP {pct:.1f}% vs similar avg (¥{avg:,.0f})"
    if pct < 0:
        return f"📉 Price DOWN {abs(pct):.1f}% vs similar avg (¥{avg:,.0f})"
    return f"➡️ Price UNCHANGED vs similar avg (¥{avg:,.0f})"

def check_price_margin(current_price_str, similar_items, threshold_percent=10, always_show=False):
    current = parse_price_number(current_price_str)
    prices = [parse_price_number(s["price"]) for s in similar_items if parse_price_number(s["price"]) is not None]
    if current is None or not prices:
        return None
    avg = sum(prices) / len(prices)
    if avg == 0:
        return None
    pct = ((current - avg) / avg) * 100
    if not always_show and abs(pct) < threshold_percent:
        return None
    if pct > 0:
        return f"⚠️ Asking price {pct:.1f}% ABOVE market avg (¥{avg:,.0f})"
    if pct < 0:
        return f"💰 Asking price {abs(pct):.1f}% BELOW market avg (¥{avg:,.0f}) — good deal!"
    return f"➡️ Asking price matches market avg (¥{avg:,.0f})"


# ════════════════════════════════════════════════════════════════
#  GENERAL HELPERS
# ════════════════════════════════════════════════════════════════
def is_japanese(text):
    return any('\u3000' <= c <= '\u9fff' or '\u30a0' <= c <= '\u30ff' or '\u3040' <= c <= '\u309f' for c in text)

def translate_to_english(text):
    if text in translation_cache:
        return translation_cache[text]
    try:
        result = GoogleTranslator(source='ja', target='en').translate(text)
        translation_cache[text] = result
        return result
    except Exception:
        return text

def get_rates(base="SGD"):
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=10)
        r.raise_for_status()
        return r.json().get("rates", {})
    except Exception as e:
        print(f"Error fetching rates: {e}")
        return {}

def make_scraper():
    return cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})


# ════════════════════════════════════════════════════════════════
#  EAGLECAPITALONE — CATEGORY DETECTION + SCRAPERS
# ════════════════════════════════════════════════════════════════
def detect_category(name_en, name_jp):
    name_lower = name_en.lower() + " " + name_jp.lower()
    if "ヤジリ" in name_jp or "arrowhead" in name_lower: return None
    if "グラス" in name_jp or "glass" in name_lower: return None
    if "ウニトップ" in name_jp or "uni top" in name_lower: return None
    if "スプーン" in name_jp or "spoon" in name_lower: return "spoon"
    if "ハートホイールフェザー" in name_jp or "heart wheel feather" in name_lower: return "heartfeather"
    if "先金" in name_jp or "gold tip" in name_lower or "tip gold" in name_lower: return "feather"
    if "プレーンフェザー" in name_jp or "plain feather" in name_lower: return "plainfeather"
    if "中古" in name_jp and "フェザー" in name_jp: return "usedfeather"
    if "ホイール" in name_jp or "wheel" in name_lower: return "wheel"
    if "フェザー" in name_jp or "feather" in name_lower: return "feather"
    if "フックホイールチェーン" in name_jp or ("hook" in name_lower and "wheel" in name_lower): return "hook"
    if "フック" in name_jp or "hook" in name_lower or "チェーン" in name_jp or "chain" in name_lower: return "hook"
    if "イーグル" in name_jp or "eagle" in name_lower: return "eagle"
    if "メタル" in name_jp or "metal" in name_lower: return "metal"
    if "ブレス" in name_jp or "bracelet" in name_lower or "brace" in name_lower: return "brace"
    if "リング" in name_jp or "ring" in name_lower: return "ring"
    if "コンチョ" in name_jp or "concho" in name_lower: return "concho"
    if "クロス" in name_jp or "cross" in name_lower: return "cross"
    if "ベルト" in name_jp or "belt" in name_lower: return "belt"
    return None


def check_item_availability(scraper, product_url):
    try:
        product_url = product_url.replace("//app", "/app")
        response = scraper.get(product_url, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")
        lines = [l.strip() for l in soup.get_text().split("\n") if l.strip()]
        for line in lines:
            if "soldout" in line.lower() or "売り切れ" in line.lower():
                return "❌ Sold Out"
            if "在庫あり" in line or ("in stock" in line.lower() and "out" not in line.lower()):
                return "✅ In Stock"
        return "❓ Unknown"
    except Exception as e:
        print(f"Error checking availability: {e}")
        return "❓ Unknown"


def scrape_sold_from_category(category_key, keywords, min_matches=2, max_soldout=20):
    url = ECO_CATEGORY_URLS.get(category_key)
    if not url:
        return []
    try:
        scraper = make_scraper()
        response = scraper.get(url, timeout=20)
        if response.status_code != 200:
            return []
        html = response.text
        sold_items = []
        soldout_positions = [m.start() for m in re.finditer(r'soldout', html, re.IGNORECASE)]
        for pos in soldout_positions[-max_soldout:]:
            chunk = html[max(0, pos - 3000):pos]
            prices = re.findall(r'[￥¥][\d,]+', chunk)
            if not prices:
                continue
            price_str = prices[-1]
            strongs = re.findall(r'<strong>(.*?)</strong>', chunk, re.DOTALL)
            name_jp = ""
            for m in reversed(strongs):
                clean = re.sub(r'<.*?>', '', m).strip()
                if clean and '￥' not in clean and '¥' not in clean and len(clean) > 2:
                    name_jp = clean
                    break
            if not name_jp:
                continue
            ver_match = re.findall(r'version/(\d+)/', chunk)
            version = int(ver_match[-1]) if ver_match else 0
            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            combined = (name_en + " " + name_jp).lower()
            matches = sum(1 for kw in keywords if kw.lower() in combined)
            if matches >= min_matches and not any(s["name_jp"] == name_jp for s in sold_items):
                sold_items.append({"name_jp": name_jp, "name_en": name_en, "price": price_str, "version": version})
        sold_items.sort(key=lambda x: x["version"], reverse=True)
        return sold_items
    except Exception as e:
        print(f"Error scraping category: {e}")
        return []


def get_similar_sold_prices(name_en, name_jp, max_results=3):
    category_key = detect_category(name_en, name_jp)
    if not category_key:
        return []
    jp_base = re.sub(r'【.*?】', '', name_jp).strip()
    stop_words = {
        'the','and','for','with','on','at','in','of','a','an','current','latest','cast',
        'old','new','good','condition','product','excellent','very','rare','individual',
        'diameter','model','size','weight','right','left','no','super','hobo','mint',
        'almost','barely','thick'
    }
    en_base = re.sub(r'\[.*?\]', '', name_en).strip().lower()
    en_words = [w for w in en_base.split() if len(w) >= 2 and w not in stop_words]

    sold_items = []
    if "プレーンフェザー" in name_jp or "plain feather" in en_base:
        sold_items = scrape_sold_from_category(category_key, ["プレーンフェザー", "plain", "feather"], min_matches=2)
    elif "先金" in name_jp:
        sold_items = scrape_sold_from_category(category_key, ["先金特大フェザー"], min_matches=1)
        sold_items = [s for s in sold_items if "縄" not in s["name_jp"] and "ターコイズ" not in s["name_jp"] and "上金" not in s["name_jp"]]
    elif "ハートホイールフェザー" in name_jp:
        sold_items = scrape_sold_from_category(category_key, ["ハートホイールフェザー"], min_matches=1)
    elif category_key == "hook":
        sold_items = scrape_sold_from_category(category_key, ["イーグルフック", "ホイールチェーン", "太角", "フックホイール"], min_matches=1)
    else:
        kws = [jp_base] if jp_base else en_words
        sold_items = scrape_sold_from_category(category_key, kws, min_matches=1 if jp_base else 2)

    if not sold_items:
        fallback = {
            "wheel": ["ホイール", "wheel"], "feather": ["フェザー", "feather"],
            "heartfeather": ["フェザー", "feather"], "plainfeather": ["フェザー", "feather"],
            "usedfeather": ["フェザー", "feather"], "hook": ["フック", "ホイール", "hook", "wheel", "chain"],
            "eagle": ["イーグル", "eagle"], "metal": ["メタル", "metal"], "brace": ["ブレス", "bracelet"],
            "ring": ["リング", "ring"], "concho": ["コンチョ", "concho"], "cross": ["クロス", "cross"],
            "belt": ["ベルト", "belt"], "spoon": ["スプーン", "spoon"],
        }.get(category_key, en_words or [jp_base])
        sold_items = scrape_sold_from_category(category_key, fallback, min_matches=1)
        for s in sold_items:
            s["loose_match"] = True
    return sold_items[:max_results]


def get_goros_prices_grouped():
    if price_cache["data"] and (time.time() - price_cache["timestamp"]) < CACHE_DURATION:
        return price_cache["data"]
    url = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"
    try:
        scraper = make_scraper()
        scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        time.sleep(3)
        response = scraper.get(url, timeout=20)
        if response.status_code != 200:
            return price_cache["data"] or []
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Scraper error: {e}")
        return price_cache["data"] or []

    grouped, section, items = [], "General", []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "table"]):
        if el.name in ["h1", "h2", "h3", "h4"]:
            if items:
                grouped.append({"section": section, "items": items}); items = []
            section = translate_to_english(el.get_text(strip=True))
        elif el.name == "table":
            for row in el.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 2:
                    jp, pr = cols[0].get_text(strip=True), cols[1].get_text(strip=True)
                    items.append({"item_en": translate_to_english(jp), "item_jp": jp, "price": pr})
    if items:
        grouped.append({"section": section, "items": items})
    if grouped:
        price_cache["data"], price_cache["timestamp"] = grouped, time.time()
    return grouped


def get_new_arrivals(force_refresh=False):
    cache = new_arrivals_cache["eco"]
    if not force_refresh and cache["data"] is not None and (time.time() - cache["timestamp"]) < NEW_ARRIVALS_CACHE_DURATION:
        return cache["data"], cache["date"]
    try:
        scraper = make_scraper()
        response = scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        if response.status_code != 200:
            return cache["data"] or [], cache["date"] or ""
        soup = BeautifulSoup(response.text, "html.parser")

        update_date, section = "", None
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            text = h.get_text(strip=True)
            if "新着" in text and "入荷" not in text:
                update_date, section = translate_to_english(text), h
                break
        if not section:
            return [], ""

        names, prices, imgs, urls = [], [], [], []
        for sib in section.find_all_next():
            if sib.name in ["h1", "h2", "h3", "h4"] and "カテゴリ" in sib.get_text(strip=True):
                break
            if sib.name == "a" and sib.string and len(sib.string.strip()) > 1:
                href = sib.get("href", "")
                if href.startswith("//"): href = "https:" + href
                elif href.startswith("/"): href = "https://www.eaglecapitalone.com" + href
                names.append(sib.string.strip()); urls.append(href)
            if sib.name == "a":
                img = sib.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src.startswith("//"): src = "https:" + src
                    elif src.startswith("/"): src = "https://www.eaglecapitalone.com" + src
                    imgs.append(src)
            if sib.name == "strong" and sib.string:
                p = sib.string.strip()
                if "￥" in p or "¥" in p:
                    prices.append(p)

        items = []
        for idx in range(min(len(names), len(prices))):
            nj = names[idx]
            items.append({
                "name_jp": nj,
                "name_en": translate_to_english(nj) if is_japanese(nj) else nj,
                "price": prices[idx],
                "img_url": imgs[idx] if idx < len(imgs) else None,
                "product_url": urls[idx] if idx < len(urls) else None,
                "is_reserved": "専用販売" in nj,
            })

        new_arrivals_cache["eco"] = {"data": items, "date": update_date, "timestamp": time.time()}
        return items, update_date
    except Exception as e:
        print(f"New arrivals error: {e}")
        return cache["data"] or [], cache["date"] or ""


# ════════════════════════════════════════════════════════════════
#  RINKAN
# ════════════════════════════════════════════════════════════════
def get_rinkan_new_arrivals(force_refresh=False):
    cache = new_arrivals_cache["rinkan"]
    if not force_refresh and cache["data"] is not None and (time.time() - cache["timestamp"]) < NEW_ARRIVALS_CACHE_DURATION:
        return cache["data"]
    try:
        scraper = make_scraper()
        response = scraper.get(RINKAN_URL, headers=RINKAN_HEADERS, timeout=20)
        if response.status_code != 200:
            return cache["data"] or []
        response.encoding = "euc_jp"
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        all_links = soup.find_all("a", href=re.compile(r'/shopdetail/\d+/?$'))
        products = {}
        for link in all_links:
            href = link.get("href", "")
            if href not in products:
                products[href] = {"img_url": None, "name_jp": None}
            img_tag = link.find("img")
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = "https://www.rinkan-goros.com" + src
                if products[href]["img_url"] is None:
                    products[href]["img_url"] = src
            text = link.get_text(strip=True)
            if text and len(text) > 2:
                products[href]["name_jp"] = text

        items = []
        for href, data in products.items():
            if not data["name_jp"]:
                continue
            name_jp = data["name_jp"]
            link_pos = html.find(href)
            if link_pos == -1:
                continue
            chunk = html[link_pos:link_pos + 1500]
            price_match = re.search(r'([\d,]+)円', chunk)
            if not price_match:
                continue
            price_str = price_match.group(1) + "円"
            full_url = "https://www.rinkan-goros.com" + href
            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            items.append({
                "name_jp": name_jp, "name_en": name_en, "price": price_str,
                "img_url": data["img_url"], "product_url": full_url, "source": "Rinkan"
            })

        new_arrivals_cache["rinkan"] = {"data": items, "timestamp": time.time()}
        return items
    except Exception as e:
        print(f"Rinkan scrape error: {e}")
        return cache["data"] or []


def check_rinkan_availability(scraper, product_url, retries=2):
    for attempt in range(retries):
        try:
            response = scraper.get(product_url, headers=RINKAN_HEADERS, timeout=15)
            response.encoding = "euc_jp"
            html = response.text
            if len(html) < 5000:
                time.sleep(8)
                continue
            if re.search(r'class=["\']soldout["\']', html):
                return "❌ Sold Out"
            if "basketBtn" in html or "カートに入れる" in html or "すぐに購入する" in html:
                return "✅ In Stock"
            return "❓ Unknown"
        except Exception as e:
            print(f"Rinkan availability error: {e}")
            time.sleep(3)
    return "❓ Unknown"


def detect_rinkan_category(keyword):
    kw = keyword.lower()
    if "large feather" in kw or "特大フェザー" in keyword: return "largefeather"
    if "feather" in kw or "フェザー" in keyword: return "feather"
    if "ring" in kw or "リング" in keyword: return "ring"
    if "necklace" in kw or "ネックレス" in keyword: return "necklace"
    if "bracelet" in kw or "ブレス" in keyword: return "bracelet"
    if "belt" in kw or "ベルト" in keyword: return "belt"
    if "concho" in kw or "コンチョ" in keyword: return "concho"
    if "bag" in kw or "バッグ" in keyword: return "bag"
    if "wallet" in kw or "財布" in keyword: return "wallet"
    if "metal" in kw or "メタル" in keyword: return "metal"
    if "gold" in kw or "金" in keyword or "ゴールド" in keyword: return "largefeather"
    return None


def search_rinkan_category(category_url, keyword, max_items=10, exclude_jp=None):
    try:
        scraper = make_scraper()
        response = scraper.get(category_url, headers=RINKAN_HEADERS, timeout=20)
        if response.status_code != 200 or len(response.text) < 5000:
            return []
        response.encoding = "euc_jp"
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=re.compile(r'/shopdetail/\d+/'))

        products = {}
        for link in all_links:
            href = link.get("href", "")
            id_match = re.search(r'/shopdetail/(\d+)/', href)
            if not id_match:
                continue
            base_href = f"/shopdetail/{id_match.group(1)}/"
            if base_href not in products:
                products[base_href] = {"img_url": None, "name_jp": None}
            img_tag = link.find("img")
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = "https://www.rinkan-goros.com" + src
                if products[base_href]["img_url"] is None:
                    products[base_href]["img_url"] = src
            text = link.get_text(strip=True)
            if text and len(text) > 2:
                products[base_href]["name_jp"] = text

        keyword_jp_map = {
            "gold": ["金", "ゴールド", "上金", "先金"], "silver": ["銀", "シルバー", "SV"],
            "turquoise": ["ターコイズ"], "feather": ["フェザー"], "old": ["オールド", "OLD"],
            "new": ["新品"], "plain": ["プレーン"], "rare": ["希少", "レア"],
            "bag": ["バッグ"], "concho": ["コンチョ"],
        }
        jp_keywords = keyword_jp_map.get(keyword.lower(), [])
        exclude_jp = exclude_jp or []

        items = []
        for base_href, data in products.items():
            if not data["name_jp"]:
                continue
            name_jp = data["name_jp"]
            if any(ex in name_jp for ex in exclude_jp):
                continue
            jp_match = any(jk in name_jp for jk in jp_keywords) if jp_keywords else False
            name_en_check = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            en_match = keyword.lower() in name_en_check.lower() or keyword.lower() in name_jp.lower()
            if not (jp_match or en_match):
                continue
            link_pos = html.find(base_href)
            if link_pos == -1:
                continue
            chunk = html[link_pos:link_pos + 1500]
            price_match = re.search(r'([\d,]+)円', chunk)
            if not price_match:
                continue
            price_str = price_match.group(1) + "円"
            full_url = "https://www.rinkan-goros.com" + base_href
            items.append({
                "name_jp": name_jp, "name_en": name_en_check, "price": price_str,
                "img_url": data["img_url"], "product_url": full_url, "source": "Rinkan"
            })
        return items[:max_items]
    except Exception as e:
        print(f"Rinkan category search error: {e}")
        return []


# ════════════════════════════════════════════════════════════════
#  DELTAONE
# ════════════════════════════════════════════════════════════════
def get_deltaone_new_arrivals(max_items=15):
    try:
        scraper = make_scraper()
        response = scraper.get(DELTAONE_URL, timeout=20)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        product_links = soup.find_all("a", href=re.compile(r'/collections/.+/products/'))

        items, seen_urls = [], set()
        for link in product_links:
            href = link.get("href", "")
            full_url = href if href.startswith("http") else "https://www.deltaone.jp" + href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            raw_text = link.get_text(strip=True)
            if not raw_text or len(raw_text) < 3:
                continue

            price_match = re.search(r'¥[\d,]+', raw_text)
            price_str = price_match.group() if price_match else None
            if not price_str:
                continue

            clean_name = re.sub(r'¥[\d,]+', '', raw_text).strip()
            clean_name = re.sub(r'^Quick view\s*', '', clean_name).strip()
            clean_name = re.sub(r'^NEW\s*', '', clean_name).strip()

            img_tag = link.find("img")
            img_url = None
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                if src.startswith("//"): img_url = "https:" + src
                elif src.startswith("/"): img_url = "https://www.deltaone.jp" + src
                else: img_url = src

            parent = link.find_parent()
            is_sold_out = False
            if parent:
                parent_text = parent.get_text()
                if "Sold Out" in parent_text or "売り切れ" in parent_text:
                    is_sold_out = True

            name_en = translate_to_english(clean_name) if is_japanese(clean_name) else clean_name

            items.append({
                "name_jp": clean_name, "name_en": name_en, "price": price_str,
                "img_url": img_url, "product_url": full_url,
                "sold_out": is_sold_out, "source": "DELTAone"
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"DELTAone scrape error: {e}")
        return []


def detect_deltaone_category(keyword):
    kw = keyword.lower()
    if "large feather" in kw or "特大フェザー" in keyword or "フェザーxl" in keyword.replace(" ", "").lower():
        return "largefeather"
    if "feather" in kw or "フェザー" in keyword: return "feather"
    if "eagle ring" in kw or "リングイーグル" in keyword.replace(" ", ""): return "ringeagle"
    if "feather ring" in kw or "リングフェザー" in keyword.replace(" ", ""): return "ringfeather"
    if "eagle" in kw or "イーグル" in keyword: return "eagle"
    if "leather brace" in kw or "ブレス革" in keyword.replace(" ", ""): return "leatherbrace"
    if "face bracelet" in kw or "ブレス顔" in keyword.replace(" ", ""): return "facebracelet"
    if "bracelet" in kw or "ブレス" in keyword: return "bracelet"
    if "wheel" in kw or "ホイール" in keyword: return "wheel"
    if "leather cord" in kw or "革紐" in keyword: return "leathercord"
    if "chain" in kw or "チェーン" in keyword: return "chain"
    if "sun metal" in kw or "太陽メタル" in keyword: return "sunmetal"
    if "metal" in kw or "メタル" in keyword: return "metal"
    if "cross" in kw or "クロス" in keyword: return "cross"
    if "spoon" in kw or "スプーン" in keyword: return "spoon"
    if "heart" in kw or "ハート" in keyword: return "heart"
    if "concho" in kw or "コンチョ" in keyword: return "concho"
    if "ring" in kw or "リング" in keyword: return "ring"
    if "bag" in kw or "バッグ" in keyword: return "bag"
    if "wallet" in kw or "財布" in keyword: return "wallet"
    if "belt" in kw or "ベルト" in keyword: return "belt"
    if "beads" in kw or "ビーズ" in keyword: return "beads"
    if "earring" in kw or "ピアス" in keyword: return "earring"
    if "old" in kw: return "old"
    if "very rare" in kw or "超希少" in keyword: return "veryrare"
    if "rare" in kw or "希少" in keyword: return "rare"
    if "custom" in kw or "特注" in keyword: return "custom"
    if "current" in kw or "現行" in keyword: return "current"
    if "sale" in kw or "セール" in keyword: return "sale"
    return None


def search_deltaone_category(category_url, max_items=10):
    try:
        scraper = make_scraper()
        response = scraper.get(category_url, timeout=20)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        product_links = soup.find_all("a", href=re.compile(r'/collections/.+/products/'))

        items, seen_urls = [], set()
        for link in product_links:
            href = link.get("href", "")
            full_url = href if href.startswith("http") else "https://www.deltaone.jp" + href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            raw_text = link.get_text(strip=True)
            if not raw_text or len(raw_text) < 3:
                continue
            price_match = re.search(r'¥[\d,]+', raw_text)
            price_str = price_match.group() if price_match else None
            if not price_str:
                continue

            clean_name = re.sub(r'¥[\d,]+', '', raw_text).strip()
            clean_name = re.sub(r'^Quick view\s*', '', clean_name).strip()
            clean_name = re.sub(r'^NEW\s*', '', clean_name).strip()

            img_tag = link.find("img")
            img_url = None
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                if src.startswith("//"): img_url = "https:" + src
                elif src.startswith("/"): img_url = "https://www.deltaone.jp" + src
                else: img_url = src

            parent = link.find_parent()
            is_sold_out = False
            if parent:
                parent_text = parent.get_text()
                if "Sold Out" in parent_text or "売り切れ" in parent_text:
                    is_sold_out = True

            name_en = translate_to_english(clean_name) if is_japanese(clean_name) else clean_name
            items.append({
                "name_jp": clean_name, "name_en": name_en, "price": price_str,
                "img_url": img_url, "product_url": full_url,
                "sold_out": is_sold_out, "source": "DELTAone"
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"DELTAone category search error: {e}")
        return []


# ════════════════════════════════════════════════════════════════
#  CONCURRENT ITEM-CHECK HELPERS
# ════════════════════════════════════════════════════════════════
async def check_eco_item_async(scraper, item):
    async with ECO_SEMAPHORE:
        availability = await asyncio.to_thread(check_item_availability, scraper, item["product_url"])
        previous_history = get_sold_history_list(item["name_en"])
        site_sold = []
        if availability == "❌ Sold Out":
            record_sold_price(item["name_en"], item["name_jp"], item["price"], datetime.now().strftime("%Y-%m-%d %H:%M"))
        site_sold = await asyncio.to_thread(get_similar_sold_prices, item["name_en"], item["name_jp"])
        return {"item": item, "availability": availability, "previous_history": previous_history, "site_sold": site_sold}

async def check_rinkan_item_async(scraper, item):
    async with RINKAN_SEMAPHORE:
        availability = await asyncio.to_thread(check_rinkan_availability, scraper, item["product_url"])
        return {"item": item, "availability": availability}


# ════════════════════════════════════════════════════════════════
#  AUTO-CHECK NEW ARRIVALS (notify) + WATCHLIST
# ════════════════════════════════════════════════════════════════
async def auto_check_new_arrivals(context):
    try:
        items, update_date = get_new_arrivals(force_refresh=True)
        if not update_date:
            return
        if update_date != last_known_update["date"] and last_known_update["date"] != "":
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"🔔 New arrivals posted!\n📅 {update_date}\n\nType /neweco to see the latest items."
            )
            watches = get_watches(context.job.chat_id)
            for watch in watches:
                matched = [i for i in items if item_matches_watch(i, watch)]
                for m in matched[:3]:
                    rates = get_rates(base="JPY")
                    sgd_rate = rates.get("SGD")
                    price_line = format_price(m["price"], sgd_rate)
                    text = f"👁️ Watchlist match: '{watch['keyword']}'\n\n{m['name_en']}\n({m['name_jp']})\n{price_line}"
                    if m.get("product_url"):
                        text += f"\n🔗 {m['product_url']}"
                    try:
                        if m.get("img_url"):
                            await context.bot.send_photo(chat_id=context.job.chat_id, photo=m["img_url"], caption=text)
                        else:
                            await context.bot.send_message(chat_id=context.job.chat_id, text=text)
                    except Exception as e:
                        print(f"Watchlist alert failed: {e}")
        last_known_update["date"] = update_date
    except Exception as e:
        print(f"Auto-check error: {e}")


# ════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ════════════════════════════════════════════════════════════════
async def send_grouped_results(update, title, keywords=None, keyword=None):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔍 Searching... please wait")
    rates, grouped = get_rates(base="JPY"), get_goros_prices_grouped()
    sgd_rate = rates.get("SGD")
    found_any = False

    for section in grouped:
        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return
        if keywords:
            section_match = any(kw.lower() in section["section"].lower() for kw in keywords)
            items = section["items"] if section_match else [
                i for i in section["items"]
                if any(kw.lower() in i["item_en"].lower() or kw in i["item_jp"] for kw in keywords)
            ]
        elif keyword:
            section_match = keyword.lower() in section["section"].lower()
            items = section["items"] if section_match else [
                i for i in section["items"]
                if keyword.lower() in i["item_en"].lower() or keyword.lower() in i["item_jp"].lower()
            ]
        else:
            items = section["items"]
        if not items:
            continue
        found_any = True
        msg = f"📋 {section['section']}\n{'─'*30}\n"
        for i in items:
            msg += f"• {i['item_en']}\n  ({i['item_jp']})\n  {format_price(i['price'], sgd_rate)}\n\n"
        for chunk in range(0, len(msg), 4096):
            await update.message.reply_text(msg[chunk:chunk+4096])
    if not found_any:
        await update.message.reply_text(f"❌ No items found for '{title}'")


async def cmd_neweco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching eaglecapitalone new arrivals... please wait\n⚡ Checking items in parallel")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items, update_date = get_new_arrivals()
    if not items:
        await update.message.reply_text("❌ Could not fetch new arrivals. Try again later.")
        return
    await update.message.reply_text(f"🆕 {update_date}\n{'─'*30}")
    scraper = make_scraper()

    eligible = [i for i in items if not i.get("is_reserved") and i.get("product_url")]
    tasks = [check_eco_item_async(scraper, item) for item in eligible]
    results = await asyncio.gather(*tasks) if tasks else []
    results_by_url = {r["item"]["product_url"]: r for r in results}

    for idx, i in enumerate(items, 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue.")
            return

        price_line = format_price(i["price"], sgd_rate)
        if i.get("is_reserved"):
            availability = "🔒 Reserved/Exclusive Sale"
            previous_history, site_sold = [], []
            trend_alert = margin_alert = None
        else:
            r = results_by_url.get(i["product_url"])
            if not r:
                availability, previous_history, site_sold = "❓ Unknown", [], []
                trend_alert = margin_alert = None
            else:
                availability = r["availability"]
                previous_history = r["previous_history"]
                site_sold = r["site_sold"]
                trend_alert = margin_alert = None
                if availability == "❌ Sold Out" and site_sold:
                    trend_alert = check_price_trend_vs_similar(i["price"], site_sold, threshold_percent=15, always_show=True)
                elif availability == "✅ In Stock" and site_sold:
                    margin_alert = check_price_margin(i["price"], site_sold, threshold_percent=10, always_show=True)

        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}"
        if i.get("product_url"):
            caption += f"\n🔗 {i['product_url']}"
        if trend_alert: caption += f"\n\n{trend_alert}"
        if margin_alert: caption += f"\n\n{margin_alert}"
        if site_sold:
            is_loose = any(s.get("loose_match") for s in site_sold)
            label = "📊 Similar sold (loosely related, latest first):" if is_loose else "📊 Similar sold on site (latest first):"
            caption += f"\n\n{label}"
            for s in site_sold:
                caption += f"\n  • {s['name_en']}\n    {format_price(s['price'], sgd_rate)}"
        if availability == "❌ Sold Out" and previous_history:
            caption += "\n\n🕐 Previously recorded:"
            for r2 in previous_history[:3]:
                caption += f"\n  • {r2['price']} on {r2['sold_date']}"

        if i.get("img_url"):
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=i["img_url"], caption=caption)
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)


async def cmd_newrinkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching new items from Rinkan... please wait\n⚡ Checking items in parallel")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items = get_rinkan_new_arrivals()
    if not items:
        await update.message.reply_text("❌ Could not fetch items from Rinkan. The site may be blocking requests.")
        return
    await update.message.reply_text(f"🆕 Rinkan New Items\n{'─'*30}")
    scraper = make_scraper()

    limited_items = items[:15]
    tasks = [check_rinkan_item_async(scraper, item) for item in limited_items]
    results = await asyncio.gather(*tasks) if tasks else []
    results_by_url = {r["item"]["product_url"]: r["availability"] for r in results}

    for idx, i in enumerate(limited_items, 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(limited_items)}. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = results_by_url.get(i["product_url"], "❓ Unknown")
        caption = (
            f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n"
            f"🏪 Source: Rinkan\n🔗 {i['product_url']}"
        )
        if i.get("img_url"):
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=i["img_url"], caption=caption)
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)


async def cmd_newdelta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching new arrivals from DELTAone... please wait")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items = get_deltaone_new_arrivals(max_items=15)
    if not items:
        await update.message.reply_text("❌ Could not fetch items from DELTAone. Try again later.")
        return
    await update.message.reply_text(f"🆕 DELTAone Newest Items\n{'─'*30}")

    for idx, i in enumerate(items, 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = "❌ Sold Out" if i["sold_out"] else "✅ In Stock"
        caption = (
            f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n"
            f"🏪 Source: DELTAone\n🔗 {i['product_url']}"
        )
        if i.get("img_url"):
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=i["img_url"], caption=caption)
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)


async def cmd_rinkansearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("Usage: /rinkansearch <keyword>\nExample: /rinkansearch feather")
        return
    category_key = detect_rinkan_category(keyword)
    if not category_key:
        await update.message.reply_text(
            "❌ Couldn't detect category.\nTry: feather, ring, bracelet, necklace, belt, concho, wallet, bag, metal, gold"
        )
        return
    category_url = RINKAN_CATEGORY_URLS.get(category_key)
    await update.message.reply_text(f"🔍 Searching Rinkan for '{keyword}'... please wait")
    exclude_jp = ["上金", "ターコイズ", "メタル付"] if keyword.lower() == "gold" else []
    items = search_rinkan_category(category_url, keyword, max_items=10, exclude_jp=exclude_jp)
    if not items:
        await update.message.reply_text(f"❌ No items found for '{keyword}'")
        return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    await update.message.reply_text(f"🔍 Rinkan Results for '{keyword}' ({len(items)} found)\n{'─'*30}")
    scraper = make_scraper()

    tasks = [check_rinkan_item_async(scraper, item) for item in items]
    results = await asyncio.gather(*tasks) if tasks else []
    results_by_url = {r["item"]["product_url"]: r["availability"] for r in results}

    for idx, i in enumerate(items, 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = results_by_url.get(i["product_url"], "❓ Unknown")
        caption = (
            f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n"
            f"🏪 Source: Rinkan\n🔗 {i['product_url']}"
        )
        if i.get("img_url"):
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=i["img_url"], caption=caption)
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)


async def cmd_deltasearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text(
            "Usage: /deltasearch <keyword>\nExample: /deltasearch feather\n\n"
            "Categories: feather, largefeather, eagle, bracelet, wheel, chain, "
            "metal, sunmetal, cross, spoon, heart, concho, ring, belt, bag, "
            "wallet, beads, earring, old, rare, custom, current, sale"
        )
        return
    category_key = detect_deltaone_category(keyword)
    if not category_key:
        await update.message.reply_text(
            "❌ Couldn't detect category.\nTry: feather, eagle, bracelet, wheel, chain, metal, cross, spoon, heart, concho, ring, belt, bag, wallet, old, rare, custom"
        )
        return
    category_url = DELTAONE_CATEGORY_URLS.get(category_key)
    await update.message.reply_text(f"🔍 Searching DELTAone for '{keyword}'... please wait")
    items = search_deltaone_category(category_url, max_items=10)
    if not items:
        await update.message.reply_text(f"❌ No items found for '{keyword}'")
        return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    await update.message.reply_text(f"🔍 DELTAone Results for '{keyword}' ({len(items)} found)\n{'─'*30}")

    for idx, i in enumerate(items, 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = "❌ Sold Out" if i["sold_out"] else "✅ In Stock"
        caption = (
            f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n"
            f"🏪 Source: DELTAone\n🔗 {i['product_url']}"
        )
        if i.get("img_url"):
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=i["img_url"], caption=caption)
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)


async def cmd_soldhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    keyword = " ".join(context.args).strip()
    history = load_sold_history()
    if not history:
        await update.message.reply_text("📭 No sold history recorded yet.\nHistory builds up as items are checked via /neweco.")
        return
    results = {k: v for k, v in history.items() if keyword.lower() in k} if keyword else history
    if keyword and not results:
        await update.message.reply_text(f"❌ No sold history found for '{keyword}'")
        return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    msg = "🕐 Sold Price History\n" + "─"*30 + "\n\n"
    for key, records in list(results.items())[:20]:
        for r in records[:3]:
            msg += f"• {r['name_en']}\n  ({r['name_jp']})\n  {format_price(r['price'], sgd_rate)} — sold {r['sold_date']}\n\n"
    for x in range(0, len(msg), 4096):
        await update.message.reply_text(msg[x:x+4096])


async def cmd_soldonsite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    args = " ".join(context.args).strip()
    if not args:
        await update.message.reply_text(
            "Usage: /soldonsite <category> <keyword>\nExample: /soldonsite wheel sv\n"
            "Categories: wheel, feather, hook, eagle, metal, brace, ring, concho, cross, belt, spoon"
        )
        return
    parts = args.split()
    category_key, search_keywords = parts[0].lower(), parts[1:] or parts
    if category_key not in ECO_CATEGORY_URLS:
        await update.message.reply_text("❌ Category not found.")
        return
    await update.message.reply_text(f"🔍 Searching sold items for '{args}'... please wait")
    sold_items = scrape_sold_from_category(category_key, search_keywords)
    if not sold_items:
        await update.message.reply_text(f"❌ No sold items found for '{args}'")
        return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    msg = f"❌ Sold items matching '{args}':\n{'─'*30}\n\n"
    for i in sold_items:
        msg += f"• {i['name_en']}\n  ({i['name_jp']})\n  {format_price(i['price'], sgd_rate)}\n\n"
    for x in range(0, len(msg), 4096):
        await update.message.reply_text(msg[x:x+4096])


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /watch <keyword> [max_price]\nExample: /watch eagle 500000\n\n"
            "Note: requires /notify to be active to receive alerts."
        )
        return
    max_price = None
    if args[-1].replace(",", "").isdigit():
        max_price = float(args[-1].replace(",", ""))
        keyword = " ".join(args[:-1]).strip()
    else:
        keyword = " ".join(args).strip()
    if not keyword:
        await update.message.reply_text("❌ Please provide a keyword to watch.")
        return
    chat_id = update.effective_chat.id
    add_watch(chat_id, keyword, max_price)
    msg = f"👁️ Watching for: '{keyword}'"
    if max_price:
        msg += f" under ¥{max_price:,.0f}"
    msg += "\n\nMake sure /notify is enabled to get alerts."
    await update.message.reply_text(msg)

async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("Usage: /unwatch <keyword>")
        return
    chat_id = update.effective_chat.id
    removed = remove_watch(chat_id, keyword)
    await update.message.reply_text(f"🗑️ Removed watch for '{keyword}'." if removed else f"❌ No watch found for '{keyword}'.")

async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    watches = get_watches(chat_id)
    if not watches:
        await update.message.reply_text("📭 Your watchlist is empty.\nUse /watch <keyword> [max_price] to add one.")
        return
    msg = "👁️ Your Watchlist:\n" + "─"*30 + "\n\n"
    for w in watches:
        line = f"• {w['keyword']}"
        if w.get("max_price"):
            line += f" (under ¥{w['max_price']:,.0f})"
        msg += line + "\n"
    await update.message.reply_text(msg)


async def cmd_healthcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🩺 Running healthcheck on all sites... please wait")
    msg = "🩺 Healthcheck Report\n" + "─"*30 + "\n\n"
    try:
        scraper = make_scraper()
        r = scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        items, update_date = get_new_arrivals(force_refresh=True)
        msg += f"eaglecapitalone.com\n  Status: {r.status_code}\n  Items parsed: {len(items)}\n\n"
    except Exception as e:
        msg += f"eaglecapitalone.com\n  ❌ Error: {e}\n\n"
    try:
        rinkan_items = get_rinkan_new_arrivals(force_refresh=True)
        msg += f"rinkan-goros.com\n  Items parsed: {len(rinkan_items)}\n\n"
    except Exception as e:
        msg += f"rinkan-goros.com\n  ❌ Error: {e}\n\n"
    try:
        delta_items = get_deltaone_new_arrivals(max_items=15)
        msg += f"deltaone.jp\n  Items parsed: {len(delta_items)}\n\n"
    except Exception as e:
        msg += f"deltaone.jp\n  ❌ Error: {e}\n\n"

    if price_cache["data"]:
        age = int((time.time() - price_cache["timestamp"]) / 60)
        msg += f"💾 Price list cache: {len(price_cache['data'])} sections, {age} min old\n"
    history = load_sold_history()
    msg += f"📦 Sold history: {len(history)} items tracked\n"
    watches = load_watchlist()
    msg += f"👁️ Active watches (all chats): {sum(len(v) for v in watches.values())}\n"
    await update.message.reply_text(msg)


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    amount, from_currency, to_currency = 1.0, "SGD", "SGD"
    if args:
        try:
            amount = float(args[0])
            if len(args) >= 2: from_currency = args[1].upper()
            if len(args) >= 3: to_currency = args[2].upper()
        except ValueError:
            from_currency = args[0].upper()
            if len(args) >= 2: to_currency = args[1].upper()
    rates = get_rates(base=from_currency)
    if not rates:
        await update.message.reply_text(f"❌ Could not fetch rates for {from_currency}")
        return
    if to_currency not in rates:
        await update.message.reply_text(f"❌ Currency '{to_currency}' not supported.")
        return
    converted = amount * rates[to_currency]
    await update.message.reply_text(f"💱 {amount:.2f} {from_currency} ≈ {converted:.2f} {to_currency}\n⚠️ Approximate exchange rate")


async def list_currencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates = get_rates("SGD")
    if not rates:
        await update.message.reply_text("❌ Unable to fetch currency list.")
        return
    lines = [
        f"{CURRENCY_FLAG[c]} {c:<3} – {CURRENCY_COUNTRY[c]:<15} | 1 SGD = {rates[c]:>6.2f}"
        for c in sorted(rates) if c in CURRENCY_COUNTRY and c in CURRENCY_FLAG
    ]
    msg = "💱 Exchange Rates\n\n" + "\n".join(lines) + "\n\nUsage:\n/C 100 SGD JPY"
    await update.message.reply_text(msg)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("Usage: /price <item name>\nExample: /price eagle")
        return
    if is_japanese(keyword):
        translated = translate_to_english(keyword)
        await send_grouped_results(update, keyword, keywords=[keyword, translated])
    else:
        await send_grouped_results(update, keyword, keyword=keyword)


async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()
    sgt = pytz.timezone("Asia/Singapore")
    times = [dtime(h, m, tzinfo=sgt) for h, m in [(18,0),(18,30),(19,0),(19,30),(20,0)]]
    for t in times:
        context.job_queue.run_daily(auto_check_new_arrivals, time=t, chat_id=chat_id, name=f"{chat_id}_{t.hour}_{t.minute}")
    await update.message.reply_text(
        "✅ Notifications enabled!\n🕕 Checking at 6:00, 6:30, 7:00, 7:30, 8:00 PM SGT.\n"
        "👁️ Your /watchlist will also be checked.\nType /notifyoff to disable."
    )

async def cmd_notifyoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    removed = 0
    for h, m in [(18,0),(18,30),(19,0),(19,30),(20,0)]:
        for job in context.job_queue.get_jobs_by_name(f"{chat_id}_{h}_{m}"):
            job.schedule_removal(); removed += 1
    await update.message.reply_text("🔕 Notifications disabled." if removed else "⚠️ No active notifications to disable.")


def make_category_cmd(display_name, keywords_key):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_grouped_results(update, display_name, CATEGORY_KEYWORDS[keywords_key])
    return handler


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📋 Available Commands:\n\n"
        "💱 Currency:\n/C 100 SGD JPY — Convert currency\n/list — Show all exchange rates\n\n"
        "🆕 New Arrivals:\n"
        "/neweco — eaglecapitalone new arrivals\n"
        "/newrinkan — Rinkan new arrivals\n"
        "/newdelta — DELTAone newest items\n"
        "/rinkansearch <keyword> — Search Rinkan by category\n"
        "/deltasearch <keyword> — Search DELTAone by category\n\n"
        "👁️ Watchlist:\n"
        "/watch <keyword> [max_price] — Add a watch\n"
        "/unwatch <keyword> — Remove a watch\n"
        "/watchlist — View your active watches\n\n"
        "🔔 Notifications:\n/notify — Auto alert (+ watchlist)\n/notifyoff — Disable notifications\n\n"
        "⏸️ Control:\n/stop — Pause/stop a running search\n/resume — Resume search commands\n\n"
        "🕐 Sold History:\n/soldhistory — View sold price history\n/soldonsite wheel sv — Search sold items\n\n"
        "🪶 Goro's Price Search:\n/price <keyword> — Free search\n"
        "/feather /largefeather /wheel /hook /sunmetal /eagle /ring /brace /chain /metal /cross /belt /concho /gold\n\n"
        "🔧 Debug:\n/healthcheck — Status report on all 3 sites\n"
    )
    await update.message.reply_text(msg)


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
async def main():
    init_semaphores()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("C", convert))
    app.add_handler(CommandHandler("list", list_currencies))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("neweco", cmd_neweco))
    app.add_handler(CommandHandler("newrinkan", cmd_newrinkan))
    app.add_handler(CommandHandler("newdelta", cmd_newdelta))
    app.add_handler(CommandHandler("rinkansearch", cmd_rinkansearch))
    app.add_handler(CommandHandler("deltasearch", cmd_deltasearch))
    app.add_handler(CommandHandler("soldhistory", cmd_soldhistory))
    app.add_handler(CommandHandler("soldonsite", cmd_soldonsite))
    app.add_handler(CommandHandler("healthcheck", cmd_healthcheck))
    app.add_handler(CommandHandler("notify", cmd_notify))
    app.add_handler(CommandHandler("notifyoff", cmd_notifyoff))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))

    categories = [
        ("feather", "Feather"), ("largefeather", "Extra Large Feather"),
        ("wheel", "Wheel"), ("hook", "Hook"), ("sunmetal", "Sun Metal"),
        ("eagle", "Eagle"), ("ring", "Ring"), ("brace", "Bracelet"),
        ("chain", "Chain"), ("metal", "Metal"), ("cross", "Cross"),
        ("belt", "Belt"), ("concho", "Concho"), ("gold", "Gold"),
    ]
    for key, label in categories:
        app.add_handler(CommandHandler(key, make_category_cmd(label, key)))

    print("Bot started...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
