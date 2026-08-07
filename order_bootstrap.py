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


def search(pattern, string, flags=0):
    normalized = _normalized(string)
    if pattern == r"(\d{1,2})\s*/\s*(\d{1,2})":
        result = _original_search(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\s*/)", normalized, flags)
        if result is None:
            result = _original_search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|號|号)?", normalized, flags)
        return result
    return _original_search(pattern, normalized, flags)


def findall(pattern, string, flags=0):
    return _original_findall(pattern, _normalized(string), flags)


def sub(pattern, repl, string, count=0, flags=0):
    return _original_sub(pattern, repl, _normalized(string), count, flags)


_re.search = search
_re.findall = findall
_re.sub = sub


from order_app_server import main


if __name__ == "__main__":
    main()
