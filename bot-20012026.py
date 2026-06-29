import asyncio
import json
import os
import re
import time
from datetime import datetime

import cloudscraper
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ─── Constants ──────────────────────────────────────────────────────
BOT_TOKEN = "8517153660:AAExRG-RKm2SeeZ7xF7JTp8dBWwc0jOYh4U"
SOLD_HISTORY_FILE = "sold_history.json"

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

CATEGORY_URLS = {
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

# ─── Cache ──────────────────────────────────────────────────────────
price_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600
translation_cache = {}


# ─── Sold History ───────────────────────────────────────────────────
def load_sold_history():
    if os.path.exists(SOLD_HISTORY_FILE):
        try:
            with open(SOLD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sold_history(history):
    with open(SOLD_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def record_sold_price(name_en, name_jp, price, sold_date):
    history = load_sold_history()
    key = name_en[:40].lower().strip()
    if key not in history:
        history[key] = []

    # Compare date only (first 10 chars = YYYY-MM-DD)
    sold_date_only = sold_date[:10]
    for existing in history[key]:
        if existing["sold_date"][:10] == sold_date_only and existing["price"] == price:
            print(f"Skipping duplicate: {name_en} @ {price} on {sold_date_only}")
            return

    history[key].insert(0, {
        "name_en":   name_en,
        "name_jp":   name_jp,
        "price":     price,
        "sold_date": sold_date
    })
    history[key] = history[key][:5]
    save_sold_history(history)
    print(f"Recorded sold: {name_en} @ {price} on {sold_date}")

def get_sold_history_list(name_en):
    history = load_sold_history()
    key = name_en[:40].lower().strip()
    if key in history and history[key]:
        return history[key]
    return []


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


# ─── Detect category from item name ────────────────────────────────
def detect_category(name_en, name_jp):
    name_lower = name_en.lower() + " " + name_jp.lower()

    # ── Exclude no-category items ──
    if "ヤジリ" in name_jp or "arrowhead" in name_lower:
        return None
    if "グラス" in name_jp or "glass" in name_lower:
        return None
    if "ウニトップ" in name_jp or "uni top" in name_lower:
        return None

    # ── Specific categories FIRST ──

    # Spoon
    if "スプーン" in name_jp or "spoon" in name_lower:
        return "spoon"

    # Heart wheel feather — before wheel and feather
    if "ハートホイールフェザー" in name_jp or "heart wheel feather" in name_lower:
        return "heartfeather"

    # Gold tip feather — 先金
    if "先金" in name_jp or "gold tip" in name_lower or "tip gold" in name_lower:
        return "feather"

    # Plain feather
    if "プレーンフェザー" in name_jp or "plain feather" in name_lower:
        return "plainfeather"

    # Used large feather
    if "中古" in name_jp and "フェザー" in name_jp:
        return "usedfeather"

    # Wheel
    if "ホイール" in name_jp or "wheel" in name_lower:
        return "wheel"

    # General feather
    if "フェザー" in name_jp or "feather" in name_lower:
        return "feather"

    # Hook/chain
    if "フック" in name_jp or "hook" in name_lower or "チェーン" in name_jp or "chain" in name_lower:
        return "hook"

    # Eagle
    if "イーグル" in name_jp or "eagle" in name_lower:
        return "eagle"

    # Metal
    if "メタル" in name_jp or "metal" in name_lower:
        return "metal"

    # Bracelet
    if "ブレス" in name_jp or "bracelet" in name_lower or "brace" in name_lower:
        return "brace"

    # Ring
    if "リング" in name_jp or "ring" in name_lower:
        return "ring"

    # Concho
    if "コンチョ" in name_jp or "concho" in name_lower:
        return "concho"

    # Cross
    if "クロス" in name_jp or "cross" in name_lower:
        return "cross"

    # Belt
    if "ベルト" in name_jp or "belt" in name_lower:
        return "belt"

    return None


# ─── Check item availability ────────────────────────────────────────
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


# ─── Scrape sold items from category page ──────────────────────────
def scrape_sold_from_category(category_key, keywords, min_matches=2):
    url = CATEGORY_URLS.get(category_key)
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
        print(f"Found {len(soldout_positions)} soldout occurrences")

        for pos in soldout_positions:
            chunk = html[max(0, pos - 3000):pos]

            price_matches = re.findall(r'[￥¥][\d,]+', chunk)
            if not price_matches:
                continue
            price_str = price_matches[-1]

            strong_matches = re.findall(r'<strong>(.*?)</strong>', chunk, re.DOTALL)
            name_jp = ""
            for match in reversed(strong_matches):
                clean = re.sub(r'<.*?>', '', match).strip()
                if clean and '￥' not in clean and '¥' not in clean and len(clean) > 2:
                    name_jp = clean
                    break

            if not name_jp or not price_str:
                continue

            # Extract version from image URL
            version_matches = re.findall(r'version/(\d+)/', chunk)
            version = int(version_matches[-1]) if version_matches else 0

            name_en = translate_to_english(name_jp) if is_japanese(name_jp) else name_jp
            name_combined = name_en.lower() + " " + name_jp.lower()

            match_count = sum(1 for kw in keywords if kw.lower() in name_combined)

            if match_count >= min_matches:
                print(f"✅ MATCHED ({match_count}/{min_matches} kw, v={version}): {name_jp} @ {price_str}")
                if not any(s["name_jp"] == name_jp for s in sold_items):
                    sold_items.append({
                        "name_jp": name_jp,
                        "name_en": name_en,
                        "price":   price_str,
                        "version": version,
                    })
            else:
                print(f"❌ Only {match_count}/{min_matches} matches: {name_jp}")

        # Sort by version descending (latest first)
        sold_items.sort(key=lambda x: x["version"], reverse=True)

        print(f"Total sold items found: {len(sold_items)}")
        return sold_items

    except Exception as e:
        print(f"Error scraping category: {e}")
        return []


# ─── Get similar sold prices from website ──────────────────────────
def get_similar_sold_prices(name_en, name_jp, max_results=3):
    category_key = detect_category(name_en, name_jp)
    if not category_key:
        return []

    # ── Extract Japanese base name (remove brackets) ──
    jp_base = re.sub(r'【.*?】', '', name_jp).strip()

    # ── If we have a specific Japanese base, use it as PRIMARY keyword ──
    # This ensures ハートホイールフェザー小 only matches heart wheel feather items
    if jp_base:
        # Use full jp_base as ONE keyword — must contain this exact string
        keywords = [jp_base]
        min_matches = 1  # only need 1 match but it must be the full jp_base
        print(f"Category: {category_key}, Primary JP keyword: '{jp_base}'")
        sold_items = scrape_sold_from_category(category_key, keywords, min_matches=min_matches)

        # If no results with exact JP base, try English keywords as fallback
        if not sold_items:
            stop_words = {
                'the', 'and', 'for', 'with', 'on', 'at', 'in', 'of', 'a', 'an',
                'current', 'latest', 'cast', 'old', 'new', 'good', 'condition',
                'product', 'excellent', 'very', 'rare', 'individual', 'diameter',
                'model', 'size', 'weight', 'right', 'left', 'no', 'super',
                'hobo', 'mint', 'almost', 'barely'
            }
            en_base = re.sub(r'\[.*?\]', '', name_en).strip().lower()
            en_words = [w for w in en_base.split() if len(w) >= 3 and w not in stop_words]
            if en_words:
                print(f"Fallback EN keywords: {en_words}")
                sold_items = scrape_sold_from_category(category_key, en_words, min_matches=2)
    else:
        return []

    return sold_items[:max_results]

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

        names, prices, imgs, product_urls = [], [], [], []

        for sibling in new_arrival_section.find_all_next():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                if "カテゴリ" in sibling.get_text(strip=True):
                    break
            if sibling.name == "a" and sibling.string and len(sibling.string.strip()) > 1:
                name = sibling.string.strip()
                href = sibling.get("href", "")
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://www.eaglecapitalone.com" + href
                names.append(name)
                product_urls.append(href)
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

        print(f"Names: {len(names)}, Prices: {len(prices)}, Images: {len(imgs)}, URLs: {len(product_urls)}")

        items = []
        for idx in range(min(len(names), len(prices))):
            name_jp = names[idx]
            items.append({
                "name_jp":     name_jp,
                "name_en":     translate_to_english(name_jp) if is_japanese(name_jp) else name_jp,
                "price":       prices[idx],
                "img_url":     imgs[idx] if idx < len(imgs) else None,
                "product_url": product_urls[idx] if idx < len(product_urls) else None,
                "is_reserved": "専用販売" in name_jp,
            })

        print(f"Total items: {len(items)}")
        return items, update_date

    except Exception as e:
        print(f"New arrivals error: {e}")
        return [], ""


# ─── Shared search helper ───────────────────────────────────────────
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


# ─── /new command (new arrivals) ────────────────────────────────────
async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆕 Fetching new arrivals... please wait\n"
        "⚠️ Checking availability and sold prices, this may take a moment"
    )

    rates    = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")

    items, update_date = get_new_arrivals()

    if not items:
        await update.message.reply_text("❌ Could not fetch new arrivals. Try again later.")
        return

    await update.message.reply_text(f"🆕 {update_date}\n{'─' * 30}")

    scraper = make_scraper()

    for idx, i in enumerate(items, 1):
        price_line = format_price(i["price"], sgd_rate)

        if i.get("is_reserved"):
            availability  = "🔒 Reserved/Exclusive Sale"
            previous_history = []
            site_sold     = []

        elif i.get("product_url"):
            # ── Get previous history BEFORE checking ──
            previous_history = get_sold_history_list(i["name_en"])

            # ── Check availability ──
            availability = check_item_availability(scraper, i["product_url"])
            time.sleep(1)

            # ── Record if sold out ──
            if availability == "❌ Sold Out":
                sold_date = datetime.now().strftime("%Y-%m-%d %H:%M")
                record_sold_price(
                    i["name_en"],
                    i["name_jp"],
                    i["price"],
                    sold_date
                )

            # ── Get similar sold prices from website (latest first) ──
            site_sold = get_similar_sold_prices(i["name_en"], i["name_jp"])
            time.sleep(1)

        else:
            availability     = "❓ Unknown"
            previous_history = []
            site_sold        = []

        # ── Build caption ──
        caption = (
            f"{idx}. {i['name_en']}\n"
            f"({i['name_jp']})\n"
            f"{price_line}\n"
            f"{availability}"
        )

        # ── Show similar sold prices from website sorted latest first ──
        if site_sold:
            caption += "\n\n📊 Similar sold on site (latest first):"
            for s in site_sold:
                caption += f"\n  • {s['name_en']}"
                caption += f"\n    {format_price(s['price'], sgd_rate)}"

        # ── Show bot's own previous history ──
        if availability == "❌ Sold Out" and previous_history:
            caption += "\n\n🕐 Previously recorded:"
            for record in previous_history[:3]:
                caption += f"\n  • {record['price']} on {record['sold_date']}"

        # ── Send photo or text ──
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

        time.sleep(0.5)


# ─── /soldhistory command ───────────────────────────────────────────
async def cmd_soldhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = " ".join(context.args).strip()
    history = load_sold_history()

    if not history:
        await update.message.reply_text(
            "📭 No sold history recorded yet.\n"
            "History builds up as items are checked via /new."
        )
        return

    if keyword:
        results = {k: v for k, v in history.items() if keyword.lower() in k}
        if not results:
            await update.message.reply_text(f"❌ No sold history found for '{keyword}'")
            return
    else:
        results = history

    rates    = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")

    msg = "🕐 Sold Price History\n" + "─" * 30 + "\n\n"
    for key, records in list(results.items())[:20]:
        for r in records[:3]:
            msg += f"• {r['name_en']}\n"
            msg += f"  ({r['name_jp']})\n"
            msg += f"  {format_price(r['price'], sgd_rate)} — sold {r['sold_date']}\n\n"

    if len(msg) > 4096:
        for x in range(0, len(msg), 4096):
            await update.message.reply_text(msg[x:x+4096])
    else:
        await update.message.reply_text(msg)


# ─── /soldonsite command ────────────────────────────────────────────
async def cmd_soldonsite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = " ".join(context.args).strip()
    if not args:
        await update.message.reply_text(
            "Usage: /soldonsite <category> <keyword>\n"
            "Example: /soldonsite wheel sv\n"
            "Categories: wheel, feather, hook, eagle, metal, brace, ring, concho, cross, belt"
        )
        return

    parts = args.split()
    category_key = parts[0].lower()
    search_keywords = parts[1:] if len(parts) > 1 else parts

    if category_key not in CATEGORY_URLS:
        await update.message.reply_text(
            "❌ Category not found. Use one of:\n"
            "wheel, feather, hook, eagle, metal, brace, ring, concho, cross, belt"
        )
        return

    await update.message.reply_text(f"🔍 Searching sold items on website for '{args}'... please wait")

    sold_items = scrape_sold_from_category(category_key, search_keywords)

    if not sold_items:
        await update.message.reply_text(f"❌ No sold items found for '{args}'")
        return

    rates    = get_rates(base="JPY")
    sgd_rate = rates.get("SGD")

    msg = f"❌ Sold items on website matching '{args}':\n{'─' * 30}\n\n"
    for i in sold_items:
        msg += f"• {i['name_en']}\n"
        msg += f"  ({i['name_jp']})\n"
        msg += f"  {format_price(i['price'], sgd_rate)}\n\n"

    if len(msg) > 4096:
        for x in range(0, len(msg), 4096):
            await update.message.reply_text(msg[x:x+4096])
    else:
        await update.message.reply_text(msg)


# ─── /debug command ─────────────────────────────────────────────────
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

        history = load_sold_history()
        msg += f"\n📦 Sold history: {len(history)} items tracked"

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ─── /C command ─────────────────────────────────────────────────────
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


# ─── /list command ──────────────────────────────────────────────────
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
        translated = translate_to_english(keyword)
        print(f"Search: '{keyword}' → '{translated}'")
        await send_grouped_results(update, keyword, keywords=[keyword, translated])
    else:
        await send_grouped_results(update, keyword, keyword=keyword)


# ─── /menu command ──────────────────────────────────────────────────
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📋 Available Commands:\n\n"
        "💱 Currency:\n"
        "/C 100 SGD JPY — Convert currency\n"
        "/list — Show all exchange rates\n\n"
        "🆕 New Arrivals:\n"
        "/new — Latest new arrivals with photos + availability\n\n"
        "🕐 Sold History:\n"
        "/soldhistory — View all sold price history\n"
        "/soldhistory wheel — Search sold history by keyword\n"
        "/soldonsite wheel sv — Search sold items on website\n\n"
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


# ─── Category command factory ────────────────────────────────────────
def make_category_cmd(display_name, keywords_key):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_grouped_results(update, display_name, CATEGORY_KEYWORDS[keywords_key])
    return handler


# ─── Main ────────────────────────────────────────────────────────────
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("C",           convert))
    app.add_handler(CommandHandler("list",        list_currencies))
    app.add_handler(CommandHandler("price",       price))
    app.add_handler(CommandHandler("menu",        menu))
    app.add_handler(CommandHandler("new",         cmd_new))
    app.add_handler(CommandHandler("soldhistory", cmd_soldhistory))
    app.add_handler(CommandHandler("soldonsite",  cmd_soldonsite))
    app.add_handler(CommandHandler("debug",       cmd_debug))

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
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
