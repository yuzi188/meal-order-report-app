import os
import re as _re
import time
import unicodedata


os.environ["TZ"] = "Asia/Taipei"
if hasattr(time, "tzset"):
    time.tzset()


_original_search = _re.search
_original_findall = _re.findall
_original_sub = _re.sub


def _normalized(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    return value


def _date_match(value):
    normalized = _normalized(value)
    return (
        _original_search(r"(?<!\d)(20\d{2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})(?!\d)", normalized)
        or _original_search(r"(?<!\d)(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|號|号)?", normalized)
        or _original_search(r"(?<!\d)(\d{1,2})\s*[/.-]\s*(\d{1,2})(?!\s*/)", normalized)
        or _original_search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|號|号)?", normalized)
    )


def search(pattern, string, flags=0):
    normalized = _normalized(string)
    if pattern == r"(\d{1,2})\s*/\s*(\d{1,2})":
        return _date_match(normalized)
    return _original_search(pattern, normalized, flags)


def findall(pattern, string, flags=0):
    return _original_findall(pattern, _normalized(string), flags)


def sub(pattern, repl, string, count=0, flags=0):
    return _original_sub(pattern, repl, _normalized(string), count, flags)


_re.search = search
_re.findall = findall
_re.sub = sub


import order_app_server as _app


_original_parse_bot_3f_report = _app.parse_bot_3f_report


def parse_bot_3f_report(text):
    if not _date_match(text):
        raise ValueError("人數回報請加日期，例如：8/8 餐盒")
    return _original_parse_bot_3f_report(text)


_app.parse_bot_3f_report = parse_bot_3f_report
main = _app.main


if __name__ == "__main__":
    main()
