"""Polite, cache-first fetching of public web pages."""

import hashlib
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"

USER_AGENT = (
    "cat-bond-issuance/0.1 (research project on catastrophe bond issuance data; "
    "contact caropark4@gmail.com)"
)

REQUEST_DELAY_SECONDS = 2

DEAL_DIRECTORY_URL = "https://www.artemis.bm/deal-directory/"

# Set ARTEMIS_OFFLINE=1 to make any cache miss an error instead of a request.
# Reviews and tests are meant to run without touching the network; this makes
# the claim checkable rather than declared.
OFFLINE_ENV = "ARTEMIS_OFFLINE"


def _normalise(url):
    """Canonical form for cache identity.

    The cache key hashed the verbatim URL, so ".../slug" and ".../slug/" were
    different entries and the same page could be fetched twice. Trailing slash
    and fragment are not part of a page's identity here.
    """
    parsed = urlparse(url)
    # Scheme and host are case-insensitive; a query string never selects a
    # different Artemis page. NOTE: every change here re-keys raw/ -- migrate
    # (rename) the cached files in the same commit, or the whole cache is
    # silently re-fetched.
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(),
                           path=parsed.path.rstrip("/"), query="",
                           fragment="").geturl()


def _cache_path(url):
    """Derive a stable, readable filename in raw/ from a URL."""
    url = _normalise(url)
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

    if os.environ.get(OFFLINE_ENV):
        raise FileNotFoundError(
            f"{OFFLINE_ENV} is set and {url} is not cached ({path.name})")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[fetch] {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    html = response.text
    path.write_text(html, encoding="utf-8")
    print(f"[saved] {path.name} ({len(html):,} bytes)")
    return html
