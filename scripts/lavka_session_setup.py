"""Manually paste a Lavka Cookie header locally; never reads a browser store."""
import getpass
import json
import os
from http.cookies import SimpleCookie
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / "outputs/lavka-private/config.json"
    if target.exists():
        raise SystemExit("Config already exists; it was not overwritten.")
    raw = getpass.getpass("Lavka Cookie header (hidden input): ")
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    parsed = SimpleCookie()
    try:
        parsed.load(raw)
    except Exception:
        raise SystemExit("Invalid Cookie header; nothing saved.") from None
    cookies = {key: value.value for key, value in parsed.items()}
    if not (cookies.get("Session_id") or cookies.get("Session_id2")):
        raise SystemExit("No signed-in Yandex session found; nothing saved.")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump({"cookies": cookies, "location": {}, "context": {"webCity": "2"}}, output)
    print("Saved locally with owner-only permissions. Do not share or commit this file.")


if __name__ == "__main__":
    main()
