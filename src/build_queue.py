"""Build the crawl work queue: family-grouped, chronologically ascending.

Order matters for correctness, not tidiness. Artemis prose references
*predecessor* deals ("the notes issued by Ursa Re in 2014, which priced at
5%"), so a deal must be parsed only after its older siblings. Ascending order
within each family guarantees the sibling registry is populated before the deal
that cites it.

Emits data/queue.csv with family, family_seq (1 = oldest in family) and
sibling_sizes: the sizes of every EARLIER deal in the same family, which are
exactly the figures at risk of bleeding into this page.
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from measure_contamination import family          # noqa: E402

# Programme names carry a generation marker -- "Windmill I / II / III Re",
# "Kilimanjaro Re / II / III", "Sanders Re III", "Residential Reinsurance 2015"
# -- so the raw family name splits one programme into several. Stripping the
# roman numeral and any embedded year merges them, which is the whole point:
# Windmill II's contaminating $46m IS Windmill I's size.
def _roman_numerals(limit=30):
    """Roman numerals 1..limit, longest first so alternation matches greedily."""
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for n in range(1, limit + 1):
        rest, buf = n, ""
        for v, sym in vals:
            while rest >= v:
                buf += sym
                rest -= v
        out.append(buf)
    return sorted(out, key=len, reverse=True)


# Programme generations run well past X: Dodeka reaches XXIV, Vitality XVII,
# Queen Street XII. A hand-written I..X alternation left each of those as its
# own family, which is exactly where the sibling registry is most needed.
ROMAN = r"\b(?:" + "|".join(_roman_numerals(30)) + r")\b"


def family_root(name):
    n = family(name)
    n = re.sub(ROMAN, " ", n)
    n = re.sub(r"\b(?:19|20)\d\d\b", " ", n)
    # Stripping the year from "Radnor Re 2020-2" leaves "Radnor Re -2"; the
    # orphaned series suffix then split 27 families across 65 deals.
    # Only an ORPHANED suffix (preceded by the space the year strip left):
    # "IBRD CAR 111-112" must keep its 112.
    n = re.sub(r"(?<=\s)[-\u2013]\s*\d+[A-Za-z]?\b", " ", n)
    return re.sub(r"\s+", " ", n).strip(" ,-\u2013")

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def month_ordinal(date_text):
    parts = str(date_text).split()
    if len(parts) != 2:
        return 0
    return int(parts[1]) * 12 + MONTHS.get(parts[0], 0)


def main():
    df = pd.read_csv(ROOT / "data" / "index.csv", keep_default_na=False, dtype=str)
    df["family"] = df.issuer_name.map(family_root)
    df["ord"] = df.date_text.map(month_ordinal)
    df["year"] = df.date_text.str[-4:].astype(int)
    df["decade"] = df.year // 10 * 10

    # Families ordered by their earliest deal; deals ascending within family.
    # The directory lists newest-first, so within one month the site order is
    # backwards. Without this tiebreak Eclipse's Oct 2021 siblings emerge
    # 08A, 07A, 06A, 05A and the registry treats later deals as ancestors.
    df["site_pos"] = range(len(df))
    first = df.groupby("family")["ord"].min().rename("family_first")
    df = df.join(first, on="family").sort_values(
        ["family_first", "family", "ord", "site_pos"],
        ascending=[True, True, True, False], kind="stable").reset_index(drop=True)
    df["family_seq"] = df.groupby("family").cumcount() + 1
    df["family_size"] = df.groupby("family")["family"].transform("size")

    # A "family" of transformer cells (Seaside Re x69, Eclipse Re x59, Artex,
    # Dodeka ...) shares a vehicle, not a sponsor or a programme. Its prose
    # never cites an earlier cell, so it is not a sibling family for the
    # registry: no sibling sizes are recorded for it.
    unknown_share = (df.sponsor.str.strip().str.lower() == "unknown").groupby(df.family).transform("mean")
    df["family_kind"] = "programme"
    df.loc[(df.family_size >= 5) & (unknown_share >= 0.5), "family_kind"] = "platform"

    # Sizes of earlier siblings: the figures most likely to contaminate.
    sib = []
    for fam, grp in df.groupby("family", sort=False):
        seen = []
        for _, r in grp.iterrows():
            sib.append((r.deal_url, "" if r.family_kind == "platform" else "|".join(seen)))
            seen.append(r.size_text)
    sib = dict(sib)
    df["sibling_sizes"] = df.deal_url.map(sib)

    cols = ["family", "family_kind", "family_seq", "family_size", "issuer_name", "sponsor",
            "size_text", "date_text", "year", "decade", "deal_url", "sibling_sizes"]
    df[cols].to_csv(ROOT / "data" / "queue.csv", index=False, encoding="utf-8")
    print("wrote data/queue.csv  %d rows" % len(df))
    print("platform families: %d (%d deals)" % (
        df[df.family_kind == "platform"].family.nunique(),
        (df.family_kind == "platform").sum()))
    print("\nfirst 8 of the queue (oldest families first):")
    print(df[["family", "family_seq", "issuer_name", "date_text"]]
          .head(8).to_string(index=False))
    multi = df[df.family_size > 1]
    print("\n%d deals in %d serial families; %d have >=1 earlier sibling"
          % (len(multi), multi.family.nunique(), (df.family_seq > 1).sum()))
    print("\nexample with sibling context:")
    w = df[df.family.str.contains("Windmill")][
        ["family", "family_seq", "issuer_name", "size_text", "sibling_sizes"]]
    print(w.to_string(index=False))


if __name__ == "__main__":
    main()
