import json
from pathlib import Path

import httpx

CONFIG_DIR = Path.home() / ".config" / "pymp3dl"
COOKIE_FILE = CONFIG_DIR / "cookies.json"


def load_cookies() -> dict[str, str]:
    if not COOKIE_FILE.exists():
        return {}
    try:
        result: dict[str, str] = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError):
        return {}


def save_cookies(cookies: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")


def set_cookie(name: str, value: str) -> None:
    cookies = load_cookies()
    cookies[name] = value
    save_cookies(cookies)


def delete_cookie(name: str) -> None:
    cookies = load_cookies()
    cookies.pop(name, None)
    save_cookies(cookies)


def clear_cookies() -> None:
    save_cookies({})


def cookies_to_httpx(cookies: dict[str, str]) -> httpx.Cookies:
    jar = httpx.Cookies()
    for name, value in cookies.items():
        jar.set(name, value, domain="downloads.khinsider.com")
    return jar


def import_netscape_cookies(path: str) -> None:
    """Parse a Netscape-format cookie file and merge into stored cookies."""
    cookies: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    existing = load_cookies()
    existing.update(cookies)
    save_cookies(existing)


def import_json_cookies(path: str) -> None:
    """Merge a JSON {name: value} cookie file into stored cookies."""
    with open(path, encoding="utf-8") as fh:
        incoming: dict[str, str] = json.load(fh)
    existing = load_cookies()
    existing.update(incoming)
    save_cookies(existing)
