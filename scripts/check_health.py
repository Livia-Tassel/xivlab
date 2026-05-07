#!/usr/bin/env python3
"""Smoke test the running app's /health endpoint.

Exits 0 on healthy, 1 on any non-200 or unexpected payload, 2 on error
reaching the URL. Defaults to the configured ``app_base_url``; pass any
URL as the first positional argument to override.

Usage::

    uv run python scripts/check_health.py
    uv run python scripts/check_health.py https://xivlab.example.com
"""

from __future__ import annotations

import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import get_settings


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else get_settings().app_base_url
    url = base.rstrip("/") + "/health"
    try:
        with urlopen(Request(url), timeout=5) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except URLError as exc:
        print(f"error: could not reach {url}: {exc}", file=sys.stderr)
        return 2

    if status != 200:
        print(f"error: {url} returned status {status}: {body}", file=sys.stderr)
        return 1

    if '"status":"ok"' not in body.replace(" ", ""):
        print(f"error: unexpected health body: {body}", file=sys.stderr)
        return 1

    print(f"ok: {url} -> {body}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
