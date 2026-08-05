import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
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

DEPARTMENTS = ["1001", "1002-2\u4ee3\u7406", "1002-3\u91d1\u6d41", "3F", "\u4fdd\u59c6\u90e8\u9580", "\u6d77\u5357\u96de\u98ef", "1002-2\u5ba2\u670d"]
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
CUISINES = ["taiwan", "healthy", "cambodia"]
FIXED_REPORTS = [
    {
        "unit": "1001",
        "location": "\u90e8\u9580\u73fe\u5834",
        "cuisine": "taiwan",
        "counts": {"breakfast": 10, "lunch": 40, "dinner": 40, "late_night": 40},
        "beef_notes": {"lunch": 10, "dinner": 10, "late_night": 10},
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
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


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
        }
        for column, definition in expense_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE daily_costs ADD COLUMN {column} {definition}")


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
            ORDER BY unit, meal_key, delivery_location, cuisine
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
    for rule in FIXED_REPORTS:
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
        for unit in DEPARTMENTS
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
                   rice_cost, ice_cost
            FROM daily_costs
            WHERE report_date >= ? AND report_date <= ?
            ORDER BY report_date
            """,
            (start_date, end_date),
        ).fetchall()
    return {row["report_date"]: dict(row) for row in rows}


def build_cost_row(report_date, stored):
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
    )
    total_cost = supplier_food_cost if supplier_food_cost else taiwan_cost + cambodia_cost
    total_expense_cost = total_cost + other_cost
    total_count = taiwan_count + cambodia_count
    avg = round(total_cost / total_count, 4) if total_count else 0
    return {
        "date": report_date,
        "taiwan_cost": taiwan_cost,
        "cambodia_cost": cambodia_cost,
        **supplier_costs,
        "supplier_food_cost": round(supplier_food_cost, 2),
        "other_cost": round(other_cost, 2),
        "total_cost": round(total_cost, 2),
        "total_expense_cost": round(total_expense_cost, 2),
        "taiwan_count": taiwan_count,
        "cambodia_count": cambodia_count,
        "total_count": total_count,
        "average": avg,
        "over_limit": avg > 1.32 if total_count else False,
        "note": stored.get("note", "") if stored else "",
        "saved": bool(stored),
    }


def cost_report(start_date, end_date):
    from datetime import date, timedelta

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    stored = db_cost_rows(start_date, end_date)
    rows = []
    current = start
    while current <= end:
        key = current.isoformat()
        rows.append(build_cost_row(key, stored.get(key)))
        current += timedelta(days=1)

    def empty_group(label):
        return {
            "label": label,
            "cost": 0.0,
            "other_cost": 0.0,
            "total_expense_cost": 0.0,
            "count": 0,
            "average": 0.0,
            "expense_average": 0.0,
            "over_limit": False,
        }

    month = empty_group("month")
    weeks = {}
    for row in rows:
        month["cost"] += row["total_cost"]
        month["other_cost"] += row["other_cost"]
        month["total_expense_cost"] += row["total_expense_cost"]
        month["count"] += row["total_count"]
        row_date = date.fromisoformat(row["date"])
        period_start_day = ((row_date.day - 1) // 5) * 5 + 1
        period_end_day = min(period_start_day + 4, (date(row_date.year, row_date.month + 1, 1) - timedelta(days=1)).day) if row_date.month < 12 else min(period_start_day + 4, 31)
        period_label = f"{row_date.month}/{period_start_day}-{row_date.month}/{period_end_day}"
        weeks.setdefault(period_label, empty_group(period_label))
        weeks[period_label]["cost"] += row["total_cost"]
        weeks[period_label]["other_cost"] += row["other_cost"]
        weeks[period_label]["total_expense_cost"] += row["total_expense_cost"]
        weeks[period_label]["count"] += row["total_count"]

    for group in [month, *weeks.values()]:
        group["cost"] = round(group["cost"], 2)
        group["other_cost"] = round(group["other_cost"], 2)
        group["total_expense_cost"] = round(group["total_expense_cost"], 2)
        group["average"] = round(group["cost"] / group["count"], 4) if group["count"] else 0.0
        group["expense_average"] = round(group["total_expense_cost"] / group["count"], 4) if group["count"] else 0.0
        group["over_limit"] = group["average"] > 1.32 if group["count"] else False

    return {"rows": rows, "month": month, "weeks": list(weeks.values()), "limit": 1.32}


def save_cost(payload):
    report_date = str(payload.get("date") or today_key())
    now = datetime.now().isoformat(timespec="seconds")
    defaults = default_cost_counts(report_date)
    existing = db_cost_rows(report_date, report_date).get(report_date)
    has_payload_counts = "taiwan_count" in payload or "cambodia_count" in payload
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
                rice_cost, ice_cost
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ice_cost = excluded.ice_cost
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
        if parsed.path == "/api/costs":
            if not self.require_admin():
                return
            start_date = params.get("start", [today_key()])[0]
            end_date = params.get("end", [start_date])[0]
            self.send_json(cost_report(start_date, end_date))
            return
        if parsed.path == "/api/admin/storage":
            if not self.require_admin():
                return
            self.send_json(storage_status())
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
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
