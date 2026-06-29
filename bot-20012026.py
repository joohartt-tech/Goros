import cloudscraper
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

CURRENCY_COUNTRY = {
    "SGD": "Singapore",
    "JPY": "Japan",
    "CNY": "China",
    "MYR": "Malaysia",
    "USD": "United States",
    "EUR": "Eurozone",
    "GBP": "United Kingdom",
    "AUD": "Australia",
    "NZD": "New Zealand",
    "HKD": "Hong Kong",
    "KRW": "South Korea",
    "THB": "Thailand",
    "IDR": "Indonesia",
    "PHP": "Philippines",
    "INR": "India",
    "CAD": "Canada",
    "CHF": "Switzerland"
}

CURRENCY_FLAG = {
    "SGD": "🇸🇬",
    "JPY": "🇯🇵",
    "CNY": "🇨🇳",
    "MYR": "🇲🇾",
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "AUD": "🇦🇺",
    "NZD": "🇳🇿",
    "HKD": "🇭🇰",
    "KRW": "🇰🇷",
    "THB": "🇹🇭",
    "IDR": "🇮🇩",
    "PHP": "🇵🇭",
    "INR": "🇮🇳",
    "CAD": "🇨🇦",
    "CHF": "🇨🇭"
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

BOT_TOKEN = "8517153660:AAExRG-RKm2SeeZ7xF7JTp8dBWwc0jOYh4U"

# ─── Cache ──────────────────────────────────────────────────────────
price_cache = {
    "data": None,
    "timestamp": 0
}
CACHE_DURATION = 3600

# ─── Translation cache ──────────────────────────────────────────────
translation_cache = {}

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
    except:
        return text

# ─── Fetch exchange rates ───────────────────────────────────────────
def get_rates(base="SGD"):
    import requests
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("rates", {})
    except Exception as e:
        print("Error fetching rates:", e)
        return {}

# ─── Scrape Goro's price list ───────────────────────────────────────
def get_goros_prices_grouped():
    if price_cache["data"] and (time.time() - price_cache["timestamp"]) < CACHE_DURATION:
        print("Using cached data")
        return price_cache["data"]

    url = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"

    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        print("Visiting homepage first...")
        scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        time.sleep(3)

        print("Fetching price page...")
        response = scraper.get(url, timeout=20)
        print(f"Page status: {response.status_code}")

        if response.status_code != 200:
            return price_cache["data"] or []

        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        headings = soup.find_all(["h1", "h2", "h3", "h4"])
        print(f"Tables: {len(tables)}, Headings: {len(headings)}")

    except Exception as e:
        print(f"Error: {e}")
        return price_cache["data"] or []

    grouped = []
    current_section = "General"
    current_items = []

    for element in soup.find_all(["h1", "h2", "h3", "h4", "table"]):
        if element.name in ["h1", "h2", "h3", "h4"]:
            if current_items:
                grouped.append({"section": current_section, "items": current_items})
                current_items = []
            raw_heading = element.get_text(strip=True)
            current_section = translate_to_english(raw_heading)
        elif element.name == "table":
            rows = element.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) == 2:
                    item_jp = cols[0].get_text(strip=True)
                    price   = cols[1].get_text(strip=True)
                    item_en = translate_to_english(item_jp)
                    current_items.append({
                        "item_en": item_en,
                        "item_jp": item_jp,
                        "price":   price
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
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        response = scraper.get("https://www.eaglecapitalone.com/", timeout=20)
        print(f"Homepage status: {response.status_code}")

        if response.status_code != 200:
            return [], ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Find new arrivals heading
        update_date = ""
        new_arrival_section = None
        for h in soup.find_all(["h1", "h2", "h3", "h4"]):
            text = h.get_text(strip=True)
            if "新着" in text and "入荷" not in text:
                update_date = translate_to_english(text)
                new_arrival_section = h
                print(f"Found: {text}")
                break

        if not new_arrival_section:
            return [], ""

        # Collect name+price pairs using [a] and [strong] pattern
        names = []
        prices = []
        imgs = []

        for sibling in new_arrival_section.find_all_next():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                if "カテゴリ" in sibling.get_text(strip=True):
                    break

            # Collect product names from <a> tags
            if sibling.name == "a" and sibling.string and sibling.string.strip():
                name = sibling.string.strip()
                if len(name) > 1:
                    names.append(name)

            # Collect images from <a> tags containing <img>
            if sibling.name == "a":
                img = sibling.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://www.eaglecapitalone.com" + src
                    imgs.append(src)

            # Collect prices from <strong> tags
            if sibling.name == "strong" and sibling.string:
                price = sibling.string.strip()
                if "￥" in price or "¥" in price:
                    prices.append(price)

        print(f"Names: {len(names)}, Prices: {len(prices)}, Images: {len(imgs)}")

        # Build items by pairing name + price + image
        items = []
        for idx in range(min(len(names), len(prices))):
            name_jp = names[idx]
            price_str = prices[idx]
            img_url = imgs[idx] if idx < len(imgs) else None

            # Check if reserved/exclusive sale
            is_reserved = "専用販売" in name_jp
            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp

            items.append({
                "name_jp":     name_jp,
                "name_en":     name_en,
                "price":       price_str,
                "img_url":     img_url,
                "is_reserved": is_reserved
            })

        print(f"Total items: {len(items)}")
        return items, update_date

    except Exception as e:
        print(f"Error: {e}")
        return [], ""

# ─── Format price ───────────────────────────────────────────────────
def format_price(price_str, sgd_rate):
    try:
        numeric = float(
            price_str.replace("￥", "").replace("¥", "").replace(",", "").strip()
        )
        if sgd_rate:
            sgd_amount = numeric * sgd_rate
            return f"💴 {price_str} ≈ 💵 SGD {sgd_amount:,.2f}"
        return price_str
    except:
        return price_str

# ─── Send grouped results ───────────────────────────────────────────
async def send_grouped_results(update, title, keywords=None, keyword=None):
    await update.message.reply_text("🔍 Searching... please wait (translation in progress)")

    rates = get_rates(base="JPY")
    sgd_rate = rates.get("SGD", None)

    grouped = get_goros_prices_grouped()
    found_any = False

    for section in grouped:
        if keywords:
            section_match = any(kw.lower() in section["section"].lower() for kw in keywords)
            if section_match:
                items = section["items"]
            else:
                items = [
                    i for i in section["items"]
                    if any(kw.lower() in i["item_en"].lower() or
                           kw in i["item_jp"]
                           for kw in keywords)
                ]
        elif keyword:
            section_match = keyword.lower() in section["section"].lower()
            if section_match:
                items = section["items"]
            else:
                items = [
                    i for i in section["items"]
                    if keyword.lower() in i["item_en"].lower() or
                       keyword.lower() in i["item_jp"].lower()
                ]
        else:
            items = section["items"]

        if not items:
            continue

        found_any = True

        msg = f"📋 {section['section']}\n"
        msg += "─" * 30 + "\n"
        for i in items:
            msg += f"• {i['item_en']}\n"
            msg += f"  ({i['item_jp']})\n"
            msg += f"  {format_price(i['price'], sgd_rate)}\n\n"

        if len(msg) > 4096:
            for x in range(0, len(msg), 4096):
                await update.message.reply_text(msg[x:x+4096])
        else:
            await update.message.reply_text(msg)

    if not found_any:
        await update.message.reply_text(f"❌ No items found for '{title}'")

# ─── /newarrival command ────────────────────────────────────────────
async def cmd_newarrival(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆕 Fetching new arrivals... please wait")

    rates = get_rates(base="JPY")
    sgd_rate = rates.get("SGD", None)

    items, update_date = get_new_arrivals()

    if not items:
        await update.message.reply_text("❌ Could not fetch new arrivals. Try again later.")
        return

    await update.message.reply_text(f"🆕 {update_date}\n{'─' * 30}")

    for idx, i in enumerate(items, 1):
        price_line = format_price(i["price"], sgd_rate)

        # Show reserved/exclusive sale status
        if i["is_reserved"]:
            status = "🔒 Reserved/Exclusive Sale"
        else:
            status = "✅ Available"

        caption = (
            f"{idx}. {i['name_en']}\n"
            f"({i['name_jp']})\n"
            f"{price_line}\n"
            f"{status}"
        )

        if i.get("img_url"):
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=i["img_url"],
                    caption=caption
                )
            except Exception as e:
                print(f"Photo failed: {e}")
                await update.message.reply_text(caption)
        else:
            await update.message.reply_text(caption)

        import asyncio
        await asyncio.sleep(0.5)

# ─── /debug command ─────────────────────────────────────────────────
async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Testing scraper...")
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        scraper.get("https://www.eaglecapitalone.com/", timeout=15)
        time.sleep(2)

        url = "https://www.eaglecapitalone.com/goros-kaitorikakakuhyo/"
        response = scraper.get(url, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        headings = soup.find_all(["h1", "h2", "h3", "h4"])

        msg = f"✅ Page loaded: {response.status_code}\n"
        msg += f"📊 Tables found: {len(tables)}\n"
        msg += f"📝 Headings found: {len(headings)}\n\n"

        if response.status_code == 429:
            msg += "⚠️ Still rate limited\n"
        elif response.status_code == 200:
            msg += "✅ Connection successful!\n"

        if headings:
            msg += f"First heading: {headings[0].get_text(strip=True)}\n"
        if tables:
            first_rows = tables[0].find_all("tr")
            if first_rows:
                cols = first_rows[0].find_all("td")
                if cols:
                    msg += f"First table row: {cols[0].get_text(strip=True)}"

        if price_cache["data"]:
            age = int((time.time() - price_cache["timestamp"]) / 60)
            msg += f"\n\n💾 Cache: {len(price_cache['data'])} sections, {age} min old"
        else:
            msg += "\n\n💾 Cache: empty"

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ─── /C command ─────────────────────────────────────────────────────
async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = 1
    from_currency = "SGD"
    to_currency = "SGD"
    args = context.args

    if len(args) >= 1:
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
            amount = 1

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

# ─── /list command ──────────────────────────────────────────────────
async def list_currencies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rates = get_rates("SGD")
    if not rates:
        await update.message.reply_text("❌ Unable to fetch currency list.")
        return

    lines = []
    for cur in sorted(rates.keys()):
        if cur in CURRENCY_COUNTRY and cur in CURRENCY_FLAG:
            rate = rates[cur]
            line = (
                f"{CURRENCY_FLAG[cur]} "
                f"{cur:<3} – {CURRENCY_COUNTRY[cur]:<15} | "
                f"1 SGD = {rate:>6.2f}"
            )
            lines.append(line)

    message = "💱 Exchange Rates\n\n"
    message += "\n".join(lines) + "\n"
    message += "\nUsage:\n/C 100 SGD JPY\n{Convert 'Amount' 'From' 'To'}"
    await update.message.reply_text(message)

# ─── /price command ─────────────────────────────────────────────────
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
        translated_keyword = translate_to_english(keyword)
        print(f"Search: '{keyword}' → translated: '{translated_keyword}'")
        await send_grouped_results(update, keyword, keywords=[keyword, translated_keyword])
    else:
        await send_grouped_results(update, keyword, keyword=keyword)

# ─── Category commands ──────────────────────────────────────────────
async def cmd_feather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Feather", CATEGORY_KEYWORDS["feather"])

async def cmd_largefeather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Extra Large Feather", CATEGORY_KEYWORDS["largefeather"])

async def cmd_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Wheel", CATEGORY_KEYWORDS["wheel"])

async def cmd_hook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Hook", CATEGORY_KEYWORDS["hook"])

async def cmd_sunmetal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Sun Metal", CATEGORY_KEYWORDS["sunmetal"])

async def cmd_eagle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Eagle", CATEGORY_KEYWORDS["eagle"])

async def cmd_ring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Ring", CATEGORY_KEYWORDS["ring"])

async def cmd_brace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Bracelet", CATEGORY_KEYWORDS["brace"])

async def cmd_chain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Chain", CATEGORY_KEYWORDS["chain"])

async def cmd_metal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Metal", CATEGORY_KEYWORDS["metal"])

async def cmd_cross(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Cross", CATEGORY_KEYWORDS["cross"])

async def cmd_belt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Belt", CATEGORY_KEYWORDS["belt"])

async def cmd_concho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Concho", CATEGORY_KEYWORDS["concho"])

async def cmd_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_grouped_results(update, "Gold", CATEGORY_KEYWORDS["gold"])

# ─── /menu command ──────────────────────────────────────────────────
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

# ─── Bot setup ──────────────────────────────────────────────────────
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("C", convert))
app.add_handler(CommandHandler("list", list_currencies))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("newarrival", cmd_newarrival))
app.add_handler(CommandHandler("debug", cmd_debug))
app.add_handler(CommandHandler("feather", cmd_feather))
app.add_handler(CommandHandler("largefeather", cmd_largefeather))
app.add_handler(CommandHandler("wheel", cmd_wheel))
app.add_handler(CommandHandler("hook", cmd_hook))
app.add_handler(CommandHandler("sunmetal", cmd_sunmetal))
app.add_handler(CommandHandler("eagle", cmd_eagle))
app.add_handler(CommandHandler("ring", cmd_ring))
app.add_handler(CommandHandler("brace", cmd_brace))
app.add_handler(CommandHandler("chain", cmd_chain))
app.add_handler(CommandHandler("metal", cmd_metal))
app.add_handler(CommandHandler("cross", cmd_cross))
app.add_handler(CommandHandler("belt", cmd_belt))
app.add_handler(CommandHandler("concho", cmd_concho))
app.add_handler(CommandHandler("gold", cmd_gold))

print("Bot is running...")
app.run_polling()
