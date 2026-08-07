import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
MENU_PATH = BASE_DIR / "august_menu_fixed_table.json"
DATA_DIR = Path(
    os.environ.get("DATA_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or BASE_DIR
)
DB_PATH = DATA_DIR / "meal_order_reports.sqlite3"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8787"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "ofa5153")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "585858")
ADMIN_SESSION_SECRET = os.environ.get("ADMIN_SESSION_SECRET", ADMIN_PASSWORD)
ADMIN_COOKIE = "ofa_admin_session"
ADMIN_SESSION_TTL_SECONDS = 60 * 60 * 12
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "")
TELEGRAM_MANAGER_USER_IDS = {
    value.strip()
    for value in os.environ.get("TELEGRAM_MANAGER_USER_IDS", "").split(",")
    if value.strip()
}
TELEGRAM_MANAGER_USERNAMES = {
    value.strip().lstrip("@").lower()
    for value in os.environ.get("TELEGRAM_MANAGER_USERNAMES", "").split(",")
    if value.strip()
}
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
BOT_CONFIRM_TTL_SECONDS = 60 * 30
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_FORMAT = os.environ.get("OPENAI_IMAGE_FORMAT", "webp")
OPENAI_IMAGE_QUALITY = os.environ.get("OPENAI_IMAGE_QUALITY", "low")
OPENAI_IMAGE_VERSION = os.environ.get("OPENAI_IMAGE_VERSION", "gpt-photo-low-1")
DISH_IMAGE_DIR = DATA_DIR / "dish_images"
APP_URL = "https://web-production-664d8.up.railway.app"
ADMIN_URL = f"{APP_URL}/admin"
MINI_APP_URL = f"{APP_URL}/?v=20260807-typo2"
KHMER_USAGE_ANNOUNCEMENT = """សេចក្តីជូនដំណឹងពីផ្ទះបាយ OFA

របៀបប្រើ Kitchen Bot៖

1. បើក Chat ជាមួយ Kitchen Bot ហើយចុច /start

2. មើលមុខម្ហូបថ្ងៃនេះ
ចុច「今日菜單」ឬវាយ៖ 今日菜單

3. មើលតារាងដឹកអាហារ
ចុច「送餐總表」ឬវាយ៖ 總表

4. មើលចំនួនសរុប
ចុច「送餐總數」ឬវាយ៖ 總數

5. រាយការណ៍ចំនួនអាហារ
ចុច「人數回報」បន្ទាប់មកបិទភ្ជាប់អត្ថបទរាយការណ៍។
បើទិន្នន័យត្រឹមត្រូវ សូមឆ្លើយ៖ 確認

សម្គាល់៖
បុគ្គលិកទូទៅប្រើ「今日菜單」「送餐總表」「送餐總數」។
「人數回報」និង「每日菜金」ត្រូវការសិទ្ធិអ្នកគ្រប់គ្រង។"""


def storage_status():
    volume_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    explicit_data_dir = os.environ.get("DATA_DIR")
    is_persistent = bool(volume_path or explicit_data_dir)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        writable = os.access(DATA_DIR, os.W_OK)
    except Exception:
        writable = False
    return {
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
        "persistent": is_persistent,
        "writable": writable,
        "source": "RAILWAY_VOLUME_MOUNT_PATH" if volume_path else ("DATA_DIR" if explicit_data_dir else "app filesystem"),
        "warning": "" if is_persistent else "尚未掛載 Railway Volume，部署後資料可能會消失。",
    }

DEPARTMENTS = ["1001", "1002-2\u4ee3\u7406", "1002-3\u91d1\u6d41", "3F", "\u4fdd\u59c6\u90e8\u9580", "\u6d77\u5357\u96de\u98ef", "1002-2\u5ba2\u670d", "\u6a02\u53f0\u98f2\u6599\u5e97"]
HIDDEN_FIXED_UNITS = ["\u5eda\u623f\u54e1\u5de5"]
FIXED_REPORT_UNITS = DEPARTMENTS + HIDDEN_FIXED_UNITS
DELIVERY_LOCATIONS = [
    "\u90e8\u9580\u73fe\u5834",
    "1002-2",
    "68",
    "88",
    "3F",
    "3F\u5305\u9910\u76d2",
    "\u4e0d\u5403\u725b",
    "\u4e0d\u5403\u8c6c",
    "\u4e0d\u5403\u6d77\u9bae",
]
MEAL_KEYS = ["breakfast", "lunch", "dinner", "late_night"]
MEAL_PRICES = {
    "breakfast": 1.5,
    "lunch": 2.0,
    "dinner": 3.5,
    "late_night": 3.0,
}
DEFAULT_MONTHLY_STAFF = [
    {"name": "\u609f", "role": "\u53f0\u7c4d\u5eda\u5e2b", "amount": 3750},
    {"name": "\u5764", "role": "\u53f0\u7c4d\u5eda\u5e2b", "amount": 3750},
    {"name": "PICH", "role": "\u67ec\u7c4d\u5eda\u5e2b", "amount": 550},
    {"name": "\u963fP", "role": "\u67ec\u7c4d\u5eda\u5e2b", "amount": 500},
    {"name": "\u82ad\u6a02", "role": "\u5eda\u5de5", "amount": 300},
    {"name": "LIN", "role": "\u5eda\u5de5", "amount": 300},
    {"name": "\u963f\u5927", "role": "\u5eda\u5de5", "amount": 300},
    {"name": "ALIN", "role": "\u5eda\u5de5", "amount": 300},
    {"name": "\u9e97\u5361", "role": "\u5eda\u5de5", "amount": 300},
    {"name": "\u963f\u6885", "role": "\u5eda\u5de5", "amount": 300},
]
CUISINES = ["taiwan", "healthy", "cambodia"]
COST_FIELD_LABELS = {
    "pork_cost": "\u8c6c\u8089\u5546",
    "vegetable_cost": "\u9752\u83dc\u5546",
    "frozen_cost": "\u51b7\u51cd\u5546",
    "cambodia_cost": "\u67ec\u9910",
    "grocery_cost": "\u96dc\u8ca8",
    "gas_cost": "\u74e6\u65af",
    "water_cost": "\u6c34",
    "meal_box_cost": "\u9910\u76d2",
    "corner_store_cost": "\u67d1\u4ed4\u5e97",
    "rice_cost": "\u5927\u7c73",
    "ice_cost": "\u51b0\u584a",
    "cost_68": "68",
}
COST_MENU_ROWS = [
    ["pork_cost", "vegetable_cost", "frozen_cost"],
    ["cambodia_cost"],
    ["grocery_cost", "gas_cost", "water_cost"],
    ["meal_box_cost", "corner_store_cost", "rice_cost", "ice_cost"],
    ["cost_68"],
]
FIXED_REPORTS = [
    {
        "unit": "1001",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "taiwan",
        "counts": {"breakfast": 10, "lunch": 40, "dinner": 40, "late_night": 40},
        "beef_notes": {"lunch": 10, "dinner": 10, "late_night": 10},
    },
    {
        "unit": "1002-2\u4ee3\u7406",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "taiwan",
        "counts": {"lunch": 1, "dinner": 6, "late_night": 6},
    },
    {
        "unit": "1002-2\u4ee3\u7406",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "cambodia",
        "counts": {"lunch": 1, "dinner": 1, "late_night": 1},
    },
    {
        "unit": "1002-3\u91d1\u6d41",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "taiwan",
        "counts": {"breakfast": 3, "lunch": 5, "dinner": 5, "late_night": 5},
        "beef_notes": {"lunch": 2, "dinner": 2, "late_night": 2},
    },
    {
        "unit": "1002-2\u5ba2\u670d",
        "location": "1002-2",
        "cuisine": "taiwan",
        "counts": {"breakfast": 9, "lunch": 1, "dinner": 3, "late_night": 4},
    },
    {
        "unit": "1002-2\u5ba2\u670d",
        "location": "1002-2",
        "cuisine": "cambodia",
        "counts": {"lunch": 4, "dinner": 4, "late_night": 7},
    },
    {
        "unit": "\u4fdd\u59c6\u90e8\u9580",
        "location": "68",
        "cuisine": "cambodia",
        "counts": {"breakfast": 2, "lunch": 3, "dinner": 3, "late_night": 1},
    },
    {
        "unit": "\u4fdd\u59c6\u90e8\u9580",
        "location": "88",
        "cuisine": "cambodia",
        "counts": {"breakfast": 3, "lunch": 4, "dinner": 4, "late_night": 4},
    },
    {
        "unit": "\u6d77\u5357\u96de\u98ef",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "cambodia",
        "counts": {"breakfast": 3, "lunch": 5, "dinner": 5, "late_night": 5},
    },
    {
        "unit": "\u5eda\u623f\u54e1\u5de5",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "cambodia",
        "counts": {"breakfast": 10, "lunch": 10, "dinner": 10},
    },
]


def allowed_delivery_locations(unit):
    if unit == "3F":
        return DELIVERY_LOCATIONS[2:]
    if unit == "\u4fdd\u59c6\u90e8\u9580":
        return ["68", "88"]
    if unit == "1002-2\u5ba2\u670d":
        return ["1002-2"]
    return [DELIVERY_LOCATIONS[0]]


def unit_delivery_locations():
    return {unit: allowed_delivery_locations(unit) for unit in DEPARTMENTS}


def load_menu():
    menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    return apply_menu_overrides(menu)


def load_base_menu():
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def menu_override_rows():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT report_date, meal_key, old_dish, new_dish, item_index, category, updated_at
            FROM menu_overrides
            ORDER BY updated_at, id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def apply_menu_overrides(menu):
    try:
        rows = menu_override_rows()
    except Exception:
        rows = []
    for row in rows:
        day = menu.get(row["report_date"])
        if not day:
            continue
        for meal in day.get("meals", []):
            if meal.get("key") != row["meal_key"]:
                continue
            items = meal.get("items", [])
            item_index = row.get("item_index")
            if item_index is not None:
                try:
                    index = int(item_index)
                except (TypeError, ValueError):
                    continue
                if 0 <= index < len(items):
                    items[index]["dish"] = row["new_dish"]
                continue
            for item in items:
                if str(item.get("dish") or "").strip() == row["old_dish"]:
                    item["dish"] = row["new_dish"]
    return menu


def dish_image_url(item):
    dish = str((item or {}).get("dish") or "").strip()
    category = str((item or {}).get("category") or "").strip()
    if not dish:
        return ""
    return "/api/dish-image?" + urllib.parse.urlencode(
        {"dish": dish, "category": category, "v": OPENAI_IMAGE_VERSION}
    )


def image_url_for_item(item):
    return dish_image_url(item)


def dish_image_key(dish, category):
    return hashlib.sha1(f"{category}|{dish}".encode("utf-8")).hexdigest()


def dish_image_path(dish, category):
    return DISH_IMAGE_DIR / f"{dish_image_key(dish, category)}.{OPENAI_IMAGE_FORMAT}"


def dish_image_content_type(path):
    suffix = path.suffix.lower()
    if suffix == ".jpg" or suffix == ".jpeg":
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def ai_dish_prompt(dish, category):
    kind_hint = "\u6e6f\u54c1\u8981\u662f\u4e00\u7897\u6e6f\uff0c\u770b\u5f97\u5230\u6e6f\u6c41\u548c\u4e3b\u8981\u98df\u6750\u3002" if category == "\u6e6f\u54c1" else "\u8981\u662f\u4e00\u76e4\u6210\u54c1\u83dc\uff0c\u4e3b\u9ad4\u53ea\u6709\u9019\u9053\u83dc\u3002"
    return (
        f"\u8acb\u751f\u6210\u4e00\u5f35\u771f\u5be6\u98df\u7269\u651d\u5f71\u98a8\u683c\u7684\u5716\u7247\uff1a{dish}\u3002"
        f"\u83dc\u8272\u985e\u5225\uff1a{category}\u3002{kind_hint}"
        "\u98a8\u683c\uff1a\u53f0\u7063\u5718\u81b3\u5eda\u623f\u5be6\u969b\u51fa\u9910\u7167\uff0c\u81ea\u7136\u5149\uff0c\u6e05\u695a\uff0c\u6b63\u5e38\u9910\u76e4\u6216\u6e6f\u7897\uff0c\u4e0d\u8981\u8c6a\u83ef\u9910\u5ef3\u64fa\u76e4\u3002"
        "\u5fc5\u9808\u7b26\u5408\u83dc\u540d\uff0c\u4e0d\u8981\u51fa\u73fe\u4e0d\u76f8\u95dc\u7684\u98df\u7269\u3001\u98f2\u6599\u3001\u751c\u9ede\u6216\u5176\u4ed6\u83dc\u3002"
        "\u5716\u7247\u5167\u4e0d\u8981\u4efb\u4f55\u6587\u5b57\u3001\u6c34\u5370\u3001logo\u3001\u4eba\u7269\u3001\u624b\u3002"
    )


def generate_ai_dish_image(dish, category):
    if not OPENAI_API_KEY:
        return None
    path = dish_image_path(dish, category)
    if path.exists() and path.stat().st_size > 0:
        return path
    DISH_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": ai_dish_prompt(dish, category),
        "size": "1024x1024",
        "quality": OPENAI_IMAGE_QUALITY,
        "output_format": OPENAI_IMAGE_FORMAT,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        b64_image = ((data.get("data") or [{}])[0] or {}).get("b64_json")
        if not b64_image:
            return None
        path.write_bytes(base64.b64decode(b64_image))
        return path
    except Exception:
        return None


def dish_image_svg(dish, category):
    dish = str(dish or "").strip()[:24]
    category = str(category or "").strip()[:8]
    seed = int(hashlib.sha1(f"{category}|{dish}".encode("utf-8")).hexdigest()[:8], 16)
    palettes = [
        ("#13251f", "#f5c84b", "#7bd88f", "#ff9f7a"),
        ("#201725", "#ffd84d", "#68b7ff", "#ff8a65"),
        ("#181f2d", "#f5c84b", "#9ad7ff", "#7bd88f"),
        ("#241b15", "#ffd84d", "#e7b06f", "#7bd88f"),
    ]
    bg, accent, garnish, food = palettes[seed % len(palettes)]
    is_soup = category == "\u6e6f\u54c1" or any(word in dish for word in ("\u6e6f", "\u7fb9", "\u7ca5", "\u6fc3\u6e6f"))
    title = xml_escape(dish)
    cat = xml_escape(category)
    vessel = "M165 282 C180 352 420 352 435 282 Z" if is_soup else "M130 300 C168 372 432 372 470 300 Z"
    liquid = "#b86b35" if is_soup else food
    steam = """
      <path d="M250 104 C220 140 278 156 246 194" />
      <path d="M312 96 C278 138 338 158 305 198" />
      <path d="M366 112 C338 146 392 164 360 200" />
    """ if is_soup else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="675" viewBox="0 0 900 675">
  <rect width="900" height="675" fill="{bg}"/>
  <rect x="34" y="34" width="832" height="607" rx="34" fill="#0d121a" stroke="{accent}" stroke-width="6"/>
  <circle cx="735" cy="150" r="76" fill="{garnish}" opacity=".18"/>
  <circle cx="160" cy="525" r="92" fill="{accent}" opacity=".12"/>
  <g transform="translate(150 115)">
    <ellipse cx="300" cy="285" rx="245" ry="86" fill="#05070a" opacity=".36"/>
    <path d="{vessel}" fill="#f3f0df"/>
    <ellipse cx="300" cy="280" rx="235" ry="72" fill="#f9f6ea"/>
    <ellipse cx="300" cy="270" rx="198" ry="52" fill="{liquid}"/>
    <circle cx="230" cy="254" r="28" fill="{garnish}"/>
    <circle cx="350" cy="276" r="23" fill="#f3d269"/>
    <path d="M275 246 C330 210 390 230 410 258 C356 254 322 272 275 246Z" fill="{food}"/>
    <path d="M196 282 C250 305 320 308 392 284" fill="none" stroke="#fff7d6" stroke-width="12" stroke-linecap="round" opacity=".78"/>
    <g fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round" opacity=".72">{steam}</g>
  </g>
  <text x="72" y="82" fill="{accent}" font-size="30" font-family="system-ui, 'Noto Sans TC', sans-serif" font-weight="800">{cat}</text>
  <text x="450" y="575" text-anchor="middle" fill="#f6f3e7" font-size="58" font-family="system-ui, 'Noto Sans TC', sans-serif" font-weight="900">{title}</text>
</svg>"""


def xml_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def menu_images(report_date, meal_key=None):
    day = load_menu().get(report_date)
    if not day:
        raise ValueError(f"\u627e\u4e0d\u5230 {report_date} \u83dc\u55ae")
    meals = []
    for meal in day.get("meals", []):
        if meal_key and meal.get("key") != meal_key:
            continue
        items = []
        for item in meal.get("items", []):
            if not item.get("dish"):
                continue
            image_url = image_url_for_item(item)
            items.append({**item, "image_url": image_url})
        meals.append({"key": meal.get("key"), "label": meal.get("label"), "time": meal.get("time"), "items": items})
    return {"date": report_date, "display_date": day.get("display_date"), "meals": meals}


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def normalize_digits_and_separators(text):
    return unicodedata.normalize("NFKC", str(text or ""))


def weekday_label(report_date):
    names = ["\u661f\u671f\u4e00", "\u661f\u671f\u4e8c", "\u661f\u671f\u4e09", "\u661f\u671f\u56db", "\u661f\u671f\u4e94", "\u661f\u671f\u516d", "\u661f\u671f\u65e5"]
    try:
        return names[datetime.strptime(report_date, "%Y-%m-%d").weekday()]
    except Exception:
        return ""


def session_cookie_value(username):
    expires = int(time.time()) + ADMIN_SESSION_TTL_SECONDS
    payload = f"{username}:{expires}"
    signature = hmac.new(
        ADMIN_SESSION_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii")


def verify_session_cookie(value):
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
        username, expires, signature = decoded.rsplit(":", 2)
        if username != ADMIN_USERNAME or int(expires) < int(time.time()):
            return False
        payload = f"{username}:{expires}"
        expected = hmac.new(
            ADMIN_SESSION_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                unit TEXT NOT NULL,
                delivery_location TEXT NOT NULL DEFAULT '',
                meal_key TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                count INTEGER NOT NULL,
                restrictions TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                line_key TEXT NOT NULL
            )
            """
        )
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
        migrations = {
            "delivery_location": "ALTER TABLE reports ADD COLUMN delivery_location TEXT NOT NULL DEFAULT ''",
            "restrictions": "ALTER TABLE reports ADD COLUMN restrictions TEXT NOT NULL DEFAULT '[]'",
            "note": "ALTER TABLE reports ADD COLUMN note TEXT NOT NULL DEFAULT ''",
            "line_key": "ALTER TABLE reports ADD COLUMN line_key TEXT NOT NULL DEFAULT ''",
        }
        for column, statement in migrations.items():
            if column not in existing:
                conn.execute(statement)
        conn.execute(
            """
            UPDATE reports
            SET line_key = meal_key || '-' || cuisine || '-' || delivery_location
            WHERE line_key = ''
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_line
            ON reports (report_date, unit, meal_key, line_key)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_costs (
                report_date TEXT PRIMARY KEY,
                taiwan_cost REAL NOT NULL DEFAULT 0,
                cambodia_cost REAL NOT NULL DEFAULT 0,
                taiwan_count INTEGER NOT NULL DEFAULT 0,
                cambodia_count INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                counts_locked INTEGER NOT NULL DEFAULT 1,
                pork_cost REAL NOT NULL DEFAULT 0,
                vegetable_cost REAL NOT NULL DEFAULT 0,
                frozen_cost REAL NOT NULL DEFAULT 0,
                grocery_cost REAL NOT NULL DEFAULT 0,
                gas_cost REAL NOT NULL DEFAULT 0,
                water_cost REAL NOT NULL DEFAULT 0,
                meal_box_cost REAL NOT NULL DEFAULT 0,
                corner_store_cost REAL NOT NULL DEFAULT 0,
                rice_cost REAL NOT NULL DEFAULT 0,
                ice_cost REAL NOT NULL DEFAULT 0
            )
            """
        )
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(daily_costs)").fetchall()
        }
        if "counts_locked" not in existing_columns:
            conn.execute("ALTER TABLE daily_costs ADD COLUMN counts_locked INTEGER NOT NULL DEFAULT 1")
        expense_columns = {
            "pork_cost": "REAL NOT NULL DEFAULT 0",
            "vegetable_cost": "REAL NOT NULL DEFAULT 0",
            "frozen_cost": "REAL NOT NULL DEFAULT 0",
            "grocery_cost": "REAL NOT NULL DEFAULT 0",
            "gas_cost": "REAL NOT NULL DEFAULT 0",
            "water_cost": "REAL NOT NULL DEFAULT 0",
            "meal_box_cost": "REAL NOT NULL DEFAULT 0",
            "corner_store_cost": "REAL NOT NULL DEFAULT 0",
            "rice_cost": "REAL NOT NULL DEFAULT 0",
            "ice_cost": "REAL NOT NULL DEFAULT 0",
            "cost_68": "REAL NOT NULL DEFAULT 0",
        }
        for column, definition in expense_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE daily_costs ADD COLUMN {column} {definition}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_pending_reports (
                chat_id TEXT PRIMARY KEY,
                report_date TEXT NOT NULL,
                payload TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_overhead_costs (
                month_key TEXT PRIMARY KEY,
                rent_cost REAL NOT NULL DEFAULT 0,
                utility_cost REAL NOT NULL DEFAULT 0,
                labor_cost REAL NOT NULL DEFAULT 0,
                other_monthly_cost REAL NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_staff_costs (
                month_key TEXT NOT NULL,
                staff_key TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (month_key, staff_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_pending_costs (
                chat_id TEXT PRIMARY KEY,
                report_date TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_known_chats (
                chat_id TEXT PRIMARY KEY,
                chat_type TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                meal_key TEXT NOT NULL,
                item_index INTEGER,
                category TEXT,
                old_dish TEXT NOT NULL,
                new_dish TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        menu_override_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(menu_overrides)").fetchall()
        }
        if "item_index" not in menu_override_columns:
            conn.execute("ALTER TABLE menu_overrides ADD COLUMN item_index INTEGER")
        if "category" not in menu_override_columns:
            conn.execute("ALTER TABLE menu_overrides ADD COLUMN category TEXT")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_menu_overrides_date_meal
            ON menu_overrides (report_date, meal_key)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_menu_overrides_cell
            ON menu_overrides (report_date, meal_key, item_index)
            WHERE item_index IS NOT NULL
            """
        )


def get_setting(key):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(key, value):
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )


def fixed_reports_config():
    defaults = json.loads(json.dumps(FIXED_REPORTS, ensure_ascii=False))
    stored = get_setting("fixed_reports")
    if not stored:
        return defaults
    try:
        reports = json.loads(stored)
    except Exception:
        return defaults
    if not isinstance(reports, list):
        return defaults
    existing_keys = {(rule.get("unit"), rule.get("location"), rule.get("cuisine")) for rule in reports}
    for rule in defaults:
        key = (rule.get("unit"), rule.get("location"), rule.get("cuisine"))
        if key not in existing_keys:
            reports.append(rule)
    return reports


def save_fixed_reports_config(reports):
    if not isinstance(reports, list):
        raise ValueError("固定人數格式不正確")
    cleaned = []
    for rule in reports:
        unit = str(rule.get("unit") or "").strip()
        location = str(rule.get("location") or "").strip()
        cuisine = str(rule.get("cuisine") or "").strip()
        if unit not in FIXED_REPORT_UNITS:
            raise ValueError("部門不正確")
        if cuisine not in CUISINES:
            raise ValueError("餐種不正確")
        if location not in allowed_delivery_locations(unit):
            raise ValueError("送餐地點不正確")
        counts = {}
        for meal in MEAL_KEYS:
            value = int((rule.get("counts") or {}).get(meal) or 0)
            if value < 0:
                raise ValueError("人數不能小於 0")
            if value:
                counts[meal] = value
        cleaned_rule = {"unit": unit, "location": location, "cuisine": cuisine, "counts": counts}
        if isinstance(rule.get("beef_notes"), dict):
            cleaned_rule["beef_notes"] = {meal: int(rule["beef_notes"].get(meal) or 0) for meal in MEAL_KEYS}
        cleaned.append(cleaned_rule)
    set_setting("fixed_reports", json.dumps(cleaned, ensure_ascii=False))
    return {"ok": True, "reports": cleaned}


def db_rows(report_date):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT report_date, unit, delivery_location, meal_key, cuisine, count,
                   restrictions, note, updated_at, line_key
            FROM reports
            WHERE report_date = ?
            ORDER BY unit, meal_key, delivery_location, cuisine, line_key
            """,
            (report_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_report(payload):
    init_db()
    report_date = str(payload.get("date") or today_key())
    unit = str(payload.get("unit") or "").strip()
    if unit not in DEPARTMENTS:
        raise ValueError("\u90e8\u9580\u4e0d\u6b63\u78ba")

    entries = payload.get("entries") or []
    now = datetime.now().isoformat(timespec="seconds")
    cleaned = []
    meal_keys_to_replace = set()
    for entry in entries:
        meal_key = str(entry.get("meal_key") or "")
        cuisine = str(entry.get("cuisine") or "")
        delivery_location = str(entry.get("delivery_location") or DELIVERY_LOCATIONS[0]).strip()
        note = str(entry.get("note") or "").strip()
        line_key = str(entry.get("line_key") or "").strip()
        count = int(entry.get("count") or 0)

        if meal_key not in MEAL_KEYS:
            raise ValueError("\u9910\u5225\u4e0d\u6b63\u78ba")
        if cuisine not in CUISINES:
            raise ValueError("\u9910\u7a2e\u4e0d\u6b63\u78ba")
        if delivery_location not in allowed_delivery_locations(unit):
            raise ValueError("\u9001\u9910\u5730\u9ede\u4e0d\u6b63\u78ba")
        if count < 0:
            raise ValueError("\u4eba\u6578\u4e0d\u80fd\u5c0f\u65bc 0")
        if not line_key:
            line_key = f"{meal_key}-{cuisine}-{delivery_location}-{note}"
        meal_keys_to_replace.add(meal_key)

        cleaned.append(
            (
                report_date,
                unit,
                delivery_location,
                meal_key,
                cuisine,
                count,
                "[]",
                note,
                now,
                line_key,
            )
        )

    with sqlite3.connect(DB_PATH) as conn:
        if not payload.get("merge"):
            for meal_key in meal_keys_to_replace:
                conn.execute(
                    """
                    DELETE FROM reports
                    WHERE report_date = ? AND unit = ? AND meal_key = ?
                    """,
                    (report_date, unit, meal_key),
                )
        conn.executemany(
            """
            INSERT INTO reports (
                report_date, unit, delivery_location, meal_key, cuisine, count,
                restrictions, note, updated_at, line_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date, unit, meal_key, line_key)
            DO UPDATE SET
                delivery_location = excluded.delivery_location,
                cuisine = excluded.cuisine,
                count = excluded.count,
                restrictions = excluded.restrictions,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            cleaned,
        )
    return {"ok": True, "saved": len(cleaned), "updated_at": now}


def normalize_report_date(text):
    normalized = normalize_digits_and_separators(text)
    year = datetime.now().year
    patterns = [
        r"(?<!\d)(20\d{2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})(?!\d)",
        r"(?<!\d)(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|號|号)?",
        r"(?<!\d)(\d{1,2})\s*[/.-]\s*(\d{1,2})(?:\s*(?:日|號|号))?(?!\d)",
        r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|號|号)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        if len(match.groups()) == 3:
            parsed_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
        else:
            parsed_year = year
            month = int(match.group(1))
            day = int(match.group(2))
        try:
            return datetime(parsed_year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return today_key()


def normalize_meal_key(line):
    if re.search(r"(\u65e9\u9910|\u65e9\u73ed|Breakfast)", line, re.IGNORECASE):
        return "breakfast"
    if re.search(r"(\u5348\u9910|\u4e2d\u9910|Lunch)", line, re.IGNORECASE):
        return "lunch"
    if re.search(r"(\u665a\u9910|Dinner)", line, re.IGNORECASE):
        return "dinner"
    if re.search(r"(\u5bb5\u591c|Supper)", line, re.IGNORECASE):
        return "late_night"
    return None


def normalize_short_meal_key(text):
    if re.search(r"(\u65e9\u9910|\u65e9\b|\u65e9\u73ed|Breakfast)", text, re.IGNORECASE):
        return "breakfast"
    if re.search(r"(\u5348\u9910|\u4e2d\u9910|\u4e2d\b|\u5348\b|Lunch)", text, re.IGNORECASE):
        return "lunch"
    if re.search(r"(\u665a\u9910|\u665a\b|Dinner)", text, re.IGNORECASE):
        return "dinner"
    if re.search(r"(\u5bb5\u591c|\u5bb5\b|Supper)", text, re.IGNORECASE):
        return "late_night"
    return None


def normalize_delivery_location(text):
    if "\u4e0d\u5403\u725b" in text:
        return "\u4e0d\u5403\u725b"
    if "\u4e0d\u5403\u8c6c" in text or "\u4e0d\u5403\u732a" in text or '"\u8c6c"' in text or '"\u732a"' in text:
        return "\u4e0d\u5403\u8c6c"
    if "\u4e0d\u5403\u6d77\u9bae" in text or "\u4e0d\u5403\u6d77\u9c9c" in text:
        return "\u4e0d\u5403\u6d77\u9bae"
    if "\u5305\u98ef\u76d2" in text or "\u5305\u996d\u76d2" in text or "\u9910\u6876" in text:
        return "3F\u5305\u9910\u76d2"
    if re.search(r"(^|[^0-9])68([^0-9]|$)", text):
        return "68"
    if re.search(r"(^|[^0-9])88([^0-9]|$)", text):
        return "88"
    return "3F"


def cuisine_from_text(text):
    if re.search(r"(\u80d6\u80d6|\u5065\u5eb7|Healthy)", text, re.IGNORECASE):
        return "healthy"
    if re.search(r"(\u675f\u9910|\u67ec\u9910|\u67ec\u57d4\u5be8|KH\s*Food|KH\b|Cambodia)", text, re.IGNORECASE):
        return "cambodia"
    if re.search(r"(\u53f0\u9910|TW\s*Food|TW\b|Taiwan)", text, re.IGNORECASE):
        return "taiwan"
    return None


def count_from_text(text):
    patterns = [
        r"[-\uff1a:]\s*([0-9]+)\b",
        r"([0-9]+)\s*\u4efd",
        r"\b([0-9]+)\s*(?:\u4f4d|\u4eba)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    numbers = [int(value) for value in re.findall(r"\b([0-9]+)\b", text)]
    if not numbers:
        return None
    useful_numbers = [value for value in numbers if value not in {3, 68, 88, 1002}]
    return useful_numbers[0] if useful_numbers else numbers[0]


def report_unit_from_text(text):
    if "\u6a02\u53f0" in text:
        return "\u6a02\u53f0\u98f2\u6599\u5e97"
    if "\u5ba2\u670d" in text:
        return "1002-2\u5ba2\u670d"
    if any(mark in text for mark in ["3F", "3\u6a13", "3\u697c", "MT", "\u81ea\u7531\u5973\u795e"]):
        return "3F"
    return None


def parse_letai_short_report(text):
    raw = normalize_digits_and_separators(text).strip()
    if "\u6a02\u53f0" not in raw:
        return None
    meal_key = normalize_short_meal_key(raw)
    if not meal_key:
        return None
    compact = re.sub(r"\s+", " ", raw)
    count_match = re.search(r"(?:\u65e9\u9910|\u65e9|\u4e2d\u9910|\u5348\u9910|\u4e2d|\u5348|\u665a\u9910|\u665a|\u5bb5\u591c|\u5bb5|Breakfast|Lunch|Dinner|Supper)\s*([0-9]+)", compact, re.IGNORECASE)
    if not count_match:
        numbers = [int(value) for value in re.findall(r"\b([0-9]+)\b", compact)]
        numbers = [value for value in numbers if value not in {datetime.now().year, 7, 8, 9, 10, 11, 12}]
        count = numbers[-1] if numbers else None
    else:
        count = int(count_match.group(1))
    if count is None:
        return None
    return {
        "date": normalize_report_date(raw),
        "unit": "\u6a02\u53f0\u98f2\u6599\u5e97",
        "entries": [
            {
                "meal_key": meal_key,
                "cuisine": "taiwan",
                "delivery_location": "\u90e8\u9580\u73fe\u5834",
                "count": count,
                "line_key": f"letai-{meal_key}-taiwan",
                "note": "",
            }
        ],
        "merge": False,
    }


def telegram_user_id_from_message(message):
    sender = (message or {}).get("from") or {}
    value = sender.get("id")
    return str(value) if value is not None else ""


def telegram_username_from_message(message):
    sender = (message or {}).get("from") or {}
    return str(sender.get("username") or "").lstrip("@").lower()


def telegram_user_id_from_callback(callback):
    sender = (callback or {}).get("from") or {}
    value = sender.get("id")
    return str(value) if value is not None else ""


def telegram_username_from_callback(callback):
    sender = (callback or {}).get("from") or {}
    return str(sender.get("username") or "").lstrip("@").lower()


def can_manage_bot_data(user_id, username=""):
    if not TELEGRAM_MANAGER_USER_IDS and not TELEGRAM_MANAGER_USERNAMES:
        return True
    normalized_username = str(username or "").lstrip("@").lower()
    return str(user_id or "") in TELEGRAM_MANAGER_USER_IDS or normalized_username in TELEGRAM_MANAGER_USERNAMES


def permission_denied_text(user_id, username=""):
    display_user_id = user_id or "\u8b80\u53d6\u4e0d\u5230"
    display_username = f"@{username}" if username else "\u8b80\u53d6\u4e0d\u5230"
    return (
        "\u6c92\u6709\u6b0a\u9650\u64cd\u4f5c\u9019\u500b\u529f\u80fd\u3002\n"
        "\u53ea\u6709\u6388\u6b0a\u4eba\u54e1\u53ef\u4ee5\u5beb\u5165\u4eba\u6578\u6216\u83dc\u91d1\u3002\n"
        f"\u4f60\u7684 Telegram ID\uff1a{display_user_id}\n"
        f"\u4f60\u7684 Telegram 帳號\uff1a{display_username}"
    )


def parse_menu_change_command(text):
    raw = str(text or "").strip()
    if not any(mark in raw for mark in ["\u63db", "\u6362", "\u6539\u6210"]):
        return None
    date_match = re.search(r"(\d{1,2}\s*/\s*\d{1,2})(?:\s*\u865f|\s*\u53f7)?", raw)
    if not date_match:
        return None
    tail = raw[date_match.end():].strip()
    meal_match = re.match(
        r"^(\u65e9(?:\u9910)?|\u4e2d(?:\u9910)?|\u5348(?:\u9910)?|\u665a(?:\u9910)?|\u5bb5(?:\u591c)?|Breakfast|Lunch|Dinner|Supper)\s*",
        tail,
        flags=re.IGNORECASE,
    )
    if not meal_match:
        return None
    meal_label = meal_match.group(1).lower()
    meal_key = {
        "\u65e9": "breakfast",
        "\u65e9\u9910": "breakfast",
        "breakfast": "breakfast",
        "\u4e2d": "lunch",
        "\u5348": "lunch",
        "\u4e2d\u9910": "lunch",
        "\u5348\u9910": "lunch",
        "lunch": "lunch",
        "\u665a": "dinner",
        "\u665a\u9910": "dinner",
        "dinner": "dinner",
        "\u5bb5": "late_night",
        "\u5bb5\u591c": "late_night",
        "supper": "late_night",
    }.get(meal_label)
    if not meal_key:
        return None
    tail = tail[meal_match.end():].strip()
    match = re.match(r"(.+?)\s*(?:\u63db|\u6362|\u6539\u6210)\s*(.+)$", tail)
    if not match:
        return None
    old_dish = match.group(1).strip(" ，,。")
    new_dish = match.group(2).strip(" ，,。")
    if not old_dish or not new_dish:
        return None
    return {
        "date": normalize_report_date(raw),
        "meal_key": meal_key,
        "old_dish": old_dish,
        "new_dish": new_dish,
    }


def save_menu_change(change):
    report_date = change["date"]
    meal_key = change["meal_key"]
    old_dish = change["old_dish"]
    new_dish = change["new_dish"]
    menu = load_menu()
    day = menu.get(report_date)
    if not day:
        raise ValueError(f"\u627e\u4e0d\u5230 {report_date} \u83dc\u55ae")
    meal_names = {"breakfast": "\u65e9\u9910", "lunch": "\u5348\u9910", "dinner": "\u665a\u9910", "late_night": "\u5bb5\u591c"}
    target_meal = None
    for meal in day.get("meals", []):
        if meal.get("key") == meal_key:
            target_meal = meal
            break
    if not target_meal:
        raise ValueError(f"\u627e\u4e0d\u5230 {meal_names.get(meal_key, meal_key)}")
    dishes = [str(item.get("dish") or "").strip() for item in target_meal.get("items", [])]
    if old_dish not in dishes:
        raise ValueError(f"{report_date} {meal_names.get(meal_key, meal_key)} \u627e\u4e0d\u5230\u300c{old_dish}\u300d")
    now = datetime.now().isoformat(timespec="seconds")
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO menu_overrides (report_date, meal_key, old_dish, new_dish, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report_date, meal_key, old_dish, new_dish, now),
        )
    return {
        "date": report_date,
        "meal_key": meal_key,
        "meal_label": meal_names.get(meal_key, meal_key),
        "old_dish": old_dish,
        "new_dish": new_dish,
    }


def month_menu(month):
    menu = load_menu()
    prefix = str(month or "")[:7]
    days = []
    for date in sorted(menu):
        if prefix and not date.startswith(prefix):
            continue
        days.append({"date": date, **menu[date]})
    return {
        "month": prefix,
        "meal_labels": {
            "breakfast": "\u65e9\u9910",
            "lunch": "\u5348\u9910",
            "dinner": "\u665a\u9910",
            "late_night": "\u5bb5\u591c",
        },
        "days": days,
    }


def save_menu_updates(payload):
    updates = payload.get("updates")
    if not isinstance(updates, list):
        raise ValueError("\u6c92\u6709\u6536\u5230\u83dc\u55ae\u4fee\u6539\u8cc7\u6599")
    base_menu = load_base_menu()
    now = datetime.now().isoformat(timespec="seconds")
    cleaned = []
    for update in updates:
        report_date = str(update.get("date") or "").strip()
        meal_key = str(update.get("meal_key") or "").strip()
        try:
            item_index = int(update.get("item_index"))
        except (TypeError, ValueError):
            raise ValueError("\u83dc\u55ae\u683c\u5b50\u4f4d\u7f6e\u932f\u8aa4")
        new_dish = str(update.get("dish") or "").strip()
        day = base_menu.get(report_date)
        if not day:
            raise ValueError(f"\u627e\u4e0d\u5230 {report_date} \u83dc\u55ae")
        target_meal = next((meal for meal in day.get("meals", []) if meal.get("key") == meal_key), None)
        if not target_meal:
            raise ValueError(f"{report_date} \u9910\u5225\u932f\u8aa4")
        items = target_meal.get("items", [])
        if item_index < 0 or item_index >= len(items):
            raise ValueError(f"{report_date} \u83dc\u8272\u4f4d\u7f6e\u932f\u8aa4")
        item = items[item_index]
        old_dish = str(item.get("dish") or "").strip()
        category = str(item.get("category") or "").strip()
        cleaned.append((report_date, meal_key, item_index, category, old_dish, new_dish, now))
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        for report_date, meal_key, item_index, category, old_dish, new_dish, updated_at in cleaned:
            conn.execute(
                """
                DELETE FROM menu_overrides
                WHERE report_date = ?
                  AND meal_key = ?
                  AND (
                    item_index = ?
                    OR (item_index IS NULL AND old_dish = ?)
                  )
                """,
                (report_date, meal_key, item_index, old_dish),
            )
            if new_dish != old_dish:
                conn.execute(
                    """
                    INSERT INTO menu_overrides (
                        report_date, meal_key, item_index, category, old_dish, new_dish, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (report_date, meal_key, item_index, category, old_dish, new_dish, updated_at),
                )
    month = str(payload.get("month") or (cleaned[0][0][:7] if cleaned else ""))[:7]
    return {"ok": True, "saved": len(cleaned), "menu": month_menu(month)}


def parse_bot_3f_report(text):
    raw_text = normalize_digits_and_separators(text)
    letai_payload = parse_letai_short_report(raw_text)
    if letai_payload:
        return letai_payload
    unit = report_unit_from_text(raw_text)
    if not unit:
        raise ValueError("\u76ee\u524d\u53ea\u652f\u63f4 3F \u6216 1002-2\u5ba2\u670d \u7684\u5831\u9910\u6587\u5b57")

    report_date = normalize_report_date(raw_text)
    current_meal = None
    entries_by_key = {}
    for raw_index, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or set(line) <= {"-", "_"}:
            continue
        meal_key = normalize_meal_key(line)
        if meal_key:
            current_meal = meal_key
            line = re.sub(
                r"^(\u65e9\u9910|\u5348\u9910|\u4e2d\u9910|\u665a\u9910|\u5bb5\u591c|Breakfast|Lunch|Dinner|Supper)\s*[-\uff1a:]?",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if not line:
                continue
        if not current_meal:
            continue

        cuisine = cuisine_from_text(line)
        if unit == "1002-2\u5ba2\u670d" and current_meal == "breakfast" and not cuisine:
            cuisine = "taiwan"
        if not cuisine:
            continue
        count = count_from_text(line)
        if count is None:
            continue
        location = "1002-2" if unit == "1002-2\u5ba2\u670d" else normalize_delivery_location(line)
        if unit == "3F" and current_meal == "late_night" and cuisine == "cambodia" and "\u9910\u6876" in line:
            location = "3F"
        is_late_night_cambodia_bucket = unit == "3F" and current_meal == "late_night" and cuisine == "cambodia" and location == "3F"
        line_key = f"bot-{current_meal}-{cuisine}-{location}"
        if is_late_night_cambodia_bucket:
            line_key = f"{line_key}-{raw_index}"
        if line_key in entries_by_key:
            entries_by_key[line_key]["count"] += count
        else:
            entries_by_key[line_key] = {
                "meal_key": current_meal,
                "cuisine": cuisine,
                "delivery_location": location,
                "count": count,
                "line_key": line_key,
                "note": "",
            }

    entries = list(entries_by_key.values())
    if not entries:
        raise ValueError("\u6c92\u6709\u8b80\u5230\u53ef\u5beb\u5165\u7684\u4eba\u6578\uff0c\u8acb\u78ba\u8a8d\u6709\u9910\u5225\u3001\u53f0\u9910/\u80d6\u80d6\u9910/\u675f\u9910\u6216\u67ec\u9910\u548c\u4efd\u6578")
    return {"date": report_date, "unit": unit, "entries": entries, "merge": False}


def summarize_bot_report(payload):
    meal_names = {
        "breakfast": "\u65e9\u9910",
        "lunch": "\u5348\u9910",
        "dinner": "\u665a\u9910",
        "late_night": "\u5bb5\u591c",
    }
    cuisine_names = {"taiwan": "\U0001f1f9\U0001f1fc", "healthy": "\u5065\u5eb7\u9910\U0001f966", "cambodia": "\U0001f1f0\U0001f1ed"}
    totals = {meal: {"taiwan": 0, "healthy": 0, "cambodia": 0, "total": 0} for meal in MEAL_KEYS}
    location_lines = []
    for entry in payload["entries"]:
        meal = entry["meal_key"]
        cuisine = entry["cuisine"]
        count = int(entry["count"])
        totals[meal][cuisine] += count
        totals[meal]["total"] += count
        location_lines.append(
            f"{meal_names[meal]} {display_location(entry['delivery_location'])}\uff1a{cuisine_names[cuisine]}{count}"
        )
    lines = ["\u5df2\u8b80\u5230\u4eba\u6578", f"{payload['date']} {payload['unit']}"]
    for meal in MEAL_KEYS:
        row = totals[meal]
        if not row["total"]:
            continue
        lines.append(f"{meal_names[meal]} \u53f0\u9910{row['taiwan']} \u5065\u5eb7\u9910{row['healthy']} \u67ec\u9910{row['cambodia']}\uff0c\u5408\u8a08{row['total']}")
    lines.append("")
    lines.append("\u660e\u7d30\uff1a")
    lines.extend(location_lines)
    return "\n".join(lines)


def empty_count_row():
    return {"taiwan": 0, "healthy": 0, "cambodia": 0, "total": 0}


def add_count_row(target, row, cuisines=None):
    cuisines = cuisines or CUISINES
    for cuisine in cuisines:
        target[cuisine] += int(row.get(cuisine, 0))
    target["total"] = target["taiwan"] + target["healthy"] + target["cambodia"]
    return target


def count_for_units(data, meal, unit_locations, cuisines=None):
    total = empty_count_row()
    for unit, location in unit_locations:
        row = data["units"].get(unit, {}).get(location, {}).get(meal)
        if row:
            add_count_row(total, row, cuisines)
    return total


def count_from_row(row, cuisines=None):
    total = empty_count_row()
    add_count_row(total, row, cuisines)
    return total


def display_location(location):
    labels = {
        "\u4e0d\u5403\u725b": "\U0001f42e\u4e0d\u5403\u725b",
        "\u4e0d\u5403\u8c6c": "\U0001f437\u4e0d\u5403\u8c6c",
        "\u4e0d\u5403\u6d77\u9bae": "\U0001f99e\u4e0d\u5403\u6d77\u9bae",
    }
    return labels.get(location, location)


def count_text(row, bucket_cuisines=None):
    bucket_cuisines = set(bucket_cuisines or [])
    parts = []
    if row["taiwan"]:
        suffix = "\U0001faa3" if "taiwan" in bucket_cuisines else ""
        parts.append(f"\U0001f1f9\U0001f1fc{row['taiwan']}{suffix}")
    if row["healthy"]:
        parts.append(f"\u5065\u5eb7\u9910\U0001f966{row['healthy']}")
    if row["cambodia"]:
        suffix = "\U0001faa3" if "cambodia" in bucket_cuisines else ""
        parts.append(f"\U0001f1f0\U0001f1ed{row['cambodia']}{suffix}")
    return " / ".join(parts)


def bucket_count_text(row, bucket_counts=None):
    bucket_counts = bucket_counts or {}
    parts = []
    if row["taiwan"]:
        if bucket_counts.get("taiwan"):
            parts.append(f"\U0001f1f9\U0001f1fc\U0001faa3{bucket_counts['taiwan']}\u6876")
        else:
            parts.append(f"\U0001f1f9\U0001f1fc{row['taiwan']}")
    if row["healthy"]:
        parts.append(f"\u5065\u5eb7\u9910\U0001f966{row['healthy']}")
    if row["cambodia"]:
        if bucket_counts.get("cambodia"):
            detail = bucket_counts.get("cambodia_detail", "")
            parts.append(f"\U0001f1f0\U0001f1ed\U0001faa3{bucket_counts['cambodia']}\u6876{detail}")
        else:
            parts.append(f"\U0001f1f0\U0001f1ed{row['cambodia']}")
    return " / ".join(parts)


def table_line(label, row, note="", bucket_cuisines=None):
    if not row["total"]:
        return ""
    suffix = f"\uff08{note}\uff09" if note else ""
    return f"{label}\uff1a{count_text(row, bucket_cuisines)}{suffix}"


def table_line_with_bucket_counts(label, row, note="", bucket_counts=None):
    if not row["total"]:
        return ""
    suffix = f"\uff08{note}\uff09" if note else ""
    return f"{label}\uff1a{bucket_count_text(row, bucket_counts)}{suffix}"


def meal_total_line(row, bucket_row=None, restriction_rows=None, bucket_counts=None):
    bucket_row = bucket_row or empty_count_row()
    restriction_rows = restriction_rows or []
    bucket_counts = bucket_counts or {}
    restricted_taiwan = sum(item["row"]["taiwan"] for item in restriction_rows)
    taiwan_box = max(0, row["taiwan"] - bucket_row["taiwan"] - restricted_taiwan)
    cambodia_box = max(0, row["cambodia"] - bucket_row["cambodia"])
    parts = []
    if taiwan_box:
        parts.append(f"\U0001f1f9\U0001f1fc\U0001f371\u5171 {taiwan_box}")
    if bucket_row["taiwan"]:
        parts.append(f"\U0001f1f9\U0001f1fc\U0001faa3\u5171 {bucket_row['taiwan']}")
    for item in restriction_rows:
        count = item["row"]["taiwan"]
        if count:
            parts.append(f"{item['label']}\U0001f371 {count}\uff08MT\uff09")
    if row["healthy"]:
        parts.append(f"\u5065\u5eb7\u9910\U0001f966 {row['healthy']}")
    if cambodia_box:
        parts.append(f"\U0001f1f0\U0001f1ed\U0001f371\u5171 {cambodia_box}")
    if bucket_row["cambodia"]:
        if bucket_counts.get("cambodia"):
            detail = bucket_counts.get("cambodia_detail", "")
            parts.append(f"\U0001f1f0\U0001f1ed\U0001faa3\u5171 {bucket_counts['cambodia']}\u6876{detail}")
        else:
            parts.append(f"\U0001f1f0\U0001f1ed\U0001faa3\u5171 {bucket_row['cambodia']}")
    return "\uff5c".join(parts)


def bucket_total_for_meal(data, meal):
    total = empty_count_row()
    if meal != "breakfast":
        add_count_row(
            total,
            count_for_units(data, meal, [("1001", "\u90e8\u9580\u73fe\u5834")], ["taiwan"]),
            ["taiwan"],
        )
    add_count_row(total, count_from_row(data["locations"]["3F"][meal], ["taiwan", "cambodia"]), ["taiwan", "cambodia"])
    if meal == "late_night":
        add_count_row(total, count_from_row(data["locations"]["3F\u5305\u9910\u76d2"][meal], ["cambodia"]), ["cambodia"])
    return total


def restriction_totals_for_meal(data, meal):
    restrictions = [
        ("\U0001f42e\u4e0d\u5403\u725b", "\u4e0d\u5403\u725b"),
        ("\U0001f437\u4e0d\u5403\u8c6c", "\u4e0d\u5403\u8c6c"),
        ("\U0001f99e\u4e0d\u5403\u6d77\u9bae", "\u4e0d\u5403\u6d77\u9bae"),
    ]
    return [
        {"label": label, "location": location, "row": count_for_units(data, meal, [("3F", location)], ["taiwan"])}
        for label, location in restrictions
    ]


def bucket_count_for_meal(data, meal):
    counts = {}
    if meal == "late_night":
        parts = late_night_cambodia_bucket_parts(data)
        if parts:
            counts["cambodia"] = len(parts)
            counts["cambodia_detail"] = "\uff08" + "+".join(str(value) for value in parts) + "\uff09"
    return counts


def late_night_cambodia_bucket_parts(data):
    parts = []
    for row in sorted(data["rows"], key=lambda item: str(item.get("line_key") or "")):
        if (
            row.get("unit") == "3F"
            and row.get("meal_key") == "late_night"
            and row.get("cuisine") == "cambodia"
            and row.get("delivery_location") in {"3F", "3F\u5305\u9910\u76d2"}
        ):
            parts.append(int(row.get("count") or 0))
    return [value for value in parts if value > 0]


def mt_3f_count_for_meal(data, meal):
    total = count_from_row(data["locations"]["3F"][meal], ["taiwan", "cambodia"])
    if meal == "late_night":
        add_count_row(total, count_from_row(data["locations"]["3F\u5305\u9910\u76d2"][meal], ["cambodia"]), ["cambodia"])
    return total


def package_box_count_for_meal(data, meal):
    cuisines = ["taiwan", "healthy"] if meal == "late_night" else None
    return count_from_row(data["locations"]["3F\u5305\u9910\u76d2"][meal], cuisines)


def delivery_table_text(report_date, meal_key=None):
    meal_names = {
        "breakfast": "\u65e9\u9910 07:00",
        "lunch": "\u5348\u9910 11:00",
        "dinner": "\u665a\u9910 05:00",
        "late_night": "\u5bb5\u591c 09:00",
    }
    data = summary(report_date)
    rows = [
        (
            lambda meal: "1001 3A\U0001f371" if meal == "breakfast" else "1001 3A\U0001faa3",
            lambda meal: count_for_units(data, meal, [("1001", "\u90e8\u9580\u73fe\u5834")], ["taiwan", "healthy"]),
            "",
        ),
        (
            "1002-2\u4ee3\u7406\U0001f371",
            lambda meal: count_for_units(data, meal, [("1002-2\u4ee3\u7406", "\u90e8\u9580\u73fe\u5834")]),
            lambda meal: "\U0001f9645" if meal == "dinner" else "",
        ),
        (
            "1002-3\u91d1\u6d41\U0001f371",
            lambda meal: count_for_units(data, meal, [("1002-3\u91d1\u6d41", "\u90e8\u9580\u73fe\u5834")], ["taiwan", "healthy"]),
            "",
        ),
        ("1002-2\u5ba2\u670d\U0001f371", lambda meal: count_for_units(data, meal, [("1002-2\u5ba2\u670d", "1002-2")]), ""),
        ("\u6a02\u53f0\u98f2\u6599\u5e97\U0001f371", lambda meal: count_for_units(data, meal, [("\u6a02\u53f0\u98f2\u6599\u5e97", "\u90e8\u9580\u73fe\u5834")]), ""),
        (
            "MT-3F\U0001faa3",
            lambda meal: mt_3f_count_for_meal(data, meal),
            lambda meal: "MT",
            lambda meal: ["cambodia"] if meal == "late_night" and data["locations"]["3F"][meal]["cambodia"] else [],
        ),
        ("\u5065\u5eb7\u9910\U0001f966-3F", lambda meal: count_from_row(data["locations"]["3F"][meal], ["healthy"]), "MT"),
        ("\u5305\u98ef\u76d2\U0001f371-3F", lambda meal: package_box_count_for_meal(data, meal), "MT"),
        ("68\u516c\u5bd3\U0001f371", lambda meal: count_for_units(data, meal, [("3F", "68")]), "MT"),
        ("88\u516c\u5bd3\U0001f371", lambda meal: count_for_units(data, meal, [("3F", "88")]), "MT"),
        ("\u4fdd\u59c6 68\U0001f371", lambda meal: count_for_units(data, meal, [("\u4fdd\u59c6\u90e8\u9580", "68")]), ""),
        ("\u4fdd\u59c6 88\U0001f371", lambda meal: count_for_units(data, meal, [("\u4fdd\u59c6\u90e8\u9580", "88")]), ""),
        ("\u6d77\u5357\u96de\u98ef\U0001f371", lambda meal: count_for_units(data, meal, [("\u6d77\u5357\u96de\u98ef", "\u90e8\u9580\u73fe\u5834")]), ""),
        ("\U0001f42e\u4e0d\u5403\u725b\U0001f371", lambda meal: count_for_units(data, meal, [("3F", "\u4e0d\u5403\u725b")]), "MT"),
        ("\U0001f437\u4e0d\u5403\u8c6c\U0001f371", lambda meal: count_for_units(data, meal, [("3F", "\u4e0d\u5403\u8c6c")]), "MT"),
        ("\U0001f99e\u4e0d\u5403\u6d77\u9bae\U0001f371", lambda meal: count_for_units(data, meal, [("3F", "\u4e0d\u5403\u6d77\u9bae")]), "MT"),
    ]
    def visible_total_for_meal(meal):
        total_row = empty_count_row()
        for row_def in rows:
            add_count_row(total_row, row_def[1](meal))
        return total_row

    selected_meals = [meal_key] if meal_key in MEAL_KEYS else MEAL_KEYS
    weekday = weekday_label(report_date)
    date_title = f"{report_date} {weekday}".strip()
    title = f"\u9001\u9910\u7e3d\u8868 {date_title}"
    if meal_key in MEAL_KEYS:
        title = f"{meal_names[meal_key]} \u9001\u9910\u7e3d\u8868 {date_title}"
    lines = [title]
    for meal in selected_meals:
        visible_total = visible_total_for_meal(meal)
        total = visible_total["total"]
        if not total:
            continue
        lines.append("")
        lines.append(f"{meal_names[meal]}")
        bucket_counts = bucket_count_for_meal(data, meal)
        lines.append(
            meal_total_line(
                visible_total,
                bucket_total_for_meal(data, meal),
                restriction_totals_for_meal(data, meal),
                bucket_counts,
            )
        )
        for row_def in rows:
            label, getter, note = row_def[:3]
            meal_label = label(meal) if callable(label) else label
            bucket_cuisines = row_def[3](meal) if len(row_def) > 3 and callable(row_def[3]) else (row_def[3] if len(row_def) > 3 else [])
            meal_note = note(meal) if callable(note) else note
            row = getter(meal)
            if meal_label == "MT-3F\U0001faa3" and bucket_counts:
                line = table_line_with_bucket_counts(meal_label, row, meal_note, bucket_counts)
            else:
                line = table_line(meal_label, row, meal_note, bucket_cuisines)
            if line:
                lines.append(line)
    return "\n".join(lines)


def totals_report_text(report_date):
    meal_names = {
        "breakfast": "\u65e9\u9910",
        "lunch": "\u5348\u9910",
        "dinner": "\u665a\u9910",
        "late_night": "\u5bb5\u591c",
    }
    data = summary(report_date)
    lines = [f"\u7e3d\u6578 {report_date}"]
    grand = empty_count_row()
    for meal in MEAL_KEYS:
        row = data["totals"][meal]
        add_count_row(grand, row)
        lines.append(
            f"{meal_names[meal]}\uff1a"
            f"\U0001f1f9\U0001f1fc{row['taiwan']} / "
            f"\u5065\u5eb7\u9910\U0001f966{row['healthy']} / "
            f"\U0001f1f0\U0001f1ed{row['cambodia']} / "
            f"\u5408\u8a08{row['total']}"
        )
    lines.append("")
    lines.append(
        f"\u5168\u5929\u7e3d\u6578\uff1a"
        f"\U0001f1f9\U0001f1fc{grand['taiwan']} / "
        f"\u5065\u5eb7\u9910\U0001f966{grand['healthy']} / "
        f"\U0001f1f0\U0001f1ed{grand['cambodia']} / "
        f"\u5408\u8a08{grand['total']}"
    )
    return "\n".join(lines)


def save_pending_bot_report(chat_id, payload, summary_text):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bot_pending_reports (chat_id, report_date, payload, summary_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id)
            DO UPDATE SET
                report_date = excluded.report_date,
                payload = excluded.payload,
                summary_text = excluded.summary_text,
                created_at = excluded.created_at
            """,
            (str(chat_id), payload["date"], json.dumps(payload, ensure_ascii=False), summary_text, int(time.time())),
        )


def load_pending_bot_report(chat_id):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload, created_at FROM bot_pending_reports WHERE chat_id = ?",
            (str(chat_id),),
        ).fetchone()
    if not row:
        return None
    if int(time.time()) - int(row["created_at"]) > BOT_CONFIRM_TTL_SECONDS:
        clear_pending_bot_report(chat_id)
        return None
    return json.loads(row["payload"])


def clear_pending_bot_report(chat_id):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bot_pending_reports WHERE chat_id = ?", (str(chat_id),))


def save_pending_bot_cost(chat_id, payload):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bot_pending_costs (chat_id, report_date, payload, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id)
            DO UPDATE SET
                report_date = excluded.report_date,
                payload = excluded.payload,
                created_at = excluded.created_at
            """,
            (str(chat_id), payload["date"], json.dumps(payload, ensure_ascii=False), int(time.time())),
        )


def load_pending_bot_cost(chat_id):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload, created_at FROM bot_pending_costs WHERE chat_id = ?",
            (str(chat_id),),
        ).fetchone()
    if not row:
        return None
    if int(time.time()) - int(row["created_at"]) > BOT_CONFIRM_TTL_SECONDS:
        clear_pending_bot_cost(chat_id)
        return None
    return json.loads(row["payload"])


def clear_pending_bot_cost(chat_id):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bot_pending_costs WHERE chat_id = ?", (str(chat_id),))


def parse_money_amount(text):
    match = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", str(text or ""))
    if not match:
        return None
    return round(float(match.group(1).replace(",", "")), 2)


def cost_menu_keyboard(report_date):
    keyboard = []
    for row in COST_MENU_ROWS:
        keyboard.append(
            [
                {"text": COST_FIELD_LABELS[field], "callback_data": f"cost|{report_date}|{field}"}
                for field in row
            ]
        )
    return {"inline_keyboard": keyboard}


def cost_confirm_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "\u78ba\u8a8d\u5beb\u5165", "callback_data": "cost_confirm"},
                {"text": "\u53d6\u6d88", "callback_data": "cost_cancel"},
            ]
        ]
    }


def main_reply_keyboard():
    return {
        "keyboard": [
            [
                {
                    "text": "OFA \u5c0f\u7a0b\u5f0f",
                    "web_app": {"url": MINI_APP_URL},
                },
                {
                    "text": "\u5f8c\u53f0\u7db2\u5740",
                    "web_app": {"url": ADMIN_URL},
                }
            ],
            [{"text": "\u4eba\u6578\u56de\u5831"}, {"text": "\u6bcf\u65e5\u83dc\u91d1"}],
            [{"text": "\u4eca\u65e5\u83dc\u55ae"}, {"text": "\u9001\u9910\u7e3d\u8868"}],
            [{"text": "\u9001\u9910\u7e3d\u6578"}, {"text": "\u53d6\u6d88"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "\u9078\u64c7\u529f\u80fd\u6216\u76f4\u63a5\u8f38\u5165...",
    }


def main_inline_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "\u4eba\u6578\u56de\u5831", "callback_data": "main|people"},
                {"text": "\u6bcf\u65e5\u83dc\u91d1", "callback_data": "main|cost"},
            ],
            [
                {"text": "\u4eca\u65e5\u83dc\u55ae", "callback_data": "main|menu"},
                {"text": "\u9001\u9910\u7e3d\u8868", "callback_data": "main|table"},
            ],
            [
                {"text": "\u9001\u9910\u7e3d\u6578", "callback_data": "main|total"},
                {"text": "\u516c\u544a", "callback_data": "main|announce"},
            ],
            [
                {"text": "\u5f8c\u53f0\u7db2\u5740", "url": ADMIN_URL},
            ],
        ]
    }


def telegram_api(method, payload):
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def telegram_send_message(chat_id, text, reply_to_message_id=None, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup is None:
        reply_markup = main_reply_keyboard()
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return telegram_api("sendMessage", payload)


def telegram_answer_callback(callback_query_id, text=""):
    if not callback_query_id:
        return {"ok": False, "error": "callback_query_id missing"}
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return telegram_api("answerCallbackQuery", payload)


def remember_bot_chat(chat):
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return
    now = datetime.now().isoformat(timespec="seconds")
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bot_known_chats (chat_id, chat_type, title, username, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type = excluded.chat_type,
                title = excluded.title,
                username = excluded.username,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                str(chat.get("type") or ""),
                str(chat.get("title") or chat.get("first_name") or ""),
                str(chat.get("username") or ""),
                now,
            ),
        )
        conn.commit()


def known_bot_chats():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chat_id, chat_type, title, username, updated_at
            FROM bot_known_chats
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def broadcast_bot_announcement(text):
    chats = known_bot_chats()
    sent = 0
    failed = 0
    for chat in chats:
        result = telegram_send_message(chat["chat_id"], text, reply_markup=False)
        if result.get("ok"):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "total": len(chats)}


def broadcast_delivery_table(report_date):
    chats = [chat for chat in known_bot_chats() if chat.get("chat_type") in {"group", "supergroup"}]
    text = f"\u4eca\u65e5\u9001\u9910\u8868\u5df2\u66f4\u65b0\n\n{delivery_table_text(report_date)}"
    sent = 0
    failed = 0
    results = []
    for chat in chats:
        result = telegram_send_message(chat["chat_id"], text, reply_markup=False)
        ok = bool(result.get("ok"))
        sent += 1 if ok else 0
        failed += 0 if ok else 1
        results.append(
            {
                "chat_id": chat["chat_id"],
                "title": chat.get("title") or "",
                "ok": ok,
                "error": result.get("description") or result.get("error") or "",
            }
        )
    return {"date": report_date, "sent": sent, "failed": failed, "total": len(chats), "results": results}


def send_cost_menu(chat_id, report_date=None, reply_to_message_id=None):
    report_date = report_date or today_key()
    telegram_send_message(
        chat_id,
        f"\u6bcf\u65e5\u83dc\u91d1\u8f38\u5165\n{report_date}\n\n\u8acb\u9078\u64c7\u5ee0\u5546 / \u6210\u672c\u985e\u5225\uff1a",
        reply_to_message_id,
        cost_menu_keyboard(report_date),
    )
    return {"ok": True, "action": "cost_menu", "date": report_date}


def send_main_menu(chat_id, reply_to_message_id=None):
    telegram_send_message(
        chat_id,
        "\u5df2\u958b\u555f\u5eda\u623f\u6a5f\u5668\u4eba\u5feb\u6377\u9375\u76e4\u3002\n"
        "\u5982\u679c\u624b\u6a5f\u6c92\u6709\u986f\u793a\uff0c\u8acb\u5148\u9ede\u8f38\u5165\u6846\u65c1\u908a\u7684\u9375\u76e4\u5716\u793a\u3002",
        reply_to_message_id,
        main_reply_keyboard(),
    )
    telegram_send_message(
        chat_id,
        "\u5eda\u623f\u6a5f\u5668\u4eba\u9078\u55ae\n\n"
        "\u8acb\u9ede\u4e0b\u9762\u6309\u9215\uff1a\n"
        "\u4eba\u6578\u56de\u5831 / \u6bcf\u65e5\u83dc\u91d1 / \u4eca\u65e5\u83dc\u55ae / \u9001\u9910\u7e3d\u8868 / \u9001\u9910\u7e3d\u6578 / \u5f8c\u53f0\u7db2\u5740",
        reply_to_message_id,
        main_inline_keyboard(),
    )
    return {"ok": True, "action": "main_menu"}


def today_menu_text(report_date):
    day = load_menu().get(report_date)
    if not day:
        return f"\u627e\u4e0d\u5230 {report_date} \u83dc\u55ae"
    lines = [f"{day.get('display_date', report_date)} \u4eca\u65e5\u83dc\u55ae"]
    for meal in day.get("meals", []):
        lines.append("")
        lines.append(f"{meal.get('label')} {meal.get('time')}")
        for item in meal.get("items", []):
            dish = str(item.get("dish") or "").strip()
            if dish:
                lines.append(f"{item.get('category')}\uff1a{dish}")
    return "\n".join(lines)


def people_report_help():
    return (
        "\u4eba\u6578\u56de\u5831\n\n"
        "\u7528\u6cd5 1\uff1a\u76f4\u63a5\u8cbc\u4e0a 3F / \u5ba2\u670d\u7684\u5831\u9910\u6587\u5b57\uff0c\u6a5f\u5668\u4eba\u6703\u81ea\u52d5\u5beb\u5165\u3002\n"
        "\u7528\u6cd5 2\uff1a\u56de\u8986\u5831\u9910\u8a0a\u606f\uff0c\u8f38\u5165 /people\n"
        "\u7528\u6cd5 3\uff1a/people \u5f8c\u9762\u76f4\u63a5\u8cbc\u5831\u9910\u6587\u5b57"
    )


def handle_cost_callback(chat_id, message_id, callback_id, data):
    if data == "cost_cancel":
        clear_pending_bot_cost(chat_id)
        telegram_send_message(chat_id, "\u5df2\u53d6\u6d88\u9019\u6b21\u83dc\u91d1\u8f38\u5165\u3002", message_id)
        return {"ok": True, "action": "cost_cancelled"}
    if data == "cost_confirm":
        pending = load_pending_bot_cost(chat_id)
        if not pending or "amount" not in pending:
            telegram_send_message(chat_id, "\u6c92\u6709\u5f85\u78ba\u8a8d\u7684\u83dc\u91d1\uff0c\u8acb\u5148\u7528 /\u83dc\u91d1 \u9078\u5ee0\u5546\u518d\u8f38\u5165\u91d1\u984d\u3002", message_id)
            return {"ok": True, "action": "no_pending_cost"}
        result = save_cost({"date": pending["date"], pending["field"]: pending["amount"]})
        clear_pending_bot_cost(chat_id)
        telegram_send_message(
            chat_id,
            f"\u5df2\u5beb\u5165\u83dc\u91d1\n"
            f"{pending['date']}\n"
            f"{COST_FIELD_LABELS.get(pending['field'], pending['field'])}\uff1a${pending['amount']:.2f}\n"
            f"\u5f8c\u53f0\u5df2\u540c\u6b65\u3002",
            message_id,
        )
        return {"ok": True, "action": "cost_saved", "result": result}
    parts = data.split("|")
    if len(parts) == 3 and parts[0] == "cost" and parts[2] in COST_FIELD_LABELS:
        payload = {"date": parts[1], "field": parts[2]}
        save_pending_bot_cost(chat_id, payload)
        telegram_send_message(
            chat_id,
            f"{payload['date']} {COST_FIELD_LABELS[payload['field']]}\n\u8acb\u8f38\u5165\u91d1\u984d\uff0c\u4f8b\u5982\uff1a235.5",
            message_id,
        )
        return {"ok": True, "action": "cost_vendor_selected", "payload": payload}
    return {"ok": True, "ignored": "unknown callback"}


def handle_pending_cost_amount(chat_id, text, message_id):
    pending = load_pending_bot_cost(chat_id)
    if not pending or "amount" in pending:
        return None
    amount = parse_money_amount(text)
    if amount is None:
        return None
    pending["amount"] = amount
    save_pending_bot_cost(chat_id, pending)
    telegram_send_message(
        chat_id,
        f"\u8acb\u78ba\u8a8d\u83dc\u91d1\n"
        f"{pending['date']}\n"
        f"{COST_FIELD_LABELS.get(pending['field'], pending['field'])}\uff1a${amount:.2f}",
        message_id,
        cost_confirm_keyboard(),
    )
    return {"ok": True, "action": "cost_amount_pending", "payload": pending}


def handle_telegram_update(update):
    callback = update.get("callback_query") or {}
    if callback:
        data = str(callback.get("data") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        message_id = message.get("message_id")
        callback_id = callback.get("id")
        user_id = telegram_user_id_from_callback(callback)
        username = telegram_username_from_callback(callback)
        if not chat_id:
            return {"ok": True, "ignored": "callback without chat"}
        remember_bot_chat(chat)
        if TELEGRAM_ALLOWED_CHAT_ID and chat_id != TELEGRAM_ALLOWED_CHAT_ID:
            return {"ok": True, "ignored": "chat not allowed"}
        if data.startswith("main|"):
            telegram_answer_callback(callback_id, "\u5df2\u6536\u5230")
            action = data.split("|", 1)[1]
            if action == "people":
                telegram_send_message(chat_id, people_report_help(), message_id)
                return {"ok": True, "action": "parse_help"}
            if action == "cost":
                if not can_manage_bot_data(user_id, username):
                    telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
                    return {"ok": True, "action": "permission_denied"}
                return send_cost_menu(chat_id, today_key(), message_id)
            if action == "menu":
                telegram_send_message(chat_id, today_menu_text(today_key()), message_id)
                return {"ok": True, "action": "today_menu"}
            if action == "table":
                telegram_send_message(chat_id, delivery_table_text(today_key()), message_id)
                return {"ok": True, "action": "delivery_table"}
            if action == "total":
                telegram_send_message(chat_id, delivery_table_text(today_key()), message_id)
                return {"ok": True, "action": "employee_totals_report"}
            if action == "announce":
                if not can_manage_bot_data(user_id, username):
                    telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
                    return {"ok": True, "action": "permission_denied"}
                result = broadcast_bot_announcement(KHMER_USAGE_ANNOUNCEMENT)
                telegram_send_message(
                    chat_id,
                    f"\u516c\u544a\u5df2\u767c\u9001\n"
                    f"\u6210\u529f\uff1a{result['sent']}\n"
                    f"\u5931\u6557\uff1a{result['failed']}\n"
                    f"\u5df2\u8a18\u9304\u5c0d\u8c61\uff1a{result['total']}",
                    message_id,
                )
                return {"ok": True, "action": "announcement", "result": result}
            return {"ok": True, "ignored": "unknown main callback"}
        if data.startswith("cost"):
            telegram_answer_callback(callback_id, "\u5df2\u6536\u5230")
            if not can_manage_bot_data(user_id, username):
                telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
                return {"ok": True, "action": "permission_denied"}
            try:
                return handle_cost_callback(chat_id, message_id, callback_id, data)
            except Exception as exc:
                telegram_send_message(chat_id, f"\u83dc\u91d1\u9078\u55ae\u6c92\u6709\u5beb\u5165\uff1a{exc}", message_id)
                return {"ok": True, "action": "cost_callback_failed", "error": str(exc)}
        telegram_answer_callback(callback_id, "\u672a\u77e5\u9078\u9805")
        return {"ok": True, "ignored": "unknown callback"}

    message = update.get("message") or update.get("edited_message") or {}
    text = str(message.get("text") or message.get("caption") or "").strip()
    reply = message.get("reply_to_message") or {}
    reply_text = str(reply.get("text") or reply.get("caption") or "").strip()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    user_id = telegram_user_id_from_message(message)
    username = telegram_username_from_message(message)
    message_id = message.get("message_id")
    if not chat_id or not text:
        return {"ok": True, "ignored": True}
    remember_bot_chat(chat)
    if TELEGRAM_ALLOWED_CHAT_ID and chat_id != TELEGRAM_ALLOWED_CHAT_ID:
        return {"ok": True, "ignored": "chat not allowed"}

    normalized = re.sub(r"\s+", "", text)
    if text.startswith("/id") or text.startswith("/\u6211\u7684ID") or normalized in {"\u6211\u7684id", "\u6211\u7684ID"}:
        display_user_id = user_id or "\u8b80\u53d6\u4e0d\u5230"
        display_username = username or "\u8b80\u53d6\u4e0d\u5230"
        telegram_send_message(
            chat_id,
            f"\u4f60\u7684 Telegram ID\uff1a{display_user_id}\n"
            f"\u4f60\u7684 Telegram 帳號\uff1a@{display_username}",
            message_id,
        )
        return {"ok": True, "action": "my_id", "user_id": user_id, "username": username}

    if text.startswith("/start") or text.startswith("/help") or text.startswith("/keyboard") or normalized in {"\u9078\u55ae", "\u4e3b\u9078\u55ae", "menu"}:
        return send_main_menu(chat_id, message_id)

    if text.startswith("/admin") or normalized in {"\u5f8c\u53f0", "\u5f8c\u53f0\u7db2\u5740", "\u540e\u53f0", "\u540e\u53f0\u7f51\u5740", "admin"}:
        telegram_send_message(chat_id, f"\u5f8c\u53f0\u7db2\u5740\uff1a\n{ADMIN_URL}", message_id)
        return {"ok": True, "action": "admin_url"}

    if text.startswith("/announce") or text.startswith("/\u516c\u544a") or normalized in {"\u516c\u544a", "\u7528\u6236\u516c\u544a", "\u7528\u6237\u516c\u544a"}:
        if not can_manage_bot_data(user_id, username):
            telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
            return {"ok": True, "action": "permission_denied"}
        custom_text = ""
        if text.startswith("/announce"):
            custom_text = text[len("/announce"):].strip()
        elif text.startswith("/\u516c\u544a"):
            custom_text = text[len("/\u516c\u544a"):].strip()
        announcement = custom_text or KHMER_USAGE_ANNOUNCEMENT
        result = broadcast_bot_announcement(announcement)
        telegram_send_message(
            chat_id,
            f"\u516c\u544a\u5df2\u767c\u9001\n"
            f"\u6210\u529f\uff1a{result['sent']}\n"
            f"\u5931\u6557\uff1a{result['failed']}\n"
            f"\u5df2\u8a18\u9304\u5c0d\u8c61\uff1a{result['total']}",
            message_id,
        )
        return {"ok": True, "action": "announcement", "result": result}

    if text.startswith("/\u83dc\u91d1") or text.startswith("/cost") or normalized in {"\u6bcf\u65e5\u83dc\u91d1", "\u83dc\u91d1"}:
        if not can_manage_bot_data(user_id, username):
            telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
            return {"ok": True, "action": "permission_denied"}
        return send_cost_menu(chat_id, normalize_report_date(text), message_id)

    if load_pending_bot_cost(chat_id) and not can_manage_bot_data(user_id, username):
        telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
        return {"ok": True, "action": "permission_denied"}

    cost_amount_result = handle_pending_cost_amount(chat_id, text, message_id)
    if cost_amount_result:
        return cost_amount_result

    if normalized in {"\u78ba\u8a8d", "\u786e\u8ba4", "ok", "OK"}:
        pending_cost = load_pending_bot_cost(chat_id)
        if pending_cost and "amount" in pending_cost:
            if not can_manage_bot_data(user_id, username):
                telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
                return {"ok": True, "action": "permission_denied"}
            result = save_cost({"date": pending_cost["date"], pending_cost["field"]: pending_cost["amount"]})
            clear_pending_bot_cost(chat_id)
            telegram_send_message(
                chat_id,
                f"\u5df2\u5beb\u5165\u83dc\u91d1\n"
                f"{pending_cost['date']}\n"
                f"{COST_FIELD_LABELS.get(pending_cost['field'], pending_cost['field'])}\uff1a${pending_cost['amount']:.2f}\n"
                f"\u5f8c\u53f0\u5df2\u540c\u6b65\u3002",
                message_id,
            )
            return {"ok": True, "action": "cost_saved", "result": result}
        payload = load_pending_bot_report(chat_id)
        if not payload:
            telegram_send_message(chat_id, "\u6c92\u6709\u5f85\u78ba\u8a8d\u7684\u4eba\u6578\u8cc7\u6599\uff0c\u8acb\u5148\u7528 /\u4eba\u6578 \u89e3\u6790\u5831\u9910\u6587\u5b57\u3002", message_id)
            return {"ok": True, "action": "no_pending"}
        if not can_manage_bot_data(user_id, username):
            telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
            return {"ok": True, "action": "permission_denied"}
        result = save_report(payload)
        clear_pending_bot_report(chat_id)
        telegram_send_message(
            chat_id,
            f"\u5df2\u5beb\u5165 {payload['date']} {payload['unit']} \u4eba\u6578\n\u5beb\u5165 {result['saved']} \u7b46\uff0c\u5c0f\u7a0b\u5f0f\u5df2\u540c\u6b65\u3002",
            message_id,
        )
        telegram_send_message(chat_id, delivery_table_text(payload["date"]), message_id)
        return {"ok": True, "action": "saved", "result": result}

    if normalized in {"\u53d6\u6d88", "cancel", "Cancel"}:
        clear_pending_bot_cost(chat_id)
        clear_pending_bot_report(chat_id)
        telegram_send_message(chat_id, "\u5df2\u53d6\u6d88\u9019\u6b21\u5f85\u78ba\u8a8d\u8cc7\u6599\u3002", message_id)
        return {"ok": True, "action": "cancelled"}

    if text.startswith("/test") or text.startswith("/\u6e2c\u8a66") or text.startswith("/\u6d4b\u8bd5"):
        telegram_send_message(chat_id, f"bot \u6709\u6536\u5230\u8a0a\u606f\nchat_id: {chat_id}", message_id)
        return {"ok": True, "action": "test", "chat_id": chat_id}

    if text.startswith("/menu") or text.startswith("/today") or text.startswith("/\u4eca\u65e5\u83dc\u55ae") or text.startswith("/\u83dc\u55ae") or normalized in {"\u4eca\u65e5\u83dc\u55ae", "\u83dc\u55ae"}:
        telegram_send_message(chat_id, today_menu_text(normalize_report_date(text)), message_id)
        return {"ok": True, "action": "today_menu"}

    if text.startswith("/\u7e3d\u8868") or text.startswith("/\u603b\u8868") or text.startswith("/\u9001\u9910\u8868") or text.startswith("/table") or normalized in {"\u9001\u9910\u7e3d\u8868", "\u7e3d\u8868", "\u9001\u9910\u8868"}:
        telegram_send_message(chat_id, delivery_table_text(normalize_report_date(text)), message_id)
        return {"ok": True, "action": "delivery_table"}

    if text.startswith("/\u7e3d\u6578") or text.startswith("/\u603b\u6570") or text.startswith("/total") or normalized in {"\u9001\u9910\u7e3d\u6578", "\u7e3d\u6578", "\u603b\u6570"}:
        telegram_send_message(chat_id, delivery_table_text(normalize_report_date(text)), message_id)
        return {"ok": True, "action": "employee_totals_report"}

    menu_change = parse_menu_change_command(text)
    if menu_change:
        if not can_manage_bot_data(user_id, username):
            telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
            return {"ok": True, "action": "permission_denied"}
        try:
            result = save_menu_change(menu_change)
            telegram_send_message(
                chat_id,
                f"\u5df2\u4fee\u6539\u83dc\u55ae\n"
                f"{result['date']} {result['meal_label']}\n"
                f"\u300c{result['old_dish']}\u300d \u2192 \u300c{result['new_dish']}\u300d\n"
                f"\u5c0f\u7a0b\u5f0f\u5df2\u540c\u6b65\uff0c\u83dc\u8272\u5716\u7247\u6703\u6539\u7528\u65b0\u83dc\u540d\u751f\u6210\u3002",
                message_id,
            )
            return {"ok": True, "action": "menu_changed", "result": result}
        except Exception as exc:
            telegram_send_message(chat_id, f"\u83dc\u55ae\u6c92\u6709\u4fee\u6539\uff1a{exc}", message_id)
            return {"ok": True, "action": "menu_change_failed", "error": str(exc)}

    parse_text = text
    if text.startswith("/\u4eba\u6578") or text.startswith("/\u4eba\u6570") or text.startswith("/parse") or text.startswith("/people") or normalized in {"\u4eba\u6578\u56de\u5831", "\u4eba\u6570\u56de\u62a5", "\u4eba\u6578", "\u4eba\u6570"}:
        parts = text.split(maxsplit=1)
        parse_text = parts[1] if len(parts) > 1 else reply_text
        if not parse_text or normalized in {"\u4eba\u6578\u56de\u5831", "\u4eba\u6570\u56de\u62a5", "\u4eba\u6578", "\u4eba\u6570"}:
            telegram_send_message(chat_id, people_report_help(), message_id)
            return {"ok": True, "action": "parse_help"}
        if not can_manage_bot_data(user_id, username):
            telegram_send_message(chat_id, permission_denied_text(user_id, username), message_id)
            return {"ok": True, "action": "permission_denied"}

    try:
        if not can_manage_bot_data(user_id, username):
            return {"ok": True, "ignored": "permission denied for auto parse"}
        payload = parse_bot_3f_report(parse_text)
        summary_text = summarize_bot_report(payload)
        result = save_report(payload)
        clear_pending_bot_report(chat_id)
        telegram_send_message(
            chat_id,
            f"{summary_text}\n\n\u5df2\u81ea\u52d5\u5beb\u5165 {payload['date']} {payload['unit']}\n\u5beb\u5165 {result['saved']} \u7b46\uff0c\u5c0f\u7a0b\u5f0f\u5df2\u540c\u6b65\u3002",
            message_id,
        )
        return {"ok": True, "action": "saved_auto", "date": payload["date"], "unit": payload["unit"], "entries": len(payload["entries"]), "result": result}
    except Exception as exc:
        if any(mark in text for mark in ["\u53f0\u9910", "\u80d6\u80d6", "\u67ec\u9910", "\u675f\u9910", "\u65e9\u9910", "\u5348\u9910", "\u4e2d\u9910", "\u665a\u9910", "\u5bb5\u591c", "3F", "MT", "\u5ba2\u670d"]):
            telegram_send_message(chat_id, f"\u6c92\u6709\u5beb\u5165\uff1a{exc}", message_id)
        return {"ok": True, "ignored": str(exc)}


def meal_has_beef(report_date, meal_key):
    day = load_menu().get(report_date)
    if not day:
        return False
    for meal in day.get("meals", []):
        if meal.get("key") != meal_key:
            continue
        return any("\u725b" in str(item.get("dish") or "") for item in meal.get("items", []))
    return False


def fixed_rows(report_date, rows):
    updated_pairs = {(row["unit"], row["meal_key"]) for row in rows}
    defaults = []
    for rule in fixed_reports_config():
        for meal_key, count in rule["counts"].items():
            if count <= 0 or (rule["unit"], meal_key) in updated_pairs:
                continue
            beef_count = rule.get("beef_notes", {}).get(meal_key, 0)
            note = ""
            if beef_count and meal_has_beef(report_date, meal_key):
                note = f"{beef_count}\u4f4d\u4e0d\u5403\u725b"
            defaults.append(
                {
                    "report_date": report_date,
                    "unit": rule["unit"],
                    "delivery_location": rule["location"],
                    "meal_key": meal_key,
                    "cuisine": rule["cuisine"],
                    "count": count,
                    "restrictions": "[]",
                    "note": note,
                    "updated_at": "\u6bcf\u65e5\u56fa\u5b9a",
                    "line_key": f"fixed-{rule['unit']}-{rule['location']}-{rule['cuisine']}-{meal_key}",
                }
            )
    return defaults


def summary(report_date):
    rows = db_rows(report_date)
    rows = rows + fixed_rows(report_date, rows)
    totals = {meal: {"taiwan": 0, "healthy": 0, "cambodia": 0, "total": 0} for meal in MEAL_KEYS}
    locations = {
        location: {meal: {"taiwan": 0, "healthy": 0, "cambodia": 0, "total": 0} for meal in MEAL_KEYS}
        for location in DELIVERY_LOCATIONS
    }
    units = {
        unit: {
            location: {meal: {"taiwan": 0, "healthy": 0, "cambodia": 0, "total": 0} for meal in MEAL_KEYS}
            for location in DELIVERY_LOCATIONS
        }
        for unit in FIXED_REPORT_UNITS
    }

    for row in rows:
        unit = row["unit"]
        location = row["delivery_location"]
        meal = row["meal_key"]
        cuisine = row["cuisine"]
        count = int(row["count"])
        if unit not in units or location not in locations:
            continue
        units[unit][location][meal][cuisine] += count
        units[unit][location][meal]["total"] += count
        totals[meal][cuisine] += count
        totals[meal]["total"] += count
        locations[location][meal][cuisine] += count
        locations[location][meal]["total"] += count

    reported_units = sorted({row["unit"] for row in rows})
    missing_units = [unit for unit in DEPARTMENTS if unit not in reported_units]
    return {
        "rows": rows,
        "units": units,
        "locations": locations,
        "totals": totals,
        "missing_units": missing_units,
    }


def default_cost_counts(report_date):
    totals = summary(report_date)["totals"]
    taiwan = sum(totals[meal]["taiwan"] + totals[meal]["healthy"] for meal in MEAL_KEYS)
    cambodia = sum(totals[meal]["cambodia"] for meal in MEAL_KEYS)
    return {"taiwan": taiwan, "cambodia": cambodia}


def db_cost_rows(start_date, end_date):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT report_date, taiwan_cost, cambodia_cost, taiwan_count,
                   cambodia_count, note, updated_at, counts_locked,
                   pork_cost, vegetable_cost, frozen_cost, grocery_cost,
                   gas_cost, water_cost, meal_box_cost, corner_store_cost,
                   rice_cost, ice_cost, cost_68
            FROM daily_costs
            WHERE report_date >= ? AND report_date <= ?
            ORDER BY report_date
            """,
            (start_date, end_date),
        ).fetchall()
    return {row["report_date"]: dict(row) for row in rows}


def db_month_overhead(month_key):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT month_key, rent_cost, utility_cost, labor_cost,
                   other_monthly_cost, note, updated_at
            FROM monthly_overhead_costs
            WHERE month_key = ?
            """,
            (month_key,),
        ).fetchone()
    staff = db_month_staff(month_key)
    staff_total = round(sum(float(item.get("amount") or 0) for item in staff), 2)
    if not row:
        data = {
            "month": month_key,
            "rent_cost": 0.0,
            "utility_cost": 0.0,
            "labor_cost": staff_total,
            "other_monthly_cost": 0.0,
            "note": "",
            "updated_at": "",
        }
        data["staff_count"] = len(staff)
        data["staff"] = staff
        data["total"] = staff_total
        return data
    data = dict(row)
    data["month"] = data.pop("month_key")
    data["labor_cost"] = staff_total
    data["staff_count"] = len(staff)
    data["staff"] = staff
    data["total"] = round(
        float(data.get("rent_cost") or 0)
        + float(data.get("utility_cost") or 0)
        + staff_total
        + float(data.get("other_monthly_cost") or 0),
        2,
    )
    return data


def staff_key(name, index):
    normalized = re.sub(r"\s+", "-", str(name or "").strip().lower())
    return normalized or f"staff-{index + 1}"


def db_month_staff(month_key):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT staff_key, name, role, amount, sort_order
            FROM monthly_staff_costs
            WHERE month_key = ?
            ORDER BY sort_order, staff_key
            """,
            (month_key,),
        ).fetchall()
    if rows:
        return [
            {
                "staff_key": row["staff_key"],
                "name": row["name"],
                "role": row["role"],
                "amount": float(row["amount"] or 0),
                "sort_order": int(row["sort_order"] or 0),
            }
            for row in rows
        ]
    return [
        {
            "staff_key": staff_key(item["name"], index),
            "name": item["name"],
            "role": item["role"],
            "amount": float(item["amount"]),
            "sort_order": index,
        }
        for index, item in enumerate(DEFAULT_MONTHLY_STAFF)
    ]


def save_month_staff(payload):
    month_key = str(payload.get("month") or today_key()[:7])[:7]
    raw_staff = payload.get("staff") or []
    now = datetime.now().isoformat(timespec="seconds")
    cleaned = []
    for index, item in enumerate(raw_staff):
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        if not name and not role:
            continue
        cleaned.append(
            {
                "staff_key": staff_key(name or role, index),
                "name": name or role,
                "role": role or "\u4eba\u4e8b",
                "amount": float(item.get("amount") or 0),
                "sort_order": index,
            }
        )
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM monthly_staff_costs WHERE month_key = ?", (month_key,))
        conn.executemany(
            """
            INSERT INTO monthly_staff_costs (
                month_key, staff_key, name, role, amount, sort_order, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    month_key,
                    item["staff_key"],
                    item["name"],
                    item["role"],
                    item["amount"],
                    item["sort_order"],
                    now,
                )
                for item in cleaned
            ],
        )
        conn.commit()
    return {"ok": True, "overhead": db_month_overhead(month_key)}


def save_month_overhead(payload):
    month_key = str(payload.get("month") or today_key()[:7])[:7]
    now = datetime.now().isoformat(timespec="seconds")

    def cost_value(field):
        return float(payload.get(field) or 0)

    values = (
        month_key,
        cost_value("rent_cost"),
        cost_value("utility_cost"),
        cost_value("labor_cost"),
        cost_value("other_monthly_cost"),
        str(payload.get("note") or ""),
        now,
    )
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO monthly_overhead_costs (
                month_key, rent_cost, utility_cost, labor_cost,
                other_monthly_cost, note, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(month_key) DO UPDATE SET
                rent_cost = excluded.rent_cost,
                utility_cost = excluded.utility_cost,
                labor_cost = excluded.labor_cost,
                other_monthly_cost = excluded.other_monthly_cost,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            values,
        )
        conn.commit()
    return {"ok": True, "overhead": db_month_overhead(month_key)}


def build_cost_row(report_date, stored):
    day_totals = summary(report_date)["totals"]
    meal_counts = {meal: int(day_totals[meal]["total"]) for meal in MEAL_KEYS}
    revenue = sum(meal_counts[meal] * MEAL_PRICES[meal] for meal in MEAL_KEYS)
    defaults = default_cost_counts(report_date)
    use_stored_counts = bool(stored and int(stored.get("counts_locked") or 0))
    taiwan_count = int(stored["taiwan_count"]) if use_stored_counts else defaults["taiwan"]
    cambodia_count = int(stored["cambodia_count"]) if use_stored_counts else defaults["cambodia"]
    taiwan_cost = float(stored.get("taiwan_cost") or 0) if stored else 0.0
    cambodia_cost = float(stored.get("cambodia_cost") or 0) if stored else 0.0
    supplier_costs = {
        "pork_cost": float(stored.get("pork_cost") or 0) if stored else 0.0,
        "vegetable_cost": float(stored.get("vegetable_cost") or 0) if stored else 0.0,
        "frozen_cost": float(stored.get("frozen_cost") or 0) if stored else 0.0,
        "grocery_cost": float(stored.get("grocery_cost") or 0) if stored else 0.0,
        "gas_cost": float(stored.get("gas_cost") or 0) if stored else 0.0,
        "water_cost": float(stored.get("water_cost") or 0) if stored else 0.0,
        "meal_box_cost": float(stored.get("meal_box_cost") or 0) if stored else 0.0,
        "corner_store_cost": float(stored.get("corner_store_cost") or 0) if stored else 0.0,
        "rice_cost": float(stored.get("rice_cost") or 0) if stored else 0.0,
        "ice_cost": float(stored.get("ice_cost") or 0) if stored else 0.0,
        "cost_68": float(stored.get("cost_68") or 0) if stored else 0.0,
    }
    supplier_food_cost = supplier_costs["pork_cost"] + supplier_costs["vegetable_cost"] + supplier_costs["frozen_cost"]
    other_cost = (
        supplier_costs["grocery_cost"]
        + supplier_costs["gas_cost"]
        + supplier_costs["water_cost"]
        + supplier_costs["meal_box_cost"]
        + supplier_costs["corner_store_cost"]
        + supplier_costs["rice_cost"]
        + supplier_costs["ice_cost"]
        + supplier_costs["cost_68"]
    )
    taiwan_food_cost = supplier_food_cost if supplier_food_cost else taiwan_cost
    total_cost = taiwan_food_cost + cambodia_cost
    total_expense_cost = total_cost + other_cost
    total_count = taiwan_count + cambodia_count
    avg = round(total_cost / total_count, 4) if total_count else 0
    taiwan_avg = round(taiwan_food_cost / taiwan_count, 4) if taiwan_count else 0
    cambodia_avg = round(cambodia_cost / cambodia_count, 4) if cambodia_count else 0
    return {
        "date": report_date,
        "meal_counts": meal_counts,
        "revenue": round(revenue, 2),
        "taiwan_cost": taiwan_cost,
        "cambodia_cost": cambodia_cost,
        **supplier_costs,
        "taiwan_food_cost": round(taiwan_food_cost, 2),
        "supplier_food_cost": round(supplier_food_cost, 2),
        "other_cost": round(other_cost, 2),
        "total_cost": round(total_cost, 2),
        "total_expense_cost": round(total_expense_cost, 2),
        "taiwan_count": taiwan_count,
        "cambodia_count": cambodia_count,
        "total_count": total_count,
        "average": avg,
        "taiwan_average": taiwan_avg,
        "cambodia_average": cambodia_avg,
        "over_limit": avg > 1.32 if total_count else False,
        "note": stored.get("note", "") if stored else "",
        "saved": bool(stored),
    }


def cost_report(start_date, end_date, summary_end_date=None):
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    stored = db_cost_rows(start_date, end_date)
    overhead = db_month_overhead(start_date[:7])
    rows = []
    current = start
    while current <= end:
        key = current.isoformat()
        rows.append(build_cost_row(key, stored.get(key)))
        current += timedelta(days=1)
    summary_cutoff = date.fromisoformat(summary_end_date) if summary_end_date else end
    summary_rows = [row for row in rows if date.fromisoformat(row["date"]) <= summary_cutoff]

    def empty_group(label):
        return {
            "label": label,
            "cost": 0.0,
            "other_cost": 0.0,
            "total_expense_cost": 0.0,
            "revenue": 0.0,
            "profit": 0.0,
            "count": 0,
            "average": 0.0,
            "expense_average": 0.0,
            "over_limit": False,
            "pork_cost": 0.0,
            "vegetable_cost": 0.0,
            "frozen_cost": 0.0,
            "cambodia_cost": 0.0,
            "grocery_cost": 0.0,
            "gas_cost": 0.0,
            "water_cost": 0.0,
            "meal_box_cost": 0.0,
            "corner_store_cost": 0.0,
            "rice_cost": 0.0,
            "ice_cost": 0.0,
            "cost_68": 0.0,
        }

    month = empty_group("month")
    weeks = {}
    for row in summary_rows:
        month["cost"] += row["total_cost"]
        month["other_cost"] += row["other_cost"]
        month["total_expense_cost"] += row["total_expense_cost"]
        month["revenue"] += row["revenue"]
        month["count"] += row["total_count"]
        for field in [
            "pork_cost",
            "vegetable_cost",
            "frozen_cost",
            "cambodia_cost",
            "grocery_cost",
            "gas_cost",
            "water_cost",
            "meal_box_cost",
            "corner_store_cost",
            "rice_cost",
            "ice_cost",
            "cost_68",
        ]:
            month[field] += row[field]
        row_date = date.fromisoformat(row["date"])
        period_start_day = ((row_date.day - 1) // 5) * 5 + 1
        period_end_day = min(period_start_day + 4, (date(row_date.year, row_date.month + 1, 1) - timedelta(days=1)).day) if row_date.month < 12 else min(period_start_day + 4, 31)
        period_label = f"{row_date.month}/{period_start_day}-{row_date.month}/{period_end_day}"
        weeks.setdefault(period_label, empty_group(period_label))
        weeks[period_label]["cost"] += row["total_cost"]
        weeks[period_label]["other_cost"] += row["other_cost"]
        weeks[period_label]["total_expense_cost"] += row["total_expense_cost"]
        weeks[period_label]["revenue"] += row["revenue"]
        weeks[period_label]["count"] += row["total_count"]
        for field in [
            "pork_cost",
            "vegetable_cost",
            "frozen_cost",
            "cambodia_cost",
            "grocery_cost",
            "gas_cost",
            "water_cost",
            "meal_box_cost",
            "corner_store_cost",
            "rice_cost",
            "ice_cost",
            "cost_68",
        ]:
            weeks[period_label][field] += row[field]

    for group in [month, *weeks.values()]:
        group["cost"] = round(group["cost"], 2)
        group["other_cost"] = round(group["other_cost"], 2)
        group["total_expense_cost"] = round(group["total_expense_cost"], 2)
        group["revenue"] = round(group["revenue"], 2)
        group["profit"] = round(group["revenue"] - group["total_expense_cost"], 2)
        for field in [
            "pork_cost",
            "vegetable_cost",
            "frozen_cost",
            "cambodia_cost",
            "grocery_cost",
            "gas_cost",
            "water_cost",
            "meal_box_cost",
            "corner_store_cost",
            "rice_cost",
            "ice_cost",
            "cost_68",
        ]:
            group[field] = round(group[field], 2)
        group["average"] = round(group["cost"] / group["count"], 4) if group["count"] else 0.0
        group["expense_average"] = round(group["total_expense_cost"] / group["count"], 4) if group["count"] else 0.0
        group["over_limit"] = group["average"] > 1.32 if group["count"] else False

    month["monthly_overhead_cost"] = overhead["total"]
    month["grand_total_cost"] = round(month["total_expense_cost"] + overhead["total"], 2)
    month["grand_profit"] = round(month["revenue"] - month["grand_total_cost"], 2)
    month["grand_average"] = round(month["grand_total_cost"] / month["count"], 4) if month["count"] else 0.0

    return {
        "rows": rows,
        "month": month,
        "weeks": list(weeks.values()),
        "monthly_overhead": overhead,
        "limit": 1.32,
        "summary_end_date": summary_cutoff.isoformat(),
    }


def save_cost(payload):
    report_date = str(payload.get("date") or today_key())
    now = datetime.now().isoformat(timespec="seconds")
    defaults = default_cost_counts(report_date)
    existing = db_cost_rows(report_date, report_date).get(report_date)
    has_payload_counts = bool(payload.get("lock_counts")) and (
        "taiwan_count" in payload or "cambodia_count" in payload
    )
    keep_locked_counts = bool(existing and int(existing.get("counts_locked") or 0) and not has_payload_counts)
    counts_locked = 1 if (has_payload_counts or keep_locked_counts) else 0
    taiwan_count = existing["taiwan_count"] if keep_locked_counts else (
        payload.get("taiwan_count") if "taiwan_count" in payload else defaults["taiwan"]
    )
    cambodia_count = existing["cambodia_count"] if keep_locked_counts else (
        payload.get("cambodia_count") if "cambodia_count" in payload else defaults["cambodia"]
    )
    def cost_value(field):
        if field in payload:
            return float(payload.get(field) or 0)
        if existing:
            return float(existing.get(field) or 0)
        return 0.0

    values = (
        report_date,
        cost_value("taiwan_cost"),
        cost_value("cambodia_cost"),
        int(taiwan_count or 0),
        int(cambodia_count or 0),
        str(payload.get("note") if "note" in payload else (existing.get("note") if existing else "") or "").strip(),
        now,
        counts_locked,
        cost_value("pork_cost"),
        cost_value("vegetable_cost"),
        cost_value("frozen_cost"),
        cost_value("grocery_cost"),
        cost_value("gas_cost"),
        cost_value("water_cost"),
        cost_value("meal_box_cost"),
        cost_value("corner_store_cost"),
        cost_value("rice_cost"),
        cost_value("ice_cost"),
        cost_value("cost_68"),
    )
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO daily_costs (
                report_date, taiwan_cost, cambodia_cost, taiwan_count,
                cambodia_count, note, updated_at, counts_locked,
                pork_cost, vegetable_cost, frozen_cost, grocery_cost,
                gas_cost, water_cost, meal_box_cost, corner_store_cost,
                rice_cost, ice_cost, cost_68
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date)
            DO UPDATE SET
                taiwan_cost = excluded.taiwan_cost,
                cambodia_cost = excluded.cambodia_cost,
                taiwan_count = excluded.taiwan_count,
                cambodia_count = excluded.cambodia_count,
                note = excluded.note,
                updated_at = excluded.updated_at,
                counts_locked = excluded.counts_locked,
                pork_cost = excluded.pork_cost,
                vegetable_cost = excluded.vegetable_cost,
                frozen_cost = excluded.frozen_cost,
                grocery_cost = excluded.grocery_cost,
                gas_cost = excluded.gas_cost,
                water_cost = excluded.water_cost,
                meal_box_cost = excluded.meal_box_cost,
                corner_store_cost = excluded.corner_store_cost,
                rice_cost = excluded.rice_cost,
                ice_cost = excluded.ice_cost,
                cost_68 = excluded.cost_68
            """,
            values,
        )
    return {"ok": True, "row": build_cost_row(report_date, db_cost_rows(report_date, report_date).get(report_date))}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def admin_cookie(self):
        cookies = self.headers.get("Cookie", "")
        for part in cookies.split(";"):
            key, _, value = part.strip().partition("=")
            if key == ADMIN_COOKIE:
                return value
        return ""

    def is_admin(self):
        return verify_session_cookie(self.admin_cookie())

    def require_admin(self):
        if self.is_admin():
            return True
        self.send_json({"error": "需要登入後台"}, 401)
        return False

    def send_admin_session(self, username):
        cookie = session_cookie_value(username)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Set-Cookie", f"{ADMIN_COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={ADMIN_SESSION_TTL_SECONDS}")
        body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def clear_admin_session(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Set-Cookie", f"{ADMIN_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_file(BASE_DIR / "order_app.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/admin":
            if not self.is_admin():
                self.send_file(BASE_DIR / "admin_login.html", "text/html; charset=utf-8")
                return
            self.send_file(BASE_DIR / "admin_app.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/admin/session":
            self.send_json({"authenticated": self.is_admin()})
            return
        if parsed.path == "/api/today":
            date = params.get("date", [today_key()])[0]
            menu = load_menu()
            day = menu.get(date)
            if not day:
                self.send_json({"error": f"\u627e\u4e0d\u5230 {date} \u83dc\u55ae"}, 404)
                return
            self.send_json(
                {
                    "date": date,
                    "units": DEPARTMENTS,
                    "delivery_locations": DELIVERY_LOCATIONS,
                    "unit_delivery_locations": unit_delivery_locations(),
                    "menu": day,
                    "summary": summary(date),
                }
            )
            return
        if parsed.path == "/api/summary":
            date = params.get("date", [today_key()])[0]
            self.send_json({"date": date, "summary": summary(date)})
            return
        if parsed.path == "/api/delivery-table":
            date = params.get("date", [today_key()])[0]
            meal = params.get("meal", [""])[0]
            self.send_json({"date": date, "meal": meal, "text": delivery_table_text(date, meal or None)})
            return
        if parsed.path == "/api/menu-images":
            date = params.get("date", [today_key()])[0]
            meal = params.get("meal", [""])[0]
            try:
                self.send_json(menu_images(date, meal or None))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 404)
            return
        if parsed.path == "/api/dish-image":
            dish = params.get("dish", [""])[0]
            category = params.get("category", [""])[0]
            image_path = generate_ai_dish_image(dish, category)
            if image_path:
                self.send_file(image_path, dish_image_content_type(image_path))
            else:
                body = dish_image_svg(dish, category).encode("utf-8")
                self.send_bytes(body, "image/svg+xml; charset=utf-8")
            return
        if parsed.path == "/api/costs":
            if not self.require_admin():
                return
            start_date = params.get("start", [today_key()])[0]
            end_date = params.get("end", [start_date])[0]
            summary_end_date = params.get("summary_end", [end_date])[0]
            self.send_json(cost_report(start_date, end_date, summary_end_date))
            return
        if parsed.path == "/api/admin/storage":
            if not self.require_admin():
                return
            self.send_json(storage_status())
            return
        if parsed.path == "/api/admin/fixed-reports":
            if not self.require_admin():
                return
            self.send_json({"reports": fixed_reports_config(), "units": DEPARTMENTS, "cuisines": CUISINES, "meals": MEAL_KEYS})
            return
        if parsed.path == "/api/admin/delivery-table":
            if not self.require_admin():
                return
            date = params.get("date", [today_key()])[0]
            self.send_json({"date": date, "text": delivery_table_text(date)})
            return
        if parsed.path == "/api/admin/month-menu":
            if not self.require_admin():
                return
            month = params.get("month", [today_key()[:7]])[0]
            self.send_json(month_menu(month))
            return
        if parsed.path == "/api/admin/month-overhead":
            if not self.require_admin():
                return
            month = params.get("month", [today_key()[:7]])[0]
            self.send_json(db_month_overhead(month))
            return
        if parsed.path == "/api/admin/month-staff":
            if not self.require_admin():
                return
            month = params.get("month", [today_key()[:7]])[0]
            self.send_json({"month": month, "staff": db_month_staff(month)})
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/telegram/webhook":
            if TELEGRAM_WEBHOOK_SECRET:
                header_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not hmac.compare_digest(header_secret, TELEGRAM_WEBHOOK_SECRET):
                    self.send_json({"error": "bad secret"}, 401)
                    return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(handle_telegram_update(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/login":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                username = str(payload.get("username") or "")
                password = str(payload.get("password") or "")
                valid_user = hmac.compare_digest(username, ADMIN_USERNAME)
                valid_password = hmac.compare_digest(password, ADMIN_PASSWORD)
                if not (valid_user and valid_password):
                    self.send_json({"error": "帳號或密碼錯誤"}, 401)
                    return
                self.send_admin_session(username)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/logout":
            self.clear_admin_session()
            return
        if parsed.path == "/api/cost":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(save_cost(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/fixed-reports":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(save_fixed_reports_config(payload.get("reports")))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/month-menu":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(save_menu_updates(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/month-overhead":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(save_month_overhead(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/month-staff":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self.send_json(save_month_staff(payload))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/admin/broadcast-delivery-table":
            if not self.require_admin():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                report_date = str(payload.get("date") or today_key())
                self.send_json(broadcast_delivery_table(report_date))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path != "/api/report":
            self.send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(save_report(payload))
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Meal order report app: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
