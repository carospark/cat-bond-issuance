"""One-off inspection of the Artemis deal directory page. No parsing to CSV yet."""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import fetch

URL = "https://www.artemis.bm/deal-directory/"


def main():
    html = fetch(URL)
    soup = BeautifulSoup(html, "lxml")

    print("\n" + "=" * 70)
    print("(a) PAGE TITLE")
    print("=" * 70)
    print(soup.title.get_text(strip=True) if soup.title else "<no title>")

    tables = soup.find_all("table")
    print("\n" + "=" * 70)
    print("(b) TABLE COUNT")
    print("=" * 70)
    print(f"{len(tables)} <table> element(s)")

    print("\n" + "=" * 70)
    print("(c) FIRST 20 ROWS OF LARGEST TABLE")
    print("=" * 70)
    if not tables:
        print("no tables found")
    else:
        largest = max(tables, key=lambda t: len(t.find_all("tr")))
        rows = largest.find_all("tr")
        print(f"largest table has {len(rows)} <tr> rows; showing first 20:\n")
        for i, row in enumerate(rows[:20]):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            print(f"{i:>3}: {cells}")

    print("\n" + "=" * 70)
    print('(d) FIRST 10 HREFS CONTAINING "/deal-directory/"')
    print("=" * 70)
    seen, hits = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/deal-directory/" in href and href not in seen:
            seen.add(href)
            hits.append(href)
        if len(hits) == 10:
            break
    for i, href in enumerate(hits):
        print(f"{i:>3}: {href}")
    if not hits:
        print("none found")


if __name__ == "__main__":
    main()
