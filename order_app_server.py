import json
import os
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
MENU_PATH = BASE_DIR / "august_menu_fixed_table.json"
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
DB_PATH = DATA_DIR / "meal_order_reports.sqlite3"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8787"))

UNITS = ["1001", "1002-2", "1002-3", "68", "88", "3F"]
MEAL_KEYS = ["breakfast", "lunch", "dinner", "late_night"]
CUISINES = ["taiwan", "cambodia"]


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
                report_date TEXT NOT NULL,
                unit TEXT NOT NULL,
                meal_key TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (report_date, unit, meal_key, cuisine)
            )
            """
        )


def db_rows(report_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT report_date, unit, meal_key, cuisine, count, updated_at
            FROM reports
            WHERE report_date = ?
            ORDER BY unit, meal_key, cuisine
            """,
            (report_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_report(payload):
    report_date = str(payload.get("date") or today_key())
    unit = str(payload.get("unit") or "").strip()
    if unit not in UNITS:
        raise ValueError("單位不正確")

    entries = payload.get("entries") or []
    now = datetime.now().isoformat(timespec="seconds")
    cleaned = []
    for entry in entries:
        meal_key = str(entry.get("meal_key") or "")
        cuisine = str(entry.get("cuisine") or "")
        count = int(entry.get("count") or 0)
        if meal_key not in MEAL_KEYS:
            raise ValueError("餐別不正確")
        if cuisine not in CUISINES:
            raise ValueError("餐種不正確")
        if count < 0:
            raise ValueError("人數不能小於 0")
        cleaned.append((report_date, unit, meal_key, cuisine, count, now))

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO reports (report_date, unit, meal_key, cuisine, count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date, unit, meal_key, cuisine)
            DO UPDATE SET count = excluded.count, updated_at = excluded.updated_at
            """,
            cleaned,
        )
    return {"ok": True, "saved": len(cleaned), "updated_at": now}


def summary(report_date):
    rows = db_rows(report_date)
    totals = {
        meal: {"taiwan": 0, "cambodia": 0, "total": 0}
        for meal in MEAL_KEYS
    }
    units = {
        unit: {
            meal: {"taiwan": None, "cambodia": None}
            for meal in MEAL_KEYS
        }
        for unit in UNITS
    }
    for row in rows:
        meal = row["meal_key"]
        cuisine = row["cuisine"]
        count = int(row["count"])
        units[row["unit"]][meal][cuisine] = count
        totals[meal][cuisine] += count
        totals[meal]["total"] += count
    missing = [
        unit
        for unit, meals in units.items()
        if any(value is None for meal in meals.values() for value in meal.values())
    ]
    return {"rows": rows, "units": units, "totals": totals, "missing_units": missing}


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
                self.send_json({"error": f"找不到 {date} 菜單"}, 404)
                return
            self.send_json({"date": date, "units": UNITS, "menu": day, "summary": summary(date)})
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
    print(f"訂餐回報小程序：http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
