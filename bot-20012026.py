import os
import cloudscraper
import time
import asyncio
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# ─── LOGGING ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ─── BOT TOKEN (FIXED FOR RENDER) ────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

# ─── DATA ────────────────────────────────────────────────
CURRENCY_COUNTRY = {
    "SGD": "Singapore", "JPY": "Japan", "CNY": "China", "MYR": "Malaysia",
    "USD": "United States", "EUR": "Eurozone", "GBP": "United Kingdom",
    "AUD": "Australia", "NZD": "New Zealand", "HKD": "Hong Kong",
    "KRW": "South Korea", "THB": "Thailand", "IDR": "Indonesia",
    "PHP": "Philippines", "INR": "India", "CAD": "Canada", "CHF": "Switzerland"
}

CURRENCY_FLAG = {
    "SGD": "🇸🇬", "JPY": "🇯🇵", "CNY": "🇨🇳", "MYR": "🇲🇾",
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "AUD": "🇦🇺",
    "NZD": "🇳🇿", "HKD": "🇭🇰", "KRW": "🇰🇷", "THB": "🇹🇭",
    "IDR": "🇮🇩", "PHP": "🇵🇭", "INR": "🇮🇳", "CAD": "🇨🇦", "CHF": "🇨🇭"
}

CATEGORY_KEYWORDS = {
    "feather": ["feather", "フェザー"],
    "wheel": ["wheel", "ホイール"],
    "hook": ["hook", "フック"],
    "sunmetal": ["sun metal", "太陽メタル"],
    "eagle": ["eagle", "イーグル"],
    "ring": ["ring", "リング"],
    "brace": ["bracelet", "brace", "ブレス"],
    "chain": ["chain", "チェーン"],
    "metal": ["metal", "メタル"],
    "cross": ["cross", "クロス"],
    "belt": ["belt", "ベルト"],
    "concho": ["concho", "コンチョ"],
    "gold": ["gold", "ゴールド", "金"]
}

# ─── CACHE ───────────────────────────────────────────────
price_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600

translation_cache = {}

# ─── UTIL ────────────────────────────────────────────────
def is_japanese(text):
    return any('\u3000' <= c <= '\u9fff' or '\u30a0' <= c <= '\u30ff' for c in text)

def translate(text):
    if text in translation_cache:
        return translation_cache[text]
    try:
        result = GoogleTranslator(source='ja', target='en').translate(text)
        translation_cache[text] = result
        return result
    except:
        return text

# ─── RATES ───────────────────────────────────────────────
def get_rates(base="SGD"):
    import requests
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=10)
        return r.json().get("rates", {})
    except:
        return {}

# ─── SCRAPER ─────────────────────────────────────────────
def get_prices():
    if price_cache["data"] and time.time() - price_cache["timestamp"] < CACHE_DURATION:
        return price_cache["data"]

    url = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"
    scraper = cloudscraper.create_scraper()

    try:
        scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        time.sleep(2)

        res = scraper.get(url, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")

    except Exception as e:
        logging.error(e)
        return price_cache["data"] or []

    grouped = []
    section = "General"
    items = []

    for el in soup.find_all(["h1", "h2", "h3", "h4", "table"]):
        if el.name in ["h1", "h2", "h3", "h4"]:
            if items:
                grouped.append({"section": section, "items": items})
                items = []
            section = translate(el.text.strip())

        elif el.name == "table":
            for row in el.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 2:
                    items.append({
                        "item_en": translate(cols[0].text.strip()),
                        "item_jp": cols[0].text.strip(),
                        "price": cols[1].text.strip()
                    })

    if items:
        grouped.append({"section": section, "items": items})

    price_cache["data"] = grouped
    price_cache["timestamp"] = time.time()

    return grouped

# ─── COMMANDS ────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running ✅")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = " ".join(context.args)
    data = get_prices()

    msg = ""
    for sec in data:
        for i in sec["items"]:
            if kw.lower() in i["item_en"].lower() or kw in i["item_jp"]:
                msg += f"{i['item_en']} ({i['item_jp']}) - {i['price']}\n"

    await update.message.reply_text(msg or "Not found")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commands: /price, /menu")

# ─── APP SETUP ───────────────────────────────────────────
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("menu", menu))

# ─── SAFE START ──────────────────────────────────────────
if __name__ == "__main__":
    print("Bot starting...")
    try:
        app.run_polling()
    except Exception as e:
        print("CRASH:", e)
