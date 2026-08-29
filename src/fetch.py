"""Polite, cache-first fetching of public web pages."""

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"

USER_AGENT = (
    "catbond-map/0.1 (research project on catastrophe bond fund flows; "
    "contact caropark4@gmail.com)"
)

REQUEST_DELAY_SECONDS = 2


def _cache_path(url):
    """Derive a stable, readable filename in raw/ from a URL."""
    parsed = urlparse(url)
    slug = (parsed.netloc + parsed.path).strip("/")
    slug = "".join(c if c.isalnum() or c in "-._" else "_" for c in slug)
    slug = slug[:100] or "index"
    # Short hash keeps distinct query strings from colliding on one slug.
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return RAW_DIR / f"{slug}__{digest}.html"


def fetch(url):
    """Return the HTML for url, fetching it only if not already cached.

    Cached copies in raw/ are returned as-is and never re-fetched.
    """
    path = _cache_path(url)
    if path.exists():
        print(f"[cache] {url} -> {path.name}")
        return path.read_text(encoding="utf-8")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[fetch] {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    html = response.text
    path.write_text(html, encoding="utf-8")
    print(f"[saved] {path.name} ({len(html):,} bytes)")
    return html
