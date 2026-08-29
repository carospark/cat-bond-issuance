"""Parse the cached deal-directory index into data/index.csv.

Raw strings only: size and date are kept exactly as published.
"""

import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import fetch

URL = "https://www.artemis.bm/deal-directory/"
OUT = Path(__file__).resolve().parent.parent / "data" / "index.csv"

COLUMNS = ["issuer_name", "deal_url", "sponsor", "size_text", "date_text"]


def parse_index(html):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="table-deal")
    if table is None:
        raise SystemExit("could not find table#table-deal")

    records = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:  # skips the header row, which uses <th>
            continue
        issuer, cedent, _perils, size, date = cells[:5]
        link = issuer.find("a", href=True)
        records.append(
            {
                "issuer_name": issuer.get_text(" ", strip=True),
                "deal_url": urljoin(URL, link["href"]) if link else "",
                "sponsor": cedent.get_text(" ", strip=True),
                "size_text": size.get_text(" ", strip=True),
                "date_text": date.get_text(" ", strip=True),
            }
        )
    return pd.DataFrame(records, columns=COLUMNS)


def main():
    df = parse_index(fetch(URL))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8")

    print(f"\nwrote {OUT}")
    print(f"row count: {len(df)}")

    print("\n=== FIRST 15 ROWS ===")
    with pd.option_context("display.max_colwidth", 44, "display.width", 250):
        print(df.head(15).to_string())

    print("\n=== ROWS WITH AN EMPTY FIELD ===")
    blank = df.apply(lambda c: c.astype(str).str.strip() == "")
    bad = df[blank.any(axis=1)]
    if bad.empty:
        print("none — every field populated in all rows")
    else:
        print(f"{len(bad)} row(s):")
        with pd.option_context("display.max_colwidth", 44, "display.width", 250):
            print(bad.to_string())
        print("\nempty count by column:")
        print(blank.sum()[blank.sum() > 0].to_string())


if __name__ == "__main__":
    main()
