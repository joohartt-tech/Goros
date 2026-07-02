import asyncio
import json
import os
import re
import time
import threading
import urllib.request
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

def self_ping():
    """Ping own health endpoint every 5 minutes to prevent Render spin-down."""
    time.sleep(60)  # wait 1 min after startup before first ping
    url = os.environ.get("RENDER_EXTERNAL_URL", "https://goros.onrender.com")
    while True:
        try:
            urllib.request.urlopen(url, timeout=10)
            print("Self-ping OK")
        except Exception as e:
            print(f"Self-ping failed: {e}")
        time.sleep(300)  # ping every 5 minutes

threading.Thread(target=run_dummy_server, daemon=True).start()
threading.Thread(target=self_ping, daemon=True).start()

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
    "feather":      "https://www.eaglecapitalone.com/ショップ/",
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
    "concho":       "https://www.rinkan-goros.com/category/112200",
    "wallet":       "https://www.rinkan-goros.com/category/220900",
    "bag":          "https://www.rinkan-goros.com/category/220900",
    "metal":        "https://www.rinkan-goros.com/category/110600",
    "wheel":        "https://www.rinkan-goros.com/category/111100",
    "eagle":        "https://www.rinkan-goros.com/category/110100",
    "allgold":      "https://www.rinkan-goros.com/category/440000",
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

# ──────────────────────────────────────────────────────────────────
#  GLOBAL STATE / CACHE / CONCURRENCY LIMITS
# ──────────────────────────────────────────────────────────────────
price_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600

new_arrivals_cache = {"eco": {"data": None, "date": None, "timestamp": 0},
                       "rinkan": {"data": None, "timestamp": 0}}
NEW_ARRIVALS_CACHE_DURATION = 600

translation_cache = {}
last_known_update = {"date": ""}
last_eco_notify_day = {"date": ""}
last_known_rinkan_urls = set()
last_known_delta_urls = set()
paused_chats = set()
last_delta_search = {}  # chat_id -> keyword string

ECO_SEMAPHORE = None
RINKAN_SEMAPHORE = None
DELTA_SEMAPHORE = None

def init_semaphores():
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
    if is_paused(update.effective_chat.id):
        await update.message.reply_text("⏸️ Bot is paused. Type /resume to continue.")
        return False
    return True

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    paused_chats.add(update.effective_chat.id)
    await update.message.reply_text("⏸️ Search commands paused.\nType /resume to enable them again.")

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

def get_sold_history_list(name_en):
    return load_sold_history().get(name_en[:40].lower().strip(), [])


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
    return load_watchlist().get(str(chat_id), [])

def item_matches_watch(item, watch):
    combined = (item.get("name_en", "") + " " + item.get("name_jp", "")).lower()
    if watch["keyword"].lower() not in combined:
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
        return float(price_str.replace("￥","").replace("¥","").replace(",","").replace("円","").strip())
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
    if current is None or not prices: return None
    avg = sum(prices) / len(prices)
    if avg == 0: return None
    pct = ((current - avg) / avg) * 100
    if not always_show and abs(pct) < threshold_percent: return None
    if pct > 0: return f"📈 Price UP {pct:.1f}% vs similar avg (¥{avg:,.0f})"
    if pct < 0: return f"📉 Price DOWN {abs(pct):.1f}% vs similar avg (¥{avg:,.0f})"
    return f"➡️ Price UNCHANGED vs similar avg (¥{avg:,.0f})"

def check_price_margin(current_price_str, similar_items, threshold_percent=10, always_show=False):
    current = parse_price_number(current_price_str)
    prices = [parse_price_number(s["price"]) for s in similar_items if parse_price_number(s["price"]) is not None]
    if current is None or not prices: return None
    avg = sum(prices) / len(prices)
    if avg == 0: return None
    pct = ((current - avg) / avg) * 100
    if not always_show and abs(pct) < threshold_percent: return None
    if pct > 0: return f"⚠️ Asking price {pct:.1f}% ABOVE market avg (¥{avg:,.0f})"
    if pct < 0: return f"💰 Asking price {abs(pct):.1f}% BELOW market avg (¥{avg:,.0f}) — good deal!"
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

async def safe_send(context, chat_id, text=None, photo=None, caption=None):
    try:
        if photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)
        else:
            await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(f"Send failed: {e}")
        if photo and caption:
            try:
                await context.bot.send_message(chat_id=chat_id, text=caption)
            except Exception as e2:
                print(f"Fallback send also failed: {e2}")


# ════════════════════════════════════════════════════════════════
#  EAGLECAPITALONE
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

def extract_rinkan_tags(name_jp, name_en):
    """Extract grade, fitting-style, and facing-direction tags so comps only
    compare items that are actually the same category of product."""
    combined_en = name_en.lower()
    tags = set()

    # Condition / rarity tier
    if "新品" in name_jp or re.search(r'\[new\]|\bnew\b', combined_en):
        tags.add("new")
    if "希少" in name_jp or "レア" in name_jp or "rare" in combined_en:
        tags.add("rare")
    if ("オールド" in name_jp or "old" in combined_en) and "gold" not in combined_en:
        tags.add("old")
    if "中古" in name_jp or re.search(r'\bused\b', combined_en):
        tags.add("used")

    # Fitting/mounting style — the primary category split for feathers:
    # plain / turquoise rope / kamigane / kamigane+turquoise / tip
    has_turquoise = "ターコイズ" in name_jp or "turquoise" in combined_en
    has_rope = (
        "縄" in name_jp or "ロープ" in name_jp
        or "rope" in combined_en or "kanawa" in combined_en
    )
    has_kamigane = "上金" in name_jp or "上銀" in name_jp or "upper gold" in combined_en or "upper silver" in combined_en
    has_tip = "先金" in name_jp or "先銀" in name_jp or "tip gold" in combined_en or "tip silver" in combined_en
    has_plain = "プレーン" in name_jp or "plain" in combined_en

    if has_tip:
        tags.add("fit_tip")
    elif has_rope and has_turquoise:
        tags.add("fit_turquoise_rope")
    elif has_kamigane and has_turquoise:
        tags.add("fit_kamigane_turquoise")
    elif has_kamigane:
        tags.add("fit_kamigane")
    elif has_turquoise:
        tags.add("fit_turquoise_rope")
    elif has_plain:
        tags.add("fit_plain")

    # Facing direction
    if "左向き" in name_jp or "left-facing" in combined_en or "facing left" in combined_en:
        tags.add("face_left")
    elif "右向き" in name_jp or "right-facing" in combined_en or "facing right" in combined_en:
        tags.add("face_right")

    # Fitting metal material — kept for display only, not enforced as a hard match
    if "上銀" in name_jp or "upper silver" in combined_en:
        tags.add("upper_silver")
    if "上金" in name_jp or "upper gold" in combined_en:
        tags.add("upper_gold")

    return tags


GRADE_TAGS = {"new", "rare", "old", "used"}
FITTING_STYLE_TAGS = {"fit_plain", "fit_turquoise_rope", "fit_kamigane", "fit_kamigane_turquoise", "fit_tip"}
FACING_TAGS = {"face_left", "face_right"}

def tags_compatible(tags_a, tags_b):
    """Require matching grade, fitting style, and facing direction whenever
    either item declares that attribute (undeclared attributes don't block a match)."""
    for tag_group in (GRADE_TAGS, FITTING_STYLE_TAGS, FACING_TAGS):
        a, b = tags_a & tag_group, tags_b & tag_group
        if a and b and not (a & b):
            return False
    return True

def check_item_availability(scraper, product_url):
    """Checks a single product page's real availability via its
    itemprop="availability" schema.org meta tag (InStock/OutOfStock),
    rather than scanning the page's raw visible text for the words
    'soldout' or '在庫あり'. The product page template includes hidden
    UI elements (e.g. a restock-notification widget) that contain the
    literal word 'soldout' even when the item is actually in stock —
    a naive text scan hits that false positive before ever reaching
    the real stock status further down the page."""
    try:
        product_url = product_url.replace("//app", "/app")
        response = scraper.get(product_url, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")

        avail_tag = soup.find(itemprop="availability")
        if avail_tag and avail_tag.get("content"):
            content = avail_tag["content"]
            if content == "OutOfStock":
                return "❌ Sold Out"
            elif content == "InStock":
                return "✅ In Stock"

        # fallback to the old text scan only if no schema tag is found at all
        for line in [l.strip() for l in soup.get_text().split("\n") if l.strip()]:
            if "soldout" in line.lower() or "売り切れ" in line.lower(): return "❌ Sold Out"
            if "在庫あり" in line or ("in stock" in line.lower() and "out" not in line.lower()): return "✅ In Stock"
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

        main_imgs = [mm.group(1) for mm in re.finditer(r'src="([^"]+)"\s+itemprop="image"', html)]

        strongs = list(re.finditer(r'<strong>(.*?)</strong>', html, re.DOTALL))
        img_idx = 0
        for m in strongs:
            clean = re.sub(r'<.*?>', '', m.group(1)).strip()
            if not clean or '￥' in clean or '¥' in clean or len(clean) < 3:
                continue
            name_jp = clean

            chunk_after = html[m.end():m.end() + 2500]
            sold_out = bool(re.search(r'soldout|sold[\s_-]?out|売り切れ', chunk_after[:2000], re.IGNORECASE))
            if not sold_out:
                img_idx += 1
                continue

            price_match = re.search(r'[￥¥]([\d,]+)', chunk_after)
            if not price_match:
                img_idx += 1
                continue
            price_str = "￥" + price_match.group(1)

            ver_match = None
            if img_idx < len(main_imgs):
                ver_search = re.search(r'version/(\d+)/', main_imgs[img_idx])
                ver_match = int(ver_search.group(1)) if ver_search else 0
            version = ver_match or 0
            img_idx += 1

            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            combined = (name_en + " " + name_jp).lower()
            matches = sum(1 for kw in keywords if kw.lower() in combined)
            if matches >= min_matches and not any(s["name_jp"] == name_jp for s in sold_items):
                sold_items.append({"name_jp": name_jp, "name_en": name_en, "price": price_str, "version": version})

            if len(sold_items) >= max_soldout:
                break

        sold_items.sort(key=lambda x: x["version"], reverse=True)
        return sold_items
    except Exception as e:
        print(f"Error scraping category: {e}")
        return []

eco_category_cache = {}  # cache_key -> {"data": [...], "timestamp": 0}
ECO_CATEGORY_CACHE_DURATION = 600  # 10 minutes


def scrape_instock_from_category(category_key, max_items=30, include_sold=False, force_refresh=False):
    """Scrape items from an eaglecapitalone category page.
    Uses BeautifulSoup to find each product's actual DOM container
    (div[itemtype="http://schema.org/Product"]) and extracts
    name/price/image/url/availability only from within that specific
    subtree, guaranteeing correct pairing — no positional list matching.

    By default only returns in-stock items (unchanged behavior for
    existing callers like deal-checking). Pass include_sold=True to
    also include sold-out items, each tagged with its availability.

    Caches the full scraped+translated result per (category, include_sold)
    combo for ECO_CATEGORY_CACHE_DURATION seconds, since translation is
    the slow part of this call (one Google Translate request per product)
    and most category contents don't change minute-to-minute. Pass
    force_refresh=True to bypass the cache."""
    cache_key = f"{category_key}_{include_sold}"
    cached = eco_category_cache.get(cache_key)
    if not force_refresh and cached and (time.time() - cached["timestamp"]) < ECO_CATEGORY_CACHE_DURATION:
        return cached["data"][:max_items]

    url = ECO_CATEGORY_URLS.get(category_key)
    if not url:
        return []
    try:
        scraper = make_scraper()
        response = scraper.get(url, timeout=20)
        if response.status_code != 200:
            return cached["data"][:max_items] if cached else []
        soup = BeautifulSoup(response.text, "html.parser")
        product_divs = soup.find_all("div", itemtype="http://schema.org/Product")

        items = []
        for pdiv in product_divs:
            name_tag = pdiv.find("span", itemprop="name")
            if not name_tag:
                continue
            name_jp = name_tag.get_text(strip=True)
            if not name_jp:
                continue

            price_tag = pdiv.find(itemprop="price")
            if not price_tag or not price_tag.get("content"):
                continue
            try:
                price_str = "￥" + f"{int(price_tag['content']):,}"
            except ValueError:
                continue

            avail_tag = pdiv.find(itemprop="availability")
            is_sold_out = bool(avail_tag and avail_tag.get("content") == "OutOfStock")
            if is_sold_out and not include_sold:
                continue

            img_tag = pdiv.find("img", itemprop="image")
            img_url = None
            if img_tag and img_tag.get("src"):
                img_url = img_tag["src"]
                if img_url.startswith("//"): img_url = "https:" + img_url
                elif img_url.startswith("/"): img_url = "https://www.eaglecapitalone.com" + img_url

            purl_tag = pdiv.find("meta", itemprop="url")
            if purl_tag and purl_tag.get("content"):
                product_url = purl_tag["content"].replace("//app", "/app")
            else:
                product_url = url

            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp

            items.append({
                "name_jp":     name_jp,
                "name_en":     name_en,
                "price":       price_str,
                "img_url":     img_url,
                "product_url": product_url,
                "category":    category_key,
                "source":      "eaglecapitalone",
                "sold_out":    is_sold_out
            })

        eco_category_cache[cache_key] = {"data": items, "timestamp": time.time()}
        print(f"ECO {category_key}: found {len(items)} items (DOM-scoped extraction, include_sold={include_sold}, freshly scraped)")
        return items[:max_items]
    except Exception as e:
        print(f"ECO instock scrape error ({category_key}): {e}")
        return cached["data"][:max_items] if cached else []


async def check_eco_deal_item(item, sgd_rate):
    """Check if a single item is a good deal (10%+ below market avg)."""
    async with ECO_SEMAPHORE:
        try:
            site_sold = await asyncio.to_thread(
                get_similar_sold_prices, item["name_en"], item["name_jp"]
            )
            if not site_sold:
                return None

            margin = check_price_margin(
                item["price"], site_sold,
                threshold_percent=10, always_show=False
            )

            # Only return if it's a good deal (margin contains "BELOW")
            if margin and "BELOW" in margin:
                return {**item, "margin": margin, "site_sold": site_sold}
            return None
        except Exception as e:
            print(f"Deal check error for {item['name_jp']}: {e}")
            return None

DELTA_KEYWORD_JP_MAP = {
    "feather":       ["フェザー"],
    "large feather": ["特大フェザー", "フェザー（XL）"],
    "eagle":         ["イーグル"],
    "eagle ring":    ["リング", "イーグル"],
    "feather ring":  ["リング", "フェザー"],
    "bracelet":      ["ブレス"],
    "face bracelet": ["ブレス", "顔"],
    "leather brace": ["ブレス", "革"],
    "wheel":         ["ホイール"],
    "chain":         ["チェーン"],
    "leather cord":  ["革紐"],
    "metal":         ["メタル"],
    "sun metal":     ["太陽メタル", "太陽"],
    "sv sun":        ["SV太陽", "SVIN太陽"],
    "gold sun":      ["K18太陽"],
    "gold insun":    ["K18IN太陽"],
    "cross":         ["クロス"],
    "spoon":         ["スプーン"],
    "top eagle":     ["トップ", "イーグル"],
    "concho":        ["コンチョ"],
    "heart":         ["ハート"],
    "ring":          ["リング"],
    "belt":          ["ベルト"],
    "bag":           ["バッグ"],
    "wallet":        ["財布"],
    "beads":         ["ビーズ"],
    "earring":       ["ピアス"],
    "old":           ["OLD", "オールド"],
    "rare":          ["希少"],
    "very rare":     ["超希少"],
    "custom":        ["特注"],
    "current":       ["現行"],
    "sale":          ["SALE", "セール"],
}
# ── ECO keyword-scoped search & deal helpers ──
ECO_KEYWORD_JP_MAP = {
    "feather":       ["フェザー"],
    "large feather": ["特大フェザー"],
    "heart feather": ["ハートホイールフェザー"],
    "plain feather": ["プレーンフェザー", "プレーン"],
    "used feather":  ["中古"],
    "gold tip":      ["先金"],
    "gold top":      ["上金"],
    "wheel":         ["ホイール"],
    "hook":          ["フック"],
    "eagle":         ["イーグル"],
    "metal":         ["メタル"],
    "sun metal":     ["太陽メタル", "サンメタル"],
    "bracelet":      ["ブレス"],
    "ring":          ["リング"],
    "concho":        ["コンチョ"],
    "cross":         ["クロス"],
    "belt":          ["ベルト"],
    "spoon":         ["スプーン"],
    "gold":          ["ゴールド", "金"],
    "claw":          ["爪"],
    "sv sun":        ["SV太陽", "銀太陽", "SVIN太陽"],
    "gold sun":      ["K18太陽"],
    "gold insun":    ["K18IN太陽"],
}

def detect_eco_category(keyword):
    kw = keyword.lower()
    if "large feather" in kw or "特大フェザー" in keyword: return "feather"
    if "heart feather" in kw or "ハートホイールフェザー" in keyword: return "heartfeather"
    if "plain feather" in kw or "プレーン" in keyword: return "plainfeather"
    if "used feather" in kw: return "usedfeather"
    if "gold tip" in kw or "先金" in keyword: return "feather"
    if "gold top" in kw or "上金" in keyword: return "feather"
    if "claw" in kw or "爪" in keyword: return "feather"
    if "sv sun" in kw or "gold sun" in kw or "gold insun" in kw: return "metal"
    if "sun metal" in kw or "太陽メタル" in keyword: return "metal"
    if "wheel" in kw or "ホイール" in keyword: return "wheel"
    if "hook" in kw or "フック" in keyword: return "hook"
    if "eagle" in kw or "イーグル" in keyword: return "eagle"
    if "bracelet" in kw or "brace" in kw or "ブレス" in keyword: return "brace"
    if "ring" in kw or "リング" in keyword: return "ring"
    if "concho" in kw or "コンチョ" in keyword: return "concho"
    if "cross" in kw or "クロス" in keyword: return "cross"
    if "belt" in kw or "ベルト" in keyword: return "belt"
    if "spoon" in kw or "スプーン" in keyword: return "spoon"
    if "metal" in kw or "メタル" in keyword: return "metal"
    if "feather" in kw or "フェザー" in keyword: return "feather"
    return None

def search_eco_category(category_key, keyword, max_items=50, exclude_terms=None):
    try:
        category_items = scrape_instock_from_category(category_key, max_items=100, include_sold=True)
        jp_keywords = ECO_KEYWORD_JP_MAP.get(keyword.lower(), [])
        exclude_terms = exclude_terms or []
        items = []
        for it in category_items:
            name_jp = it["name_jp"]
            name_en_check = it["name_en"]
            if any(ex in name_en_check.lower() or ex in name_jp for ex in exclude_terms):
                continue
            jp_match = any(jk in name_jp for jk in jp_keywords) if jp_keywords else False
            en_match = keyword.lower() in name_en_check.lower() or keyword.lower() in name_jp.lower()
            if not (jp_match or en_match):
                continue
            items.append(it)
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"ECO category search error: {e}"); return []


async def check_eco_deal_item_kw(item, keyword, sgd_rate):
    async with ECO_SEMAPHORE:
        try:
            jp_keywords = ECO_KEYWORD_JP_MAP.get(keyword.lower(), [keyword])
            site_sold = await asyncio.to_thread(
                scrape_sold_from_category, item["category"], jp_keywords, 1
            )
            if not site_sold:
                return None
            margin = check_price_margin(item["price"], site_sold, threshold_percent=10, always_show=False)
            if margin and "BELOW" in margin:
                return {**item, "margin": margin, "site_sold": site_sold}
            return None
        except Exception as e:
            print(f"ECO keyword deal check error for {item['name_jp']}: {e}")
            return None


async def cmd_ecodeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip()

    rates = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")

    # ── Keyword mode: single category, keyword-filtered ──
    if keyword:
        category_key = detect_eco_category(keyword)
        if not category_key:
            await update.message.reply_text(
                "❌ Couldn't detect category.\n"
                "Try: feather, large feather, wheel, hook, eagle, metal, sun metal, "
                "bracelet, ring, concho, cross, belt, spoon, gold tip, claw, "
                "sv sun, gold sun, gold insun"
            )
            return

        await update.message.reply_text(f"💰 Scanning eaglecapitalone '{keyword}' items for underpriced deals...")

        matching_instock = await asyncio.to_thread(search_eco_category, category_key, keyword, 100)
        if not matching_instock:
            await update.message.reply_text(f"❌ No in-stock items found matching '{keyword}'.")
            return

        tasks = [check_eco_deal_item_kw(i, keyword, sgd_rate) for i in matching_instock]
        results = await asyncio.gather(*tasks)
        deals = [r for r in results if r is not None]

        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return

        if not deals:
            await update.message.reply_text(
                f"📊 No '{keyword}' items found that are 10%+ below market average right now."
            )
            return

        await update.message.reply_text(
            f"💰 Found {len(deals)} underpriced '{keyword}' item(s) on eaglecapitalone!\n{'─' * 30}"
        )

        for idx, i in enumerate(deals[:10], 1):
            if is_paused(chat_id):
                await update.message.reply_text(f"⏸️ Stopped at item {idx}. Type /resume to continue.")
                return
            price_line = format_price(i["price"], sgd_rate)
            caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{i['margin']}\n📊 Similar sold:"
            for s in i["site_sold"][:3]:
                caption += f"\n  • {s['name_en']}: {format_price(s['price'], sgd_rate)}"
            if i.get("product_url"):
                caption += f"\n🔗 {i['product_url']}"
            await safe_send(
                context, update.effective_chat.id,
                photo=i.get("img_url"),
                caption=caption if i.get("img_url") else None,
                text=caption if not i.get("img_url") else None
            )
            await asyncio.sleep(0.5)

        if len(deals) > 10:
            await update.message.reply_text(f"ℹ️ Showing top 10 of {len(deals)} deals found.")
        return

    # ── No keyword: scan all categories ──
    await update.message.reply_text(
        "💰 Scanning eaglecapitalone for underpriced items...\n"
        "⚡ Checking all categories in parallel — this may take 1-2 minutes"
    )

    all_items = []
    for category_key in ECO_CATEGORY_URLS:
        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return
        items = await asyncio.to_thread(scrape_instock_from_category, category_key, 20)
        all_items.extend(items)
        await asyncio.sleep(1)  # small delay between category fetches

    if not all_items:
        await update.message.reply_text("❌ Could not fetch items. Try again later.")
        return

    await update.message.reply_text(
        f"✅ Found {len(all_items)} in-stock items across all categories.\n"
        f"🔍 Now checking prices against market averages..."
    )

    tasks = [check_eco_deal_item(item, sgd_rate) for item in all_items]
    results = await asyncio.gather(*tasks)
    deals = [r for r in results if r is not None]

    if is_paused(chat_id):
        await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
        return

    if not deals:
        await update.message.reply_text(
            "📊 No items found that are 10%+ below market average right now.\n"
            "Everything appears to be priced at or above market."
        )
        return

    await update.message.reply_text(
        f"💰 Found {len(deals)} underpriced item(s)!\n{'─' * 30}"
    )

    for idx, i in enumerate(deals[:10], 1):  # cap at 10 results
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}. Type /resume to continue.")
            return

        price_line = format_price(i["price"], sgd_rate)
        is_loose = any(s.get("loose_match") for s in i["site_sold"])
        sold_label = "📊 Similar sold (loose match):" if is_loose else "📊 Similar sold:"

        caption = (
            f"{idx}. {i['name_en']}\n"
            f"({i['name_jp']})\n"
            f"{price_line}\n"
            f"{i['margin']}\n"
            f"{sold_label}"
        )
        for s in i["site_sold"][:3]:
            caption += f"\n  • {s['name_en']}: {format_price(s['price'], sgd_rate)}"

        if i.get("product_url"):
            caption += f"\n🔗 {i['product_url']}"

        await safe_send(
            context, update.effective_chat.id,
            photo=i.get("img_url"),
            caption=caption if i.get("img_url") else None,
            text=caption if not i.get("img_url") else None
        )
        await asyncio.sleep(0.5)

    if len(deals) > 10:
        await update.message.reply_text(
            f"ℹ️ Showing top 10 of {len(deals)} deals found. "
            f"Run /ecodeal <keyword> to dig deeper into a specific category, "
            f"or /soldonsite <category> for raw sold history."
        )


def get_similar_sold_prices(name_en, name_jp, max_results=3):
    category_key = detect_category(name_en, name_jp)
    if not category_key: return []
    jp_base = re.sub(r'【.*?】', '', name_jp).strip()
    stop_words = {'the','and','for','with','on','at','in','of','a','an','current','latest','cast','old','new','good','condition','product','excellent','very','rare','individual','diameter','model','size','weight','right','left','no','super','hobo','mint','almost','barely','thick'}
    en_base = re.sub(r'\[.*?\]', '', name_en).strip().lower()
    en_words = [w for w in en_base.split() if len(w) >= 2 and w not in stop_words]
    sold_items = []
    if "プレーンフェザー" in name_jp or "plain feather" in en_base:
        sold_items = scrape_sold_from_category(category_key, ["プレーンフェザー","plain","feather"], min_matches=2)
    elif "先金" in name_jp:
        sold_items = scrape_sold_from_category(category_key, ["先金特大フェザー"], min_matches=1)
        sold_items = [s for s in sold_items if "縄" not in s["name_jp"] and "ターコイズ" not in s["name_jp"] and "上金" not in s["name_jp"]]
    elif "ハートホイールフェザー" in name_jp:
        sold_items = scrape_sold_from_category(category_key, ["ハートホイールフェザー"], min_matches=1)
    elif category_key == "hook":
        sold_items = scrape_sold_from_category(category_key, ["イーグルフック","ホイールチェーン","太角","フックホイール"], min_matches=1)
    else:
        kws = [jp_base] if jp_base else en_words
        sold_items = scrape_sold_from_category(category_key, kws, min_matches=1 if jp_base else 2)
    if not sold_items:
        fallback = {"wheel":["ホイール","wheel"],"feather":["フェザー","feather"],"heartfeather":["フェザー","feather"],"plainfeather":["フェザー","feather"],"usedfeather":["フェザー","feather"],"hook":["フック","ホイール","hook","wheel","chain"],"eagle":["イーグル","eagle"],"metal":["メタル","metal"],"brace":["ブレス","bracelet"],"ring":["リング","ring"],"concho":["コンチョ","concho"],"cross":["クロス","cross"],"belt":["ベルト","belt"],"spoon":["スプーン","spoon"]}.get(category_key, en_words or [jp_base])
        sold_items = scrape_sold_from_category(category_key, fallback, min_matches=1)
        for s in sold_items: s["loose_match"] = True
    return sold_items[:max_results]

def get_goros_prices_grouped():
    if price_cache["data"] and (time.time() - price_cache["timestamp"]) < CACHE_DURATION:
        return price_cache["data"]
    try:
        scraper = make_scraper()
        scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        time.sleep(3)
        response = scraper.get("https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/", timeout=20)
        if response.status_code != 200: return price_cache["data"] or []
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Scraper error: {e}"); return price_cache["data"] or []
    grouped, section, items = [], "General", []
    for el in soup.find_all(["h1","h2","h3","h4","table"]):
        if el.name in ["h1","h2","h3","h4"]:
            if items: grouped.append({"section": section, "items": items}); items = []
            section = translate_to_english(el.get_text(strip=True))
        elif el.name == "table":
            for row in el.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 2:
                    jp, pr = cols[0].get_text(strip=True), cols[1].get_text(strip=True)
                    items.append({"item_en": translate_to_english(jp), "item_jp": jp, "price": pr})
    if items: grouped.append({"section": section, "items": items})
    if grouped: price_cache["data"], price_cache["timestamp"] = grouped, time.time()
    return grouped

def get_new_arrivals(force_refresh=False):
    cache = new_arrivals_cache["eco"]
    if not force_refresh and cache["data"] is not None and (time.time() - cache["timestamp"]) < NEW_ARRIVALS_CACHE_DURATION:
        return cache["data"], cache["date"]
    try:
        scraper = make_scraper()
        response = scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        if response.status_code != 200: return cache["data"] or [], cache["date"] or ""
        soup = BeautifulSoup(response.text, "html.parser")
        update_date, section = "", None
        for h in soup.find_all(["h1","h2","h3","h4"]):
            text = h.get_text(strip=True)
            if "新着" in text and "入荷" not in text:
                update_date, section = translate_to_english(text), h; break
        if not section: return [], ""
        names, prices, imgs, urls = [], [], [], []
        for sib in section.find_all_next():
            if sib.name in ["h1","h2","h3","h4"] and "カテゴリ" in sib.get_text(strip=True): break
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
                if "￥" in p or "¥" in p: prices.append(p)
        items = []
        for idx in range(min(len(names), len(prices))):
            nj = names[idx]
            items.append({"name_jp": nj, "name_en": translate_to_english(nj) if is_japanese(nj) else nj, "price": prices[idx], "img_url": imgs[idx] if idx < len(imgs) else None, "product_url": urls[idx] if idx < len(urls) else None, "is_reserved": "専用販売" in nj})
        new_arrivals_cache["eco"] = {"data": items, "date": update_date, "timestamp": time.time()}
        return items, update_date
    except Exception as e:
        print(f"New arrivals error: {e}"); return cache["data"] or [], cache["date"] or ""


# ════════════════════════════════════════════════════════════════
#  RINKAN
# ════════════════════════════════════════════════════════════════
def scrape_rinkan_category_all(category_url, max_items=150, max_pages=3):
    """Scrape ALL items (in-stock + sold) from a Rinkan category page, following
    pagination. Categories can have 100-300+ items across multiple pages, and
    rarer attributes (e.g. gold fittings, turquoise) may only appear on later
    pages if sorted by newest-first — a single-page scrape would miss them."""
    all_items = []
    seen_hrefs = set()

    # Extract the numeric category code so we can build page URLs for page 2+
    code_match = re.search(r'/category/(\d+)', category_url)
    category_code = code_match.group(1) if code_match else None

    for page_num in range(1, max_pages + 1):
        if len(all_items) >= max_items:
            break

        if page_num == 1:
            page_url = category_url
        elif category_code:
            page_url = f"https://www.rinkan-goros.com/shopbrand/{category_code}/page{page_num}/brandname/"
        else:
            break  # can't build page 2+ URLs without a category code

        try:
            scraper = make_scraper()
            response = scraper.get(page_url, headers=RINKAN_HEADERS, timeout=20)
            if response.status_code != 200 or len(response.text) < 5000:
                break
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
                if base_href in seen_hrefs:
                    continue
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

            page_item_count = 0
            for base_href, data in products.items():
                if not data["name_jp"]:
                    continue
                name_jp = data["name_jp"]
                link_pos = html.find(base_href)
                if link_pos == -1:
                    continue
                chunk = html[max(0, link_pos - 500):link_pos + 1500]
                price_match = re.search(r'([\d,]+)円', chunk)
                if not price_match:
                    continue
                price_str = price_match.group(1) + "円"
                sold_out = bool(re.search(r'soldout|sold[\s_-]?out|売り切れ', chunk, re.IGNORECASE))
                name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
                all_items.append({
                    "name_jp": name_jp,
                    "name_en": name_en,
                    "price": price_str,
                    "img_url": data["img_url"],
                    "product_url": "https://www.rinkan-goros.com" + base_href,
                    "sold_out": sold_out,
                    "source": "Rinkan",
                })
                seen_hrefs.add(base_href)
                page_item_count += 1
                if len(all_items) >= max_items:
                    break

            if page_item_count == 0:
                break  # end of category, no more pages have new items

        except Exception as e:
            print(f"Rinkan category scrape error (page {page_num}): {e}")
            break

    print(f"Rinkan category scrape: {len(all_items)} items across pages ({sum(1 for i in all_items if i['sold_out'])} sold)")
    return all_items


def get_rinkan_comps(item, category_items):
    stop_words = {'the','and','for','with','on','at','in','of','a','an','current','latest',
                  'old','new','good','condition','excellent','very','rare','individual',
                  'model','size','right','left','no','super','mint'}
    name_en_base = re.sub(r'\[.*?\]', '', item["name_en"]).strip().lower()
    key_words = [w for w in name_en_base.split() if len(w) >= 3 and w not in stop_words]
    item_tags = extract_rinkan_tags(item["name_jp"], item["name_en"])

    def overlaps(other):
        if other["product_url"] == item["product_url"]:
            return False
        combined = (other["name_en"] + " " + other["name_jp"]).lower()
        kw_match = any(kw in combined for kw in key_words) if key_words else True
        if not kw_match:
            return False
        other_tags = extract_rinkan_tags(other["name_jp"], other["name_en"])
        return tags_compatible(item_tags, other_tags)

    sold_comps = [c for c in category_items if c.get("sold_out") and overlaps(c)]
    if len(sold_comps) >= 2:
        return sold_comps, False
    all_comps = [c for c in category_items if overlaps(c)]
    return all_comps, True


async def check_rinkan_deal_item(item, category_items, sgd_rate):
    async with RINKAN_SEMAPHORE:
        try:
            comps, loose = await asyncio.to_thread(get_rinkan_comps, item, category_items)
            if len(comps) < 2:
                return None
            margin = check_price_margin(item["price"], comps, threshold_percent=10, always_show=False)
            if margin and "BELOW" in margin:
                for c in comps:
                    c["loose_match"] = loose
                return {**item, "margin": margin, "site_sold": comps[:3]}
            return None
        except Exception as e:
            print(f"Rinkan deal check error for {item['name_jp']}: {e}")
            return None


def get_rinkan_comps_by_keyword(item, category_items, keyword):
    jp_keywords = RINKAN_KEYWORD_JP_MAP.get(keyword.lower(), [])
    exclude_terms = ["feather", "フェザー"] if keyword.lower() == "wheel" else []

    item_tags = extract_rinkan_tags(item["name_jp"], item["name_en"])

    def matches(other):
        combined_en = other["name_en"].lower()
        combined_jp = other["name_jp"]
        if any(ex in combined_en or ex in combined_jp for ex in exclude_terms):
            return False
        en_match = keyword.lower() in combined_en
        jp_match = any(jk in combined_jp for jk in jp_keywords) if jp_keywords else False
        if not (en_match or jp_match):
            return False
        other_tags = extract_rinkan_tags(other["name_jp"], other["name_en"])
        return tags_compatible(item_tags, other_tags)

    def is_self(other):
        return other["product_url"] == item["product_url"]

    sold_comps = [c for c in category_items if c.get("sold_out") and matches(c) and not is_self(c)]
    if len(sold_comps) >= 2:
        return sold_comps, False
    all_comps = [c for c in category_items if matches(c) and not is_self(c)]
    return all_comps, True


async def check_rinkan_deal_item_kw(item, category_items, keyword, sgd_rate):
    async with RINKAN_SEMAPHORE:
        try:
            comps, loose = await asyncio.to_thread(
                get_rinkan_comps_by_keyword, item, category_items, keyword
            )
            if len(comps) < 2:
                return None
            margin = check_price_margin(item["price"], comps, threshold_percent=10, always_show=False)
            if margin and "BELOW" in margin:
                for c in comps:
                    c["loose_match"] = loose
                return {**item, "margin": margin, "site_sold": comps[:3]}
            return None
        except Exception as e:
            print(f"Rinkan keyword deal check error for {item['name_jp']}: {e}")
            return None


async def cmd_rinkandeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update):
        return
    chat_id = update.effective_chat.id
    keyword = " ".join(context.args).strip()

    rates = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")

    # ── Keyword mode: single category, keyword-filtered ──
    if keyword:
        category_key = detect_rinkan_category(keyword)
        if not category_key:
            await update.message.reply_text(
                "❌ Couldn't detect category.\n"
                "Try: feather, large feather, ring, bracelet, necklace, belt, concho, wallet, bag, metal, gold, "
                "gold top, silver top, kamikane, tip, turquoise, wheel, eagle, allgold, claw, "
                "sv sun, gold sun, gold insun"
            )
            return
        category_url = RINKAN_CATEGORY_URLS.get(category_key)

        await update.message.reply_text(f"💰 Scanning Rinkan '{keyword}' items for underpriced deals...")

        category_items = await asyncio.to_thread(scrape_rinkan_category_all, category_url, 300, 6)
        if not category_items:
            await update.message.reply_text("❌ Could not fetch items. Try again later.")
            return

        # Exclude feather items when searching for pure "wheel"
        exclude_terms = []
        if keyword.lower() == "wheel":
            exclude_terms = ["feather", "フェザー"]

        jp_keywords = RINKAN_KEYWORD_JP_MAP.get(keyword.lower(), [])

        matching_instock = [
            i for i in category_items
            if not i.get("sold_out")
            and (
                keyword.lower() in i["name_en"].lower()
                or keyword.lower() in i["name_jp"].lower()
                or any(jk in i["name_jp"] for jk in jp_keywords)
            )
            and not any(ex in i["name_en"].lower() or ex in i["name_jp"] for ex in exclude_terms)
        ]
        if not matching_instock:
            await update.message.reply_text(f"❌ No in-stock items found matching '{keyword}'.")
            return

        tasks = [check_rinkan_deal_item_kw(i, category_items, keyword, sgd_rate) for i in matching_instock]
        results = await asyncio.gather(*tasks)
        deals = [r for r in results if r is not None]

        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return

        if not deals:
            await update.message.reply_text(
                f"📊 No '{keyword}' items found that are 10%+ below market average right now."
            )
            return

        await update.message.reply_text(
            f"💰 Found {len(deals)} underpriced '{keyword}' item(s) on Rinkan!\n{'─' * 30}"
        )

        for idx, i in enumerate(deals[:10], 1):
            if is_paused(chat_id):
                await update.message.reply_text(f"⏸️ Stopped at item {idx}. Type /resume to continue.")
                return
            price_line = format_price(i["price"], sgd_rate)
            is_loose = any(s.get("loose_match") for s in i["site_sold"])
            comp_label = "📊 Similar listings (loose match):" if is_loose else "📊 Similar sold/listed:"
            caption = (
                f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{i['margin']}\n{comp_label}"
            )
            for s in i["site_sold"][:3]:
                tag = " (sold)" if s.get("sold_out") else ""
                caption += f"\n  • {s['name_en']}{tag}: {format_price(s['price'], sgd_rate)}"
            if i.get("product_url"):
                caption += f"\n🔗 {i['product_url']}"
            await safe_send(
                context, update.effective_chat.id,
                photo=i.get("img_url"),
                caption=caption if i.get("img_url") else None,
                text=caption if not i.get("img_url") else None
            )
            await asyncio.sleep(0.5)

        if len(deals) > 10:
            await update.message.reply_text(f"ℹ️ Showing top 10 of {len(deals)} deals found.")
        return

    # ── No keyword: scan all categories (original behavior) ──
    await update.message.reply_text(
        "💰 Scanning Rinkan for underpriced items...\n"
        "⚡ Checking all categories in parallel — this may take 1-2 minutes"
    )

    all_deals = []
    seen_urls = set()
    for category_url in RINKAN_CATEGORY_URLS.values():
        if category_url in seen_urls:
            continue
        seen_urls.add(category_url)

        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return

        category_items = await asyncio.to_thread(scrape_rinkan_category_all, category_url, 300, 6)
        if not category_items:
            await asyncio.sleep(1)
            continue

        instock_items = [i for i in category_items if not i.get("sold_out")]
        tasks = [check_rinkan_deal_item(i, category_items, sgd_rate) for i in instock_items]
        results = await asyncio.gather(*tasks) if tasks else []
        all_deals.extend([r for r in results if r is not None])
        await asyncio.sleep(1)

    if is_paused(chat_id):
        await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
        return

    if not all_deals:
        await update.message.reply_text(
            "📊 No items found on Rinkan that are 10%+ below market average right now."
        )
        return

    await update.message.reply_text(f"💰 Found {len(all_deals)} underpriced item(s) on Rinkan!\n{'─' * 30}")

    for idx, i in enumerate(all_deals[:10], 1):
        if is_paused(chat_id):
            await update.message.reply_text(f"⏸️ Stopped at item {idx}. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        is_loose = any(s.get("loose_match") for s in i["site_sold"])
        comp_label = "📊 Similar listings (loose match):" if is_loose else "📊 Similar sold/listed:"
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{i['margin']}\n{comp_label}"
        for s in i["site_sold"][:3]:
            tag = " (sold)" if s.get("sold_out") else ""
            caption += f"\n  • {s['name_en']}{tag}: {format_price(s['price'], sgd_rate)}"
        if i.get("product_url"):
            caption += f"\n🔗 {i['product_url']}"
        await safe_send(
            context, update.effective_chat.id,
            photo=i.get("img_url"),
            caption=caption if i.get("img_url") else None,
            text=caption if not i.get("img_url") else None
        )
        await asyncio.sleep(0.5)

    if len(all_deals) > 10:
        await update.message.reply_text(
            f"ℹ️ Showing top 10 of {len(all_deals)} deals found. "
            f"Run /rinkandeal <keyword> to dig deeper into a specific category."
        )


def get_rinkan_new_arrivals(force_refresh=False):
    cache = new_arrivals_cache["rinkan"]
    if not force_refresh and cache["data"] is not None and (time.time() - cache["timestamp"]) < NEW_ARRIVALS_CACHE_DURATION:
        return cache["data"]
    try:
        scraper = make_scraper()
        response = scraper.get(RINKAN_URL, headers=RINKAN_HEADERS, timeout=20)
        if response.status_code != 200: return cache["data"] or []
        response.encoding = "euc_jp"
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=re.compile(r'/shopdetail/\d+/?$'))
        products = {}
        for link in all_links:
            href = link.get("href", "")
            if href not in products: products[href] = {"img_url": None, "name_jp": None}
            img_tag = link.find("img")
            if img_tag and img_tag.get("src"):
                src = img_tag["src"]
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = "https://www.rinkan-goros.com" + src
                if products[href]["img_url"] is None: products[href]["img_url"] = src
            text = link.get_text(strip=True)
            if text and len(text) > 2: products[href]["name_jp"] = text
        items = []
        for href, data in products.items():
            if not data["name_jp"]: continue
            name_jp = data["name_jp"]
            link_pos = html.find(href)
            if link_pos == -1: continue
            chunk = html[link_pos:link_pos + 1500]
            price_match = re.search(r'([\d,]+)円', chunk)
            if not price_match: continue
            price_str = price_match.group(1) + "円"
            full_url = "https://www.rinkan-goros.com" + href
            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            items.append({"name_jp": name_jp, "name_en": name_en, "price": price_str, "img_url": data["img_url"], "product_url": full_url, "source": "Rinkan"})
        new_arrivals_cache["rinkan"] = {"data": items, "timestamp": time.time()}
        return items
    except Exception as e:
        print(f"Rinkan scrape error: {e}"); return cache["data"] or []

def check_rinkan_availability(scraper, product_url, retries=2):
    for attempt in range(retries):
        try:
            response = scraper.get(product_url, headers=RINKAN_HEADERS, timeout=15)
            response.encoding = "euc_jp"
            html = response.text
            if len(html) < 5000: time.sleep(8); continue
            if re.search(r'class=["\']soldout["\']', html): return "❌ Sold Out"
            if "basketBtn" in html or "カートに入れる" in html or "すぐに購入する" in html: return "✅ In Stock"
            return "❓ Unknown"
        except Exception as e:
            print(f"Rinkan availability error: {e}"); time.sleep(3)
    return "❓ Unknown"


RINKAN_KEYWORD_JP_MAP = {
    "gold":            ["金", "ゴールド", "上金", "先金"],
    "silver":          ["銀", "シルバー", "SV", "上銀", "先銀"],
    "gold top":        ["上金"],
    "silver top":      ["上銀"],
    "kamikane":        ["上金", "上銀"],
    "kamigane":        ["上金", "上銀"],
    "tip":             ["先金", "先銀"],
    "tip gold":        ["先金"],
    "tip silver":      ["先銀"],
    "turquoise":       ["ターコイズ"],
    "rope":            ["縄", "ロープ"],
    "turquoise rope":  ["ターコイズ", "縄"],
    "old":             ["オールド", "OLD"],
    "new":             ["新品"],
    "plain":           ["プレーン"],
    "rare":            ["希少", "レア"],
    "bag":             ["バッグ"],
    "concho":          ["コンチョ"],
    "wheel":           ["ホイール"],
    "ring":            ["リング"],
    "bracelet":        ["ブレス"],
    "necklace":        ["ネックレス"],
    "belt":            ["ベルト"],
    "wallet":          ["財布"],
    "metal":           ["メタル"],
    "sunmetal":        ["太陽メタル", "サンメタル"],
    "sv sun":          ["SV太陽", "銀太陽", "太陽"],
    "gold sun":        ["全金メタル"],
    "gold insun":      ["全金太陽メタル"],
    "eagle":           ["イーグル"],
    "claw":            ["クロー"],
    "allgold":         ["全金"],
}

def detect_rinkan_category(keyword):
    kw = keyword.lower()
    if "large feather" in kw or "特大フェザー" in keyword: return "largefeather"
    if "wheel feather" in kw or "ホイールフェザー" in keyword: return "feather"
    if "wheel" in kw or "ホイール" in keyword: return "wheel"
    if any(t in kw for t in ["gold top", "silver top", "kamikane", "kamigane"]): return "largefeather"
    if "tip" in kw or "先金" in keyword or "先銀" in keyword: return "largefeather"
    if "turquoise" in kw or "ターコイズ" in keyword: return "largefeather"
    if "sv sun" in kw or "gold sun" in kw or "gold insun" in kw: return "metal"
    if "allgold" in kw or "all gold" in kw: return "allgold"
    if "claw" in kw or "クロー" in keyword: return "largefeather"
    if "feather" in kw or "フェザー" in keyword: return "feather"
    if "ring" in kw or "リング" in keyword: return "ring"
    if "necklace" in kw or "ネックレス" in keyword: return "necklace"
    if "bracelet" in kw or "ブレス" in keyword: return "bracelet"
    if "belt" in kw or "ベルト" in keyword: return "belt"
    if "concho" in kw or "コンチョ" in keyword: return "concho"
    if "bag" in kw or "バッグ" in keyword: return "bag"
    if "wallet" in kw or "財布" in keyword: return "wallet"
    if "metal" in kw or "メタル" in keyword: return "metal"
    if "eagle" in kw or "イーグル" in keyword: return "eagle"
    if "gold" in kw or "金" in keyword or "ゴールド" in keyword: return "largefeather"
    if "silver" in kw or "銀" in keyword or "シルバー" in keyword: return "largefeather"
    return None

def search_rinkan_category(category_url, keyword, max_items=10, exclude_jp=None):
    try:
        category_items = scrape_rinkan_category_all(category_url, max_items=300, max_pages=6)
        jp_keywords = RINKAN_KEYWORD_JP_MAP.get(keyword.lower(), [])
        exclude_jp = exclude_jp or []
        items = []
        for it in category_items:
            name_jp = it["name_jp"]
            name_en_check = it["name_en"]
            if any(ex in name_jp for ex in exclude_jp):
                continue
            jp_match = any(jk in name_jp for jk in jp_keywords) if jp_keywords else False
            en_match = keyword.lower() in name_en_check.lower() or keyword.lower() in name_jp.lower()
            if not (jp_match or en_match):
                continue
            items.append({
                "name_jp": name_jp,
                "name_en": name_en_check,
                "price": it["price"],
                "img_url": it["img_url"],
                "product_url": it["product_url"],
                "source": "Rinkan",
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"Rinkan category search error: {e}"); return []


# ════════════════════════════════════════════════════════════════
#  DELTAONE
# ════════════════════════════════════════════════════════════════
def _parse_deltaone_links(soup):
    items, seen_urls = [], set()
    for link in soup.find_all("a", href=re.compile(r'/collections/.+/products/')):
        href = link.get("href", "")
        full_url = href if href.startswith("http") else "https://www.deltaone.jp" + href
        if full_url in seen_urls: continue
        seen_urls.add(full_url)
        raw_text = link.get_text(strip=True)
        if not raw_text or len(raw_text) < 3: continue
        price_match = re.search(r'¥[\d,]+', raw_text)
        if not price_match: continue
        price_str = price_match.group()
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
        is_sold_out = bool(parent and ("Sold Out" in parent.get_text() or "売り切れ" in parent.get_text()))
        name_en = translate_to_english(clean_name) if is_japanese(clean_name) else clean_name
        items.append({"name_jp": clean_name, "name_en": name_en, "price": price_str, "img_url": img_url, "product_url": full_url, "sold_out": is_sold_out, "source": "DELTAone"})
    return items

def get_deltaone_new_arrivals(max_items=15):
    try:
        scraper = make_scraper()
        response = scraper.get(DELTAONE_URL, timeout=20)
        if response.status_code != 200: return []
        items = _parse_deltaone_links(BeautifulSoup(response.text, "html.parser"))
        return items[:max_items]
    except Exception as e:
        print(f"DELTAone scrape error: {e}"); return []

def detect_deltaone_category(keyword):
    kw = keyword.lower()
    if "large feather" in kw or "特大フェザー" in keyword or "フェザーxl" in keyword.replace(" ","").lower(): return "largefeather"
    if "feather" in kw or "フェザー" in keyword: return "feather"
    if "eagle ring" in kw or "リングイーグル" in keyword.replace(" ",""): return "ringeagle"
    if "feather ring" in kw or "リングフェザー" in keyword.replace(" ",""): return "ringfeather"
    if "eagle" in kw or "イーグル" in keyword: return "eagle"
    if "leather brace" in kw or "ブレス革" in keyword.replace(" ",""): return "leatherbrace"
    if "face bracelet" in kw or "ブレス顔" in keyword.replace(" ",""): return "facebracelet"
    if "bracelet" in kw or "ブレス" in keyword: return "bracelet"
    if "wheel" in kw or "ホイール" in keyword: return "wheel"
    if "leather cord" in kw or "革紐" in keyword: return "leathercord"
    if "chain" in kw or "チェーン" in keyword: return "chain"
    if "sv sun" in kw or "gold sun" in kw or "gold insun" in kw: return "sunmetal"
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
    if "very rare" in kw or "超希少" in keyword: return "veryrare"
    if "rare" in kw or "希少" in keyword: return "rare"
    if "custom" in kw or "特注" in keyword: return "custom"
    if "current" in kw or "現行" in keyword: return "current"
    if "sale" in kw or "セール" in keyword: return "sale"
    if "old" in kw: return "old"
    return None

deltaone_category_cache = {}  # category_url -> {"data": [...], "timestamp": 0}
DELTAONE_CATEGORY_CACHE_DURATION = 600  # 10 minutes

def search_deltaone_category(category_url, keyword=None, max_items=50, exclude_terms=None, force_refresh=False):
    """Scrape a DELTAone category page. Caches the full scraped+translated
    result per category_url for DELTAONE_CATEGORY_CACHE_DURATION seconds.
    Filters results to only items whose name_jp contains one of the JP
    terms mapped to `keyword` in DELTA_KEYWORD_JP_MAP — same jp_keywords/
    exclude_terms pattern as search_eco_category and search_rinkan_category.

    Matching is case-insensitive because DELTAone's actual product names
    use mixed case for the fitting suffix (e.g. 'K18in太陽メタル', not
    'K18IN太陽メタル'), which a case-sensitive `in` check would miss."""
    cached = deltaone_category_cache.get(category_url)
    if not force_refresh and cached and (time.time() - cached["timestamp"]) < DELTAONE_CATEGORY_CACHE_DURATION:
        category_items = cached["data"]
    else:
        try:
            scraper = make_scraper()
            response = scraper.get(category_url, timeout=20)
            if response.status_code != 200:
                category_items = cached["data"] if cached else []
            else:
                category_items = _parse_deltaone_links(BeautifulSoup(response.text, "html.parser"))
                deltaone_category_cache[category_url] = {"data": category_items, "timestamp": time.time()}
        except Exception as e:
            print(f"DELTAone category search error: {e}")
            category_items = cached["data"] if cached else []

    jp_keywords = DELTA_KEYWORD_JP_MAP.get((keyword or "").lower(), [])
    exclude_terms = exclude_terms or []
    if not jp_keywords:
        return category_items[:max_items]

    items = []
    for it in category_items:
        name_jp_upper = it["name_jp"].upper()
        name_en_lower = it["name_en"].lower()
        if any(ex.lower() in name_en_lower or ex.upper() in name_jp_upper for ex in exclude_terms):
            continue
        if any(jk.upper() in name_jp_upper for jk in jp_keywords):
            items.append(it)
        if len(items) >= max_items:
            break
    return items

# ════════════════════════════════════════════════════════════════
#  CONCURRENT HELPERS
# ════════════════════════════════════════════════════════════════
async def check_eco_item_async(scraper, item):
    async with ECO_SEMAPHORE:
        availability = await asyncio.to_thread(check_item_availability, scraper, item["product_url"])
        previous_history = get_sold_history_list(item["name_en"])
        if availability == "❌ Sold Out":
            record_sold_price(item["name_en"], item["name_jp"], item["price"], datetime.now().strftime("%Y-%m-%d %H:%M"))
        site_sold = await asyncio.to_thread(get_similar_sold_prices, item["name_en"], item["name_jp"])
        return {"item": item, "availability": availability, "previous_history": previous_history, "site_sold": site_sold}

async def check_rinkan_item_async(scraper, item):
    async with RINKAN_SEMAPHORE:
        availability = await asyncio.to_thread(check_rinkan_availability, scraper, item["product_url"])
        return {"item": item, "availability": availability}


# ════════════════════════════════════════════════════════════════
#  AUTO-CHECK + WATCHLIST
# ════════════════════════════════════════════════════════════════
async def auto_check_new_arrivals(context):
    """Checks eaglecapitalone for new arrivals. Sends at most ONE notification
    per calendar day (SGT) even if multiple date changes are detected during
    the 6-8pm run window — last_eco_notify_day tracks the date a notification
    was last actually sent, and resets naturally the next day."""
    try:
        items, update_date = await asyncio.to_thread(get_new_arrivals, True)
        if not update_date:
            return

        sgt = pytz.timezone("Asia/Singapore")
        today_str = datetime.now(sgt).strftime("%Y-%m-%d")

        if update_date != last_known_update["date"] and last_known_update["date"] != "":
            if last_eco_notify_day["date"] != today_str:
                await context.bot.send_message(
                    chat_id=context.job.chat_id,
                    text=f"🔔 New arrivals posted!\n📅 {update_date}\n\nType /neweco to see the latest items."
                )
                watches = get_watches(context.job.chat_id)
                for watch in watches:
                    for m in [i for i in items if item_matches_watch(i, watch)][:3]:
                        rates = get_rates(base="JPY")
                        sgd_rate = rates.get("SGD")
                        text = f"👁️ Watchlist match: '{watch['keyword']}'\n\n{m['name_en']}\n({m['name_jp']})\n{format_price(m['price'], sgd_rate)}"
                        if m.get("product_url"):
                            text += f"\n🔗 {m['product_url']}"
                        await safe_send(
                            context, context.job.chat_id,
                            photo=m.get("img_url"),
                            caption=text if m.get("img_url") else None,
                            text=text if not m.get("img_url") else None
                        )
                last_eco_notify_day["date"] = today_str

        last_known_update["date"] = update_date
    except Exception as e:
        print(f"Auto-check error: {e}")


async def auto_check_rinkan_new(context):
    """Every-5-min checker for new Rinkan drops. Compares the current
    'new items' page against the previously seen set of product URLs;
    any URL not seen before is treated as a fresh drop. First run only
    seeds the baseline so it doesn't spam old items as 'new'."""
    global last_known_rinkan_urls
    try:
        sgt = pytz.timezone("Asia/Singapore")
        now_sgt = datetime.now(sgt).time()
        if dtime(18, 0) <= now_sgt <= dtime(20, 0):
            return  # paused — eaglecapitalone has the 6-8pm window to itself
        items = await asyncio.to_thread(get_rinkan_new_arrivals, True)
        if not items:
            return
        current_urls = {i["product_url"] for i in items}
        if last_known_rinkan_urls:
            new_items = [i for i in items if i["product_url"] not in last_known_rinkan_urls]
            if new_items:
                rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
                for i in new_items[:5]:
                    text = f"🆕 New Rinkan drop!\n\n{i['name_en']}\n({i['name_jp']})\n{format_price(i['price'], sgd_rate)}\n🔗 {i['product_url']}"
                    await safe_send(context, context.job.chat_id, photo=i.get("img_url"),
                                     caption=text if i.get("img_url") else None,
                                     text=text if not i.get("img_url") else None)
        last_known_rinkan_urls = current_urls
    except Exception as e:
        print(f"Rinkan auto-check error: {e}")


async def auto_check_delta_new(context):
    """Every-5-min checker for new DELTAone drops. Same seen-URL diffing
    approach as the Rinkan checker above."""
    global last_known_delta_urls
    try:
        sgt = pytz.timezone("Asia/Singapore")
        now_sgt = datetime.now(sgt).time()
        if dtime(18, 0) <= now_sgt <= dtime(20, 0):
            return  # paused — eaglecapitalone has the 6-8pm window to itself
        items = await asyncio.to_thread(get_deltaone_new_arrivals, 15)
        if not items:
            return
        current_urls = {i["product_url"] for i in items}
        if last_known_delta_urls:
            new_items = [i for i in items if i["product_url"] not in last_known_delta_urls]
            if new_items:
                rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
                for i in new_items[:5]:
                    availability = "❌ Sold Out" if i["sold_out"] else "✅ In Stock"
                    text = f"🆕 New DELTAone drop!\n\n{i['name_en']}\n({i['name_jp']})\n{format_price(i['price'], sgd_rate)}\n{availability}\n🔗 {i['product_url']}"
                    await safe_send(context, context.job.chat_id, photo=i.get("img_url"),
                                     caption=text if i.get("img_url") else None,
                                     text=text if not i.get("img_url") else None)
        last_known_delta_urls = current_urls
    except Exception as e:
        print(f"DELTAone auto-check error: {e}")


# ════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ════════════════════════════════════════════════════════════════
async def send_grouped_results(update, title, keywords=None, keyword=None):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔍 Searching... please wait")
    rates, grouped = get_rates(base="JPY"), get_goros_prices_grouped()
    sgd_rate = rates.get("SGD"); found_any = False
    for section in grouped:
        if is_paused(chat_id): await update.message.reply_text("⏸️ Stopped. Type /resume to continue."); return
        if keywords:
            section_match = any(kw.lower() in section["section"].lower() for kw in keywords)
            items = section["items"] if section_match else [i for i in section["items"] if any(kw.lower() in i["item_en"].lower() or kw in i["item_jp"] for kw in keywords)]
        elif keyword:
            section_match = keyword.lower() in section["section"].lower()
            items = section["items"] if section_match else [i for i in section["items"] if keyword.lower() in i["item_en"].lower() or keyword.lower() in i["item_jp"].lower()]
        else:
            items = section["items"]
        if not items: continue
        found_any = True
        msg = f"📋 {section['section']}\n{'─'*30}\n"
        for i in items: msg += f"• {i['item_en']}\n  ({i['item_jp']})\n  {format_price(i['price'], sgd_rate)}\n\n"
        for chunk in range(0, len(msg), 4096): await update.message.reply_text(msg[chunk:chunk+4096])
    if not found_any: await update.message.reply_text(f"❌ No items found for '{title}'")


async def cmd_neweco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching eaglecapitalone new arrivals... please wait\n⚡ Checking items in parallel")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items, update_date = get_new_arrivals()
    if not items: await update.message.reply_text("❌ Could not fetch new arrivals. Try again later."); return
    await update.message.reply_text(f"🆕 {update_date}\n{'─'*30}")
    scraper = make_scraper()
    eligible = [i for i in items if not i.get("is_reserved") and i.get("product_url")]
    results = await asyncio.gather(*[check_eco_item_async(scraper, item) for item in eligible]) if eligible else []
    results_by_url = {r["item"]["product_url"]: r for r in results}
    for idx, i in enumerate(items, 1):
        if is_paused(chat_id): await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue."); return
        price_line = format_price(i["price"], sgd_rate)
        if i.get("is_reserved"):
            availability, previous_history, site_sold, trend_alert, margin_alert = "🔒 Reserved/Exclusive Sale", [], [], None, None
        else:
            r = results_by_url.get(i["product_url"])
            if not r: availability, previous_history, site_sold, trend_alert, margin_alert = "❓ Unknown", [], [], None, None
            else:
                availability, previous_history, site_sold = r["availability"], r["previous_history"], r["site_sold"]
                trend_alert = check_price_trend_vs_similar(i["price"], site_sold, threshold_percent=15, always_show=True) if availability == "❌ Sold Out" and site_sold else None
                margin_alert = check_price_margin(i["price"], site_sold, threshold_percent=10, always_show=True) if availability == "✅ In Stock" and site_sold else None
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}"
        if i.get("product_url"): caption += f"\n🔗 {i['product_url']}"
        if trend_alert: caption += f"\n\n{trend_alert}"
        if margin_alert: caption += f"\n\n{margin_alert}"
        if site_sold:
            is_loose = any(s.get("loose_match") for s in site_sold)
            caption += f"\n\n{'📊 Similar sold (loosely related, latest first):' if is_loose else '📊 Similar sold on site (latest first):'}"
            for s in site_sold: caption += f"\n  • {s['name_en']}\n    {format_price(s['price'], sgd_rate)}"
        if availability == "❌ Sold Out" and previous_history:
            caption += "\n\n🕐 Previously recorded:"
            for r2 in previous_history[:3]: caption += f"\n  • {r2['price']} on {r2['sold_date']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)


async def cmd_newrinkan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching new items from Rinkan... please wait\n⚡ Checking items in parallel")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items = get_rinkan_new_arrivals()
    if not items: await update.message.reply_text("❌ Could not fetch items from Rinkan."); return
    await update.message.reply_text(f"🆕 Rinkan New Items\n{'─'*30}")
    scraper = make_scraper()
    limited_items = items[:15]
    results = await asyncio.gather(*[check_rinkan_item_async(scraper, item) for item in limited_items]) if limited_items else []
    results_by_url = {r["item"]["product_url"]: r["availability"] for r in results}
    for idx, i in enumerate(limited_items, 1):
        if is_paused(chat_id): await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(limited_items)}. Type /resume to continue."); return
        price_line = format_price(i["price"], sgd_rate)
        availability = results_by_url.get(i["product_url"], "❓ Unknown")
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n🏪 Source: Rinkan\n🔗 {i['product_url']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)


async def cmd_newdelta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🆕 Fetching new arrivals from DELTAone... please wait")
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    items = get_deltaone_new_arrivals(max_items=15)
    if not items: await update.message.reply_text("❌ Could not fetch items from DELTAone."); return
    await update.message.reply_text(f"🆕 DELTAone Newest Items\n{'─'*30}")
    for idx, i in enumerate(items, 1):
        if is_paused(chat_id): await update.message.reply_text(f"⏸️ Stopped at item {idx}/{len(items)}. Type /resume to continue."); return
        price_line = format_price(i["price"], sgd_rate)
        availability = "❌ Sold Out" if i["sold_out"] else "✅ In Stock"
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n🏪 Source: DELTAone\n🔗 {i['product_url']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)


async def cmd_rinkansearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /rinsearch <keyword> [page]\n"
            "Example: /rinsearch feather\n"
            "/rinsearch feather 2 — for page 2"
        )
        return

    # If the last arg is a page number, split it off from the keyword
    page = 1
    if len(args) > 1 and args[-1].isdigit():
        page = int(args[-1])
        keyword = " ".join(args[:-1]).strip()
    else:
        keyword = " ".join(args).strip()

    if not keyword:
        await update.message.reply_text("Usage: /rinsearch <keyword> [page]")
        return

    category_key = detect_rinkan_category(keyword)
    if not category_key:
        await update.message.reply_text(
            "❌ Couldn't detect category.\n"
            "Try: feather, ring, bracelet, necklace, belt, concho, wallet, bag, metal, gold, wheel, "
            "eagle, allgold, claw, sv sun, gold sun, gold insun"
        )
        return
    category_url = RINKAN_CATEGORY_URLS.get(category_key)
    await update.message.reply_text(f"🔍 Searching Rinkan for '{keyword}' (page {page})... please wait")

    exclude_jp = []
    if keyword.lower() == "gold":
        exclude_jp = ["上金", "ターコイズ", "メタル付"]
    elif keyword.lower() == "wheel":
        exclude_jp = ["フェザー"]

    all_items = search_rinkan_category(category_url, keyword, max_items=100, exclude_jp=exclude_jp)
    if not all_items:
        await update.message.reply_text(f"❌ No items found for '{keyword}'")
        return

    # Sort by price ascending (lowest first)
    def price_sort_key(it):
        p = parse_price_number(it["price"])
        return p if p is not None else float("inf")
    all_items.sort(key=price_sort_key)

    PAGE_SIZE = 10
    total_items = len(all_items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    items = all_items[start:end]

    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    await update.message.reply_text(
        f"🔍 Rinkan Results for '{keyword}' — page {page}/{total_pages} "
        f"({total_items} total, sorted by price ↑)\n{'─'*30}"
    )
    scraper = make_scraper()
    results = await asyncio.gather(*[check_rinkan_item_async(scraper, item) for item in items]) if items else []
    results_by_url = {r["item"]["product_url"]: r["availability"] for r in results}
    for idx, i in enumerate(items, start + 1):
        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = results_by_url.get(i["product_url"], "❓ Unknown")
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n🏪 Source: Rinkan\n🔗 {i['product_url']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)

    if page < total_pages:
        await update.message.reply_text(
            f"ℹ️ Page {page}/{total_pages}. Type /rinsearch {keyword} {page+1} for the next page."
        )


async def cmd_ecosearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /ecosearch <keyword> [page]\n"
            "Example: /ecosearch feather\n"
            "/ecosearch feather 2 — for page 2"
        )
        return

    page = 1
    if len(args) > 1 and args[-1].isdigit():
        page = int(args[-1])
        keyword = " ".join(args[:-1]).strip()
    else:
        keyword = " ".join(args).strip()

    if not keyword:
        await update.message.reply_text("Usage: /ecosearch <keyword> [page]")
        return

    category_key = detect_eco_category(keyword)
    if not category_key:
        await update.message.reply_text(
            "❌ Couldn't detect category.\n"
            "Try: feather, large feather, wheel, hook, eagle, metal, sun metal, "
            "bracelet, ring, concho, cross, belt, spoon, gold tip, gold top, claw, "
            "sv sun, gold sun, gold insun"
        )
        return

    await update.message.reply_text(f"🔍 Searching eaglecapitalone for '{keyword}' (page {page})... please wait")

    exclude_terms = []
    if keyword.lower() == "sv sun":
        exclude_terms = ["k18"]
    elif keyword.lower() == "gold sun":
        exclude_terms = ["k18in"]

    all_items = search_eco_category(category_key, keyword, max_items=100)
    if not all_items:
        await update.message.reply_text(f"❌ No items found for '{keyword}'")
        return

    # Page order is already newest-posted-first — no re-sort needed

    PAGE_SIZE = 10
    total_items = len(all_items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    items = all_items[start:end]

    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    await update.message.reply_text(
        f"🔍 eaglecapitalone Results for '{keyword}' — page {page}/{total_pages} "
        f"({total_items} total, newest posted first)\n{'─'*30}"
    )
    for idx, i in enumerate(items, start + 1):
        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = "❌ Sold Out" if i.get("sold_out") else "✅ In Stock"
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n🏪 Source: eaglecapitalone\n🔗 {i['product_url']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)

    if page < total_pages:
        await update.message.reply_text(
            f"ℹ️ Page {page}/{total_pages}. Type /ecosearch {keyword} {page+1} for the next page."
        )


async def cmd_deltasearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /deltasearch <keyword> [page]\n"
            "Example: /deltasearch feather\n"
            "/deltasearch feather 2 — for page 2\n"
            "/deltasearch 2 — page 2 of your last search\n\n"
            "Categories: feather, largefeather, eagle, bracelet, wheel, chain, metal, sunmetal, "
            "cross, spoon, heart, concho, ring, belt, bag, wallet, beads, earring, old, rare, custom, current, sale"
        )
        return

    # Bare page number (e.g. "/deltasearch 2") reuses the last keyword for this chat
    if len(args) == 1 and args[0].isdigit():
        page = int(args[0])
        keyword = last_delta_search.get(chat_id)
        if not keyword:
            await update.message.reply_text("❌ No previous search found. Try /deltasearch <keyword> first.")
            return
    elif len(args) > 1 and args[-1].isdigit():
        page = int(args[-1])
        keyword = " ".join(args[:-1]).strip()
    else:
        page = 1
        keyword = " ".join(args).strip()

    if not keyword:
        await update.message.reply_text("Usage: /deltasearch <keyword> [page]")
        return

    category_key = detect_deltaone_category(keyword)
    if not category_key:
        await update.message.reply_text(
            "❌ Couldn't detect category.\n"
            "Try: feather, eagle, bracelet, wheel, chain, metal, cross, spoon, heart, concho, ring, belt, bag, wallet, old, rare, custom"
        )
        return
    category_url = DELTAONE_CATEGORY_URLS.get(category_key)
    last_delta_search[chat_id] = keyword  # remember for bare-page-number follow-ups

    await update.message.reply_text(f"🔍 Searching DELTAone for '{keyword}' (page {page})... please wait")

    exclude_terms = []
    if keyword.lower() == "sv sun":
        exclude_terms = ["k18"]
    elif keyword.lower() == "gold sun":
        exclude_terms = ["k18in"]

    all_items = search_deltaone_category(category_url, keyword=keyword, max_items=100, exclude_terms=exclude_terms)
    if not all_items:
        await update.message.reply_text(f"❌ No items found for '{keyword}'")
        return

    all_items.sort(key=lambda i: _price_to_int(i["price"]))  # cheapest first

    PAGE_SIZE = 10
    total_items = len(all_items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    items = all_items[start:end]

    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    await update.message.reply_text(
        f"🔍 DELTAone Results for '{keyword}' — page {page}/{total_pages} "
        f"({total_items} total, cheapest first)\n{'─'*30}"
    )
    for idx, i in enumerate(items, start + 1):
        if is_paused(chat_id):
            await update.message.reply_text("⏸️ Stopped. Type /resume to continue.")
            return
        price_line = format_price(i["price"], sgd_rate)
        availability = "❌ Sold Out" if i["sold_out"] else "✅ In Stock"
        caption = f"{idx}. {i['name_en']}\n({i['name_jp']})\n{price_line}\n{availability}\n🏪 Source: DELTAone\n🔗 {i['product_url']}"
        await safe_send(context, update.effective_chat.id, photo=i.get("img_url"), caption=caption if i.get("img_url") else None, text=caption if not i.get("img_url") else None)

    if page < total_pages:
        await update.message.reply_text(
            f"ℹ️ Page {page}/{total_pages}. Type /deltasearch {keyword} {page+1} for the next page — "
            f"or just /deltasearch {page+1}"
        )
def _price_to_int(price_str):
    """Extract the numeric JPY value from a price string like '¥140,000' for sorting."""
    digits = re.sub(r'[^\d]', '', price_str or '')
    return int(digits) if digits else float('inf')

async def cmd_soldhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    keyword = " ".join(context.args).strip()
    history = load_sold_history()
    if not history: await update.message.reply_text("📭 No sold history recorded yet."); return
    results = {k: v for k, v in history.items() if keyword.lower() in k} if keyword else history
    if keyword and not results: await update.message.reply_text(f"❌ No sold history found for '{keyword}'"); return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    msg = "🕐 Sold Price History\n" + "─"*30 + "\n\n"
    for key, records in list(results.items())[:20]:
        for r in records[:3]: msg += f"• {r['name_en']}\n  ({r['name_jp']})\n  {format_price(r['price'], sgd_rate)} — sold {r['sold_date']}\n\n"
    for x in range(0, len(msg), 4096): await update.message.reply_text(msg[x:x+4096])


async def cmd_soldonsite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    args = " ".join(context.args).strip()
    if not args: await update.message.reply_text("Usage: /soldonsite <category> <keyword>\nExample: /soldonsite wheel sv"); return
    parts = args.split()
    category_key, search_keywords = parts[0].lower(), parts[1:] or parts
    if category_key not in ECO_CATEGORY_URLS: await update.message.reply_text("❌ Category not found."); return
    await update.message.reply_text(f"🔍 Searching sold items for '{args}'... please wait")
    sold_items = scrape_sold_from_category(category_key, search_keywords)
    if not sold_items: await update.message.reply_text(f"❌ No sold items found for '{args}'"); return
    rates = get_rates(base="JPY"); sgd_rate = rates.get("SGD")
    msg = f"❌ Sold items matching '{args}':\n{'─'*30}\n\n"
    for i in sold_items: msg += f"• {i['name_en']}\n  ({i['name_jp']})\n  {format_price(i['price'], sgd_rate)}\n\n"
    for x in range(0, len(msg), 4096): await update.message.reply_text(msg[x:x+4096])


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args: await update.message.reply_text("Usage: /watch <keyword> [max_price]\nExample: /watch eagle 500000"); return
    max_price = None
    if args[-1].replace(",","").isdigit():
        max_price = float(args[-1].replace(",","")); keyword = " ".join(args[:-1]).strip()
    else:
        keyword = " ".join(args).strip()
    if not keyword: await update.message.reply_text("❌ Please provide a keyword."); return
    add_watch(update.effective_chat.id, keyword, max_price)
    msg = f"👁️ Watching for: '{keyword}'"
    if max_price: msg += f" under ¥{max_price:,.0f}"
    msg += "\n\nMake sure /notify is enabled to get alerts."
    await update.message.reply_text(msg)

async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).strip()
    if not keyword: await update.message.reply_text("Usage: /unwatch <keyword>"); return
    removed = remove_watch(update.effective_chat.id, keyword)
    await update.message.reply_text(f"🗑️ Removed watch for '{keyword}'." if removed else f"❌ No watch found for '{keyword}'.")

async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watches = get_watches(update.effective_chat.id)
    if not watches: await update.message.reply_text("📭 Your watchlist is empty.\nUse /watch <keyword> [max_price] to add one."); return
    msg = "👁️ Your Watchlist:\n" + "─"*30 + "\n\n"
    for w in watches:
        line = f"• {w['keyword']}"
        if w.get("max_price"): line += f" (under ¥{w['max_price']:,.0f})"
        msg += line + "\n"
    await update.message.reply_text(msg)


async def cmd_healthcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🩺 Running healthcheck on all sites... please wait")
    msg = "🩺 Healthcheck Report\n" + "─"*30 + "\n\n"
    try:
        items, _ = get_new_arrivals(force_refresh=True)
        msg += f"eaglecapitalone.com\n  Items parsed: {len(items)}\n\n"
    except Exception as e: msg += f"eaglecapitalone.com\n  ❌ Error: {e}\n\n"
    try:
        rinkan_items = get_rinkan_new_arrivals(force_refresh=True)
        msg += f"rinkan-goros.com\n  Items parsed: {len(rinkan_items)}\n\n"
    except Exception as e: msg += f"rinkan-goros.com\n  ❌ Error: {e}\n\n"
    try:
        delta_items = get_deltaone_new_arrivals(max_items=15)
        msg += f"deltaone.jp\n  Items parsed: {len(delta_items)}\n\n"
    except Exception as e: msg += f"deltaone.jp\n  ❌ Error: {e}\n\n"
    if price_cache["data"]:
        age = int((time.time() - price_cache["timestamp"]) / 60)
        msg += f"💾 Price list cache: {len(price_cache['data'])} sections, {age} min old\n"
    msg += f"📦 Sold history: {len(load_sold_history())} items tracked\n"
    msg += f"👁️ Active watches: {sum(len(v) for v in load_watchlist().values())}\n"
    msg += f"🔁 Self-ping: active (every 5 min)\n"
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
    if not rates: await update.message.reply_text(f"❌ Could not fetch rates for {from_currency}"); return
    if to_currency not in rates: await update.message.reply_text(f"❌ Currency '{to_currency}' not supported."); return
    await update.message.reply_text(f"💱 {amount:.2f} {from_currency} ≈ {amount * rates[to_currency]:.2f} {to_currency}\n⚠️ Approximate exchange rate")


async def list_currencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates = get_rates("SGD")
    if not rates: await update.message.reply_text("❌ Unable to fetch currency list."); return
    lines = [f"{CURRENCY_FLAG[c]} {c:<3} – {CURRENCY_COUNTRY[c]:<15} | 1 SGD = {rates[c]:>6.2f}" for c in sorted(rates) if c in CURRENCY_COUNTRY and c in CURRENCY_FLAG]
    await update.message.reply_text("💱 Exchange Rates\n\n" + "\n".join(lines) + "\n\nUsage:\n/C 100 SGD JPY")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_not_paused(update): return
    keyword = " ".join(context.args).strip()
    if not keyword: await update.message.reply_text("Usage: /price <item name>\nExample: /price eagle"); return
    if is_japanese(keyword):
        translated = translate_to_english(keyword)
        await send_grouped_results(update, keyword, keywords=[keyword, translated])
    else:
        await send_grouped_results(update, keyword, keyword=keyword)


async def cmd_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.job_queue is None:
        await update.message.reply_text("❌ JobQueue not available. Please ensure python-telegram-bot[job-queue] is installed.")
        return

    # Remove any existing jobs for this chat (eco time-slots + rinkan/delta repeaters)
    for job in context.job_queue.jobs():
        if job.name and job.name.startswith(f"{chat_id}_"):
            job.schedule_removal()

    sgt = pytz.timezone("Asia/Singapore")

    # eaglecapitalone: every 5 min from 6:00pm to 8:00pm SGT
    times = []
    for h in (18, 19):
        for m in range(0, 60, 5):
            times.append(dtime(h, m, tzinfo=sgt))
    times.append(dtime(20, 0, tzinfo=sgt))  # include 8:00pm exactly
    for t in times:
        context.job_queue.run_daily(auto_check_new_arrivals, time=t, chat_id=chat_id, name=f"{chat_id}_eco_{t.hour}_{t.minute}")

    # Rinkan & DELTAone: every 5 min, all day (both pause themselves during 6-8pm)
    context.job_queue.run_repeating(auto_check_rinkan_new, interval=300, first=15, chat_id=chat_id, name=f"{chat_id}_rinkan5min")
    context.job_queue.run_repeating(auto_check_delta_new, interval=300, first=20, chat_id=chat_id, name=f"{chat_id}_delta5min")

    await update.message.reply_text(
        "✅ Notifications enabled!\n"
        "🕕 eaglecapitalone: every 5 min, 6:00-8:00 PM SGT (max 1 alert/day)\n"
        "⏱️ Rinkan: every 5 min, all day (paused 6-8pm)\n"
        "⏱️ DELTAone: every 5 min, all day (paused 6-8pm)\n"
        "👁️ Watchlist also checked on eco runs.\n"
        "Type /notifyoff to disable."
    )
async def cmd_notifyoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if context.job_queue is None:
        await update.message.reply_text("❌ JobQueue not available.")
        return
    removed = 0
    for job in context.job_queue.jobs():
        if job.name and job.name.startswith(f"{chat_id}_"):
            job.schedule_removal()
            removed += 1
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
        "/rinsearch <keyword> [page] — Search Rinkan by category, price-sorted\n"
        "/ecosearch <keyword> [page] — Search eaglecapitalone by category, price-sorted\n"
        "/deltasearch <keyword> — Search DELTAone by category\n\n"
        "👁️ Watchlist:\n"
        "/watch <keyword> [max_price] — Add a watch\n"
        "/unwatch <keyword> — Remove a watch\n"
        "/watchlist — View your active watches\n\n"
        "🔔 Notifications:\n/notify — Auto alert (eco time-slots + Rinkan/DELTAone every 5 min, all day)\n/notifyoff — Disable notifications\n\n"
        "⏸️ Control:\n/stop — Pause/stop a running search\n/resume — Resume search commands\n\n"
        "🕐 Sold History:\n/soldhistory — View sold price history\n/soldonsite wheel sv — Search sold items\n\n"
        "🪶 Goro's Price Search:\n/price <keyword> — Free search\n"
        "/feather /largefeather /wheel /hook /sunmetal /eagle /ring /brace /chain /metal /cross /belt /concho /gold\n\n"
        "🔧 Debug:\n/healthcheck — Status report on all 3 sites\n\n"
        "💰 Deal Finder:\n"
        "/ecodeal [keyword] — Scan eaglecapitalone for items below market avg\n"
        "/rinkandeal [keyword] — Scan Rinkan for items below market avg\n\n"
        "❓ Help:\n/help rinkan — Rinkan search keyword reference\n/help eco — eaglecapitalone search keyword reference\n/help delta — DELTAone search keyword reference\n"
    )
    await update.message.reply_text(msg)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    topic = args[0].lower() if args else ""

    if topic == "rinkan":
        msg = (
            "🔍 Rinkan Search Keywords\n"
            "(for /rinsearch <keyword> and /rinkandeal <keyword>)\n"
            + "─"*30 + "\n\n"
            "🪶 Feathers:\n"
            "feather, large feather\n\n"
            "🪶 Large feather fittings:\n"
            "gold top, silver top, kamikane, kamigane,\n"
            "tip, tip gold, tip silver,\n"
            "turquoise, rope, turquoise rope,\n"
            "gold, silver, old, new, plain, rare, claw\n\n"
            "⚙️ Wheel:\n"
            "wheel (feather-combo items auto-excluded)\n\n"
            "⚙️ Metal:\n"
            "metal, sv sun, gold sun, gold insun, allgold\n\n"
            "🦅 Eagle:\n"
            "eagle\n\n"
            "💍 Jewelry & accessories:\n"
            "ring, bracelet, necklace, belt, concho, bag, wallet\n\n"
            "📄 Paging:\n"
            "/rinsearch <keyword> <page> — e.g. /rinsearch feather 2\n\n"
            "💰 Deal scan:\n"
            "/rinkandeal — scan all categories\n"
            "/rinkandeal <keyword> — scan just one, e.g. /rinkandeal wheel\n\n"
            "ℹ️ If a search comes back empty for something you know exists, "
            "the item's exact Japanese naming may not be mapped yet — "
            "send a screenshot and it can be added."
        )
        await update.message.reply_text(msg)
        return

    if topic == "eco" or topic == "eaglecapitalone":
        msg = (
            "🔍 eaglecapitalone Search Keywords\n"
            "(for /ecosearch <keyword> and /ecodeal <keyword>)\n"
            + "─"*30 + "\n\n"
            "feather, large feather, heart feather, plain feather, used feather, gold tip\n"
            "wheel, hook, eagle, metal, sun metal, gold, claw, sv sun, gold sun, gold insun\n"
            "bracelet, ring, concho, cross, belt, spoon\n\n"
            "📄 Paging:\n"
            "/ecosearch <keyword> <page> — e.g. /ecosearch feather 2\n\n"
            "💰 Deal scan:\n"
            "/ecodeal — scan all categories\n"
            "/ecodeal <keyword> — scan just one, e.g. /ecodeal wheel\n\n"
            "🕐 Sold history (raw, not deal-filtered):\n"
            "/soldonsite <category> <keyword>\n"
            "Categories: wheel, feather, heartfeather, plainfeather, "
            "usedfeather, hook, eagle, metal, brace, ring, concho, cross, belt, spoon\n\n"
            "ℹ️ If a search comes back empty for something you know exists, "
            "the item's exact Japanese naming may not be mapped yet — "
            "send a screenshot and it can be added."
        )
        await update.message.reply_text(msg)
        return

    if topic == "delta" or topic == "deltaone":
        msg = (
            "🔍 DELTAone Search Keywords\n"
            "(for /deltasearch <keyword>)\n"
            + "─"*30 + "\n\n"
            "feather, large feather\n"
            "eagle, eagle ring, feather ring\n"
            "bracelet, leather brace, face bracelet\n"
            "wheel, leather cord, chain\n"
            "sun metal, metal\n"
            "cross, spoon, heart, concho, ring\n"
            "bag, wallet, beads, earring\n"
            "old, rare, very rare, custom, current, sale"
        )
        await update.message.reply_text(msg)
        return

    # Default: no topic or unrecognized topic
    msg = (
        "❓ Help Topics\n" + "─"*30 + "\n\n"
        "/help rinkan — Rinkan search keywords\n"
        "/help eco — eaglecapitalone search keywords\n"
        "/help delta — DELTAone search keywords\n\n"
        "Or type /menu for the full command list."
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
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("neweco", cmd_neweco))
    app.add_handler(CommandHandler("newrinkan", cmd_newrinkan))
    app.add_handler(CommandHandler("newdelta", cmd_newdelta))
    app.add_handler(CommandHandler("rinsearch", cmd_rinkansearch))
    app.add_handler(CommandHandler("ecosearch", cmd_ecosearch))
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
    app.add_handler(CommandHandler("ecodeal", cmd_ecodeal))
    app.add_handler(CommandHandler("rinkandeal", cmd_rinkandeal))

    categories = [
        ("feather","Feather"),("largefeather","Extra Large Feather"),
        ("wheel","Wheel"),("hook","Hook"),("sunmetal","Sun Metal"),
        ("eagle","Eagle"),("ring","Ring"),("brace","Bracelet"),
        ("chain","Chain"),("metal","Metal"),("cross","Cross"),
        ("belt","Belt"),("concho","Concho"),("gold","Gold"),
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
