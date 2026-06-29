import asyncio
import time

import cloudscraper
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ─── Constants ──────────────────────────────────────────────────────
BOT_TOKEN = "8517153660:AAExRG-RKm2SeeZ7xF7JTp8dBWwc0jOYh4U"

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

# ─── Cache ──────────────────────────────────────────────────────────
price_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600
translation_cache = {}


# ─── Helpers ────────────────────────────────────────────────────────
def is_japanese(text):
    return any(
        '\u3000' <= c <= '\u9fff' or
        '\u30a0' <= c <= '\u30ff' or
        '\u3040' <= c <= '\u309f'
        for c in text
    )


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
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("rates", {})
    except Exception as e:
        print(f"Error fetching rates: {e}")
        return {}


def format_price(price_str, sgd_rate):
    try:
        numeric = float(
            price_str.replace("￥", "").replace("¥", "").replace(",", "").strip()
        )
        if sgd_rate:
            sgd_amount = numeric * sgd_rate
            return f"💴 {price_str} ≈ 💵 SGD {sgd_amount:,.2f}"
        return price_str
    except Exception:
        return price_str


def make_scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )


# ─── Scrape Goro's price list ───────────────────────────────────────
def get_goros_prices_grouped():
    if price_cache["data"] and (time.time() - price_cache["timestamp"]) < CACHE_DURATION:
        print("Using cached data")
        return price_cache["data"]

    url = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"
    try:
        scraper = make_scraper()
        print("Visiting homepage first...")
        scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        time.sleep(3)

        print("Fetching price page...")
        response = scraper.get(url, timeout=20)
        print(f"Page status: {response.status_code}")

        if response.status_code != 200:
            return price_cache["data"] or []

        soup = BeautifulSoup(response.text, "html.parser")
        print(f"Tables: {len(soup.find_all('table'))}, Headings: {len(soup.find_all(['h1','h2','h3','h4']))}")

    except Exception as e:
        print(f"Scraper error: {e}")
        return price_cache["data"] or []

    grouped = []
    current_section = "General"
    current_items = []

    for element in soup.find_all(["h1", "h2", "h3", "h4", "table"]):
        if element.name in ["h1", "h2", "h3", "h4"]:
            if current_items:
                grouped.append({"section": current_section, "items": current_items})
                current_items = []
            current_section = translate_to_english(element.get_text(strip=True))
        elif element.name == "table":
            for row in element.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 2:
                    item_jp = cols[0].get_text(strip=True)
                    price   = cols[1].get_text(strip=True)
                    current_items.append({
                        "item_en": translate_to_english(item_jp),
                        "item_jp": item_jp,
                        "price":   price,
                    })

    if current_items:
        grouped.append({"section": current_section, "items": current_items})

    print(f"Total sections: {len(grouped)}")
    if grouped:
        price_cache["data"] = grouped
        price_cache["timestamp"] = time.time()

    return grouped


# ─── Scrape new arrivals ────────────────────────────────────────────
def get_new_arrivals():
    try:
        scraper = make_scraper()
        response = scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        print(f"Homepage status: {response.status_code}")

        if response.status_code != 200:
            return [], ""

        soup = BeautifulSoup(response.text, "html.parser")

        update_date = ""
        new_arrival_section = None
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            text = h.get_text(strip=True)
            if "新着" in text and "入荷" not in text:
                update_date = translate_to_english(text)
                new_arrival_section = h
                print(f"Found heading: {text}")
                break

        if not new_arrival_section:
            return [], ""

        names, prices, imgs = [], [], []

        for sibling in new_arrival_section.find_all_next():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                if "カテゴリ" in sibling.get_text(strip=True):
                    break

            if sibling.name == "a" and sibling.string and len(sibling.string.strip()) > 1:
                names.append(sibling.string.strip())

            if sibling.name == "a":
                img = sibling.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://www.eaglecapitalone.com" + src
                    imgs.append(src)

            if sibling.name == "strong" and sibling.string:
                price = sibling.string.strip()
                if "￥" in price or "¥" in price:
                    prices.append(price)

        print(f"Names: {len(names)}, Prices: {len(prices)}, Images: {len(imgs)}")

        items = []
        for idx in range(min(len(names), len(prices))):
            name_jp = names[idx]
            items.append({
                "name_jp":     name_jp,
                "name_en":     translate_to_english(name_jp) if is_japanese(name_jp) else name_jp,
                "price":       prices[idx],
                "img_url":     imgs[idx] if idx < len(imgs) else None,
                "is_reserved": "専用販売" in name_jp,
            })

        print(f"Total items: {len(items)}")
        return items, update_date

    except Exception as e:
        print(f"New arrivals error: {e}")
        return [], ""


# ─── Shared search helper ────────────────────────────────────────────
async def send_grouped_results(update, title, keywords=None, keyword=None):
    await update.message.reply_text("🔍 Searching... please wait (translation in progress)")

    rates    = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")
    grouped  = get_goros_prices_grouped()
    found_any = False

    for section in grouped:
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
        msg = f"📋 {section['section']}\n{'─' * 30}\n"
        for i in items:
            msg += f"• {i['item_en']}\n  ({i['item_jp']})\n  {format_price(i['price'], sgd_rate)}\n\n"

        for chunk in range(0, len(msg), 4096):
            await update.message.reply_text(msg[chunk:chunk + 4096])

    if not found_any:
        await update.message.reply_text(f"❌ No items found for '{title}'")


# ─── Command handlers ────────────────────────────────────────────────
async def cmd_newarrival(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆕 Fetching new arrivals... please wait")

    rates    = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")
    items, update_date = get_new_arrivals()

    if not items:
        await update.message.reply_text("❌ Could not fetch new arrivals. Try again later.")
        return

    await update.message.reply_text(f"🆕 {update_date}\n{'─' * 30}")

    for idx, i in enumerate(items, 1):
        status  = "🔒 Reserved/Exclusive Sale" if i["is_reserved"] else "✅ Available"
        caption = (
            f"{idx}. {i['name_en']}\n"
            f"({i['name_jp']})\n"
            f"{format_price(i['price'], sgd_rate)}\n"
            f"{status}"
        )
        if i.get("img_url"):
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=i["img_url"],
                    caption=caption,
                )
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)

        await asyncio.sleep(0.5)


async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Testing scraper...")
    try:
        scraper = make_scraper()
        scraper.get("https://www.eaglecapitalone.com/", timeout=15)
        time.sleep(2)

        url      = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"
        response = scraper.get(url, timeout=20)
        soup     = BeautifulSoup(response.text, "html.parser")
        tables   = soup.find_all("table")
        headings = soup.find_all(["h1", "h2", "h3", "h4"])

        msg = (
            f"✅ Page loaded: {response.status_code}\n"
            f"📊 Tables found: {len(tables)}\n"
            f"📝 Headings found: {len(headings)}\n"
        )
        if response.status_code == 429:
            msg += "⚠️ Still rate limited\n"
        elif response.status_code == 200:
            msg += "✅ Connection successful!\n"
        if headings:
            msg += f"\nFirst heading: {headings[0].get_text(strip=True)}"
        if tables:
            first_rows = tables[0].find_all("tr")
            if first_rows:
                cols = first_rows[0].find_all("td")
                if cols:
                    msg += f"\nFirst table row: {cols[0].get_text(strip=True)}"
        if price_cache["data"]:
            age = int((time.time() - price_cache["timestamp"]) / 60)
            msg += f"\n\n💾 Cache: {len(price_cache['data'])} sections, {age} min old"
        else:
            msg += "\n\n💾 Cache: empty"

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args          = context.args
    amount        = 1.0
    from_currency = "SGD"
    to_currency   = "SGD"

    if args:
        try:
            amount = float(args[0])
            if len(args) >= 2:
                from_currency = args[1].upper()
            if len(args) >= 3:
                to_currency = args[2].upper()
        except ValueError:
            from_currency = args[0].upper()
            if len(args) >= 2:
                to_currency = args[1].upper()

    rates = get_rates(base=from_currency)
    if not rates:
        await update.message.reply_text(f"❌ Could not fetch rates for {from_currency}")
        return
    if to_currency not in rates:
        await update.message.reply_text(f"❌ Currency '{to_currency}' not supported.")
        return

    converted = amount * rates[to_currency]
    await update.message.reply_text(
        f"💱 {amount:.2f} {from_currency} ≈ {converted:.2f} {to_currency}\n⚠️ Approximate exchange rate"
    )


async def list_currencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates = get_rates("SGD")
    if not rates:
        await update.message.reply_text("❌ Unable to fetch currency list.")
        return

    lines = [
        f"{CURRENCY_FLAG[cur]} {cur:<3} – {CURRENCY_COUNTRY[cur]:<15} | 1 SGD = {rates[cur]:>6.2f}"
        for cur in sorted(rates.keys())
        if cur in CURRENCY_COUNTRY and cur in CURRENCY_FLAG
    ]
    message = "💱 Exchange Rates\n\n" + "\n".join(lines)
    message += "\n\nUsage:\n/C 100 SGD JPY\n{Convert 'Amount' 'From' 'To'}"
    await update.message.reply_text(message)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text(
            "Usage: /price <item name>\n"
            "Example: /price eagle\n"
            "Japanese also works: /price シルバープレーンホイール"
        )
        return

    if is_japanese(keyword):
        translated = translate_to_english(keyword)
        print(f"Search: '{keyword}' → '{translated}'")
        await send_grouped_results(update, keyword, keywords=[keyword, translated])
    else:
        await send_grouped_results(update, keyword, keyword=keyword)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📋 Available Commands:\n\n"
        "💱 Currency:\n"
        "/C 100 SGD JPY — Convert currency\n"
        "/list — Show all exchange rates\n\n"
        "🆕 New Arrivals:\n"
        "/newarrival — Latest new arrivals with photos\n\n"
        "🪶 Goro's Price Search:\n"
        "/price <keyword> — Free search (English or Japanese)\n"
        "/feather — All feathers\n"
        "/largefeather — Extra large feathers only\n"
        "/wheel — All wheels\n"
        "/hook — All hooks\n"
        "/sunmetal — Sun metals\n"
        "/eagle — Eagles\n"
        "/ring — Rings\n"
        "/brace — Bracelets\n"
        "/chain — Chains\n"
        "/metal — Metals\n"
        "/cross — Crosses\n"
        "/belt — Belts\n"
        "/concho — Conchos\n"
        "/gold — Gold items\n\n"
        "🔧 Debug:\n"
        "/debug — Test scraper connection\n"
    )
    await update.message.reply_text(msg)


# Category command factory — avoids 14 near-identical functions
def make_category_cmd(display_name, keywords_key):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_grouped_results(update, display_name, CATEGORY_KEYWORDS[keywords_key])
    return handler


# ─── Main ────────────────────────────────────────────────────────────
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("C",            convert))
    app.add_handler(CommandHandler("list",          list_currencies))
    app.add_handler(CommandHandler("price",         price))
    app.add_handler(CommandHandler("menu",          menu))
    app.add_handler(CommandHandler("newarrival",    cmd_newarrival))
    app.add_handler(CommandHandler("debug",         cmd_debug))

    categories = [
        ("feather",      "Feather"),
        ("largefeather", "Extra Large Feather"),
        ("wheel",        "Wheel"),
        ("hook",         "Hook"),
        ("sunmetal",     "Sun Metal"),
        ("eagle",        "Eagle"),
        ("ring",         "Ring"),
        ("brace",        "Bracelet"),
        ("chain",        "Chain"),
        ("metal",        "Metal"),
        ("cross",        "Cross"),
        ("belt",         "Belt"),
        ("concho",       "Concho"),
        ("gold",         "Gold"),
    ]
    for key, label in categories:
        app.add_handler(CommandHandler(key, make_category_cmd(label, key)))

    print("Bot started...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
