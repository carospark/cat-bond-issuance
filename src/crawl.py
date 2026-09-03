"""Fetch every deal page in the queue that is not already cached.

Order comes from data/queue.csv -- family-grouped, chronologically ascending --
because prose cites predecessor deals, so ancestors must be on disk before
descendants are parsed. fetch() is cache-first and sleeps 2s before each real
request, so this is resumable: rerunning skips everything already cached.
"""

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch, _cache_path                    # noqa: E402


def main():
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    todo = [r.deal_url for _, r in q.iterrows() if not _cache_path(r.deal_url).exists()]
    print("queue: %d deals, %d already cached, %d to fetch (~%.0f min)"
          % (len(q), len(q) - len(todo), len(todo), len(todo) * 2.2 / 60), flush=True)

    start, ok, fail = time.time(), 0, []
    for i, url in enumerate(todo, 1):
        try:
            fetch(url)
            ok += 1
        except Exception as exc:                         # noqa: BLE001
            fail.append((url, "%s: %s" % (type(exc).__name__, exc)))
        if i % 50 == 0:
            el = time.time() - start
            print("  %d/%d  ok=%d fail=%d  %.1f min elapsed, ~%.0f min left"
                  % (i, len(todo), ok, len(fail), el / 60,
                     el / i * (len(todo) - i) / 60), flush=True)

    print("\nDONE: %d fetched, %d failed" % (ok, len(fail)), flush=True)
    for url, err in fail[:20]:
        print("  FAIL %s  %s" % (url, err[:80]), flush=True)
    if fail:
        pd.DataFrame(fail, columns=["deal_url", "error"]).to_csv(
            ROOT / "data" / "crawl_failures.csv", index=False)


if __name__ == "__main__":
    main()
