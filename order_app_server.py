import json
import json
import os
import sqlite3
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

DEPARTMENTS = ["1001", "1002-2\u4ee3\u7406", "1002-3", "3F", "\u4fdd\u59c6\u90e8\u9580", "\u6d77\u5357\u96de\u98ef", "1002-2\u5ba2\u670d"]
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


def allowed_delivery_locations(unit):
    if unit == "3F":
        return DELIVERY_LOCATIONS[2:]
    if unit == "1002-2\u5ba2\u670d":
        return ["1002-2"]
    return [DELIVERY_LOCATIONS[0]]


def load_menu():
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


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


def summary(report_date):
    rows = db_rows(report_date)
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_file(BASE_DIR / "order_app.html", "text/html; charset=utf-8")
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
                    "menu": day,
                    "summary": summary(date),
                }
            )
            return
        if parsed.path == "/api/summary":
            date = params.get("date", [today_key()])[0]
            self.send_json({"date": date, "summary": summary(date)})
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
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
