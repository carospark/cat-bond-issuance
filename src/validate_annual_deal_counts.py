"""Smoke-test the deal-directory crawl against Artemis annual deal counts.

This deliberately validates counts only.  It does not parse or convert deal
sizes, and it does not claim that the full Deal Directory has the same market
scope as the Artemis cumulative-issuance dashboard.  Artemis excludes mortgage
ILS from that dashboard, while ``data/index.csv`` contains the full directory.

Outputs are local because they contain data derived from Artemis:

    data/annual_deal_count_validation.csv
    plots/annual_deal_count_validation.png
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fetch import fetch  # noqa: E402


REFERENCE_URL = (
    "https://www.artemis.bm/dashboard/cat-bonds-ils-cumulative-issuance/"
)
DEFAULT_INDEX = ROOT / "data" / "index.csv"
DEFAULT_CSV = ROOT / "data" / "annual_deal_count_validation.csv"
DEFAULT_PLOT = ROOT / "plots" / "annual_deal_count_validation.png"


@dataclass(frozen=True)
class DashboardReference:
    counts: pd.DataFrame
    modified_at: Optional[str]


def parse_dashboard_reference(html: str) -> DashboardReference:
    """Extract year and transaction-count arrays from the dashboard script."""
    categories = re.search(
        r"categories\s*:\s*\[(?P<values>.*?)\]", html, re.DOTALL
    )
    transactions = re.search(
        r"name\s*:\s*['\"]No\.\s*of\s*Transactions['\"]"
        r".*?data\s*:\s*\[(?P<values>.*?)\]",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if categories is None or transactions is None:
        raise ValueError(
            "could not find Artemis year/count arrays; the dashboard markup changed"
        )

    years = [int(x) for x in re.findall(r"['\"](\d{4})['\"]", categories["values"])]
    try:
        counts = [
            int(float(x.strip()))
            for x in transactions["values"].split(",")
            if x.strip()
        ]
    except ValueError as exc:
        raise ValueError("Artemis transaction counts are not numeric") from exc

    if not years or len(years) != len(counts):
        raise ValueError(
            "Artemis dashboard arrays have different lengths: "
            f"{len(years)} years and {len(counts)} counts"
        )
    if len(years) != len(set(years)):
        raise ValueError("Artemis dashboard contains duplicate years")

    modified = re.search(r'"dateModified"\s*:\s*"([^"]+)"', html)
    frame = pd.DataFrame(
        {"year": years, "artemis_dashboard_count": counts}
    ).sort_values("year", ignore_index=True)
    return DashboardReference(frame, modified.group(1) if modified else None)


def count_directory_deals(index: pd.DataFrame) -> pd.DataFrame:
    """Return unique Deal Directory URLs per year, failing on structural errors."""
    required = {"deal_url", "date_text"}
    missing = sorted(required - set(index.columns))
    if missing:
        raise ValueError(f"index is missing required column(s): {', '.join(missing)}")

    blank_url = index["deal_url"].isna() | index["deal_url"].astype(str).str.strip().eq("")
    if blank_url.any():
        raise ValueError(f"index contains {int(blank_url.sum())} blank deal URL(s)")

    duplicate_url = index["deal_url"].duplicated(keep=False)
    if duplicate_url.any():
        examples = index.loc[duplicate_url, "deal_url"].drop_duplicates().head(3).tolist()
        raise ValueError(
            f"index contains {index['deal_url'].duplicated().sum()} duplicate deal URL(s): "
            + ", ".join(examples)
        )

    parsed_dates = pd.to_datetime(index["date_text"], format="%b %Y", errors="coerce")
    if parsed_dates.isna().any():
        examples = index.loc[parsed_dates.isna(), "date_text"].astype(str).head(5).tolist()
        raise ValueError(
            f"index contains {int(parsed_dates.isna().sum())} invalid date(s): "
            + ", ".join(examples)
        )

    counted = index.assign(year=parsed_dates.dt.year).groupby("year", as_index=False).agg(
        directory_count=("deal_url", "nunique")
    )
    return counted.sort_values("year", ignore_index=True)


def compare_counts(
    directory_counts: pd.DataFrame, dashboard_counts: pd.DataFrame
) -> pd.DataFrame:
    """Align both universes and label missing rows versus expected scope gaps."""
    result = dashboard_counts.merge(directory_counts, on="year", how="outer").sort_values(
        "year", ignore_index=True
    )
    for column in ("artemis_dashboard_count", "directory_count"):
        result[column] = result[column].fillna(0).astype(int)

    result["directory_minus_dashboard"] = (
        result["directory_count"] - result["artemis_dashboard_count"]
    )
    result["result"] = "MATCH"
    result.loc[result["directory_minus_dashboard"] > 0, "result"] = "SCOPE_GAP"
    result.loc[result["directory_minus_dashboard"] < 0, "result"] = "FAIL_MISSING"
    return result[
        [
            "year",
            "directory_count",
            "artemis_dashboard_count",
            "directory_minus_dashboard",
            "result",
        ]
    ]


def write_plot(result: pd.DataFrame, output: Path, modified_at: Optional[str]) -> None:
    """Plot dashboard-scope counts plus the full-directory surplus."""
    # The default user cache is not writable in every managed environment.
    # Keep plotting caches local and gitignored so chart generation is quiet
    # and repeatable without touching user-level state.
    cache_root = ROOT / ".cache"
    (cache_root / "matplotlib").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))

    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    output.parent.mkdir(parents=True, exist_ok=True)
    years = result["year"]
    dashboard = result["artemis_dashboard_count"]
    positive_gap = result["directory_minus_dashboard"].clip(lower=0)
    missing = result["directory_minus_dashboard"] < 0

    fig, ax = plt.subplots(figsize=(14, 7))
    dashboard_bars = ax.bar(
        years,
        dashboard,
        width=0.78,
        color="#173f5f",
        label="Artemis dashboard count",
    )
    gap_bars = ax.bar(
        years,
        positive_gap,
        width=0.78,
        bottom=dashboard,
        color="#8ecae6",
        label="Additional Deal Directory rows (scope gap)",
    )
    directory_line = ax.plot(
        years,
        result["directory_count"],
        color="#111827",
        linewidth=1.25,
        marker="o",
        markersize=3.5,
        label="Parsed Deal Directory total",
    )
    if missing.any():
        ax.scatter(
            result.loc[missing, "year"],
            result.loc[missing, "directory_count"],
            color="#b91c1c",
            marker="x",
            s=70,
            linewidths=2,
            label="Missing from parsed directory",
            zorder=5,
        )

    shortfall_years = int(missing.sum())
    total_directory = int(result["directory_count"].sum())
    total_dashboard = int(result["artemis_dashboard_count"].sum())
    scope_gap = total_directory - total_dashboard
    verdict = "PASS" if shortfall_years == 0 else "FAIL"

    ax.set_title(
        "Annual Deal Count Validation",
        loc="left",
        fontsize=18,
        weight="bold",
        pad=42,
    )
    ax.text(
        0,
        1.015,
        f"Smoke test {verdict}: {shortfall_years} year(s) below Artemis dashboard count  |  "
        f"Directory {total_directory:,} vs dashboard {total_dashboard:,} "
        f"({scope_gap:+,} scope gap)",
        transform=ax.transAxes,
        fontsize=10.5,
        color="#374151" if verdict == "PASS" else "#b91c1c",
        va="bottom",
    )
    ax.set_xlabel("Issue year")
    ax.set_ylabel("Number of transactions")
    ax.set_xticks(years.iloc[::2])
    ax.tick_params(axis="x", rotation=45)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color="#d1d5db", linewidth=0.7, alpha=0.65)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(
        [dashboard_bars, gap_bars, directory_line[0]],
        [
            "Artemis dashboard count",
            "Additional Deal Directory rows (scope gap)",
            "Parsed Deal Directory total",
        ],
        frameon=False,
        ncols=2,
        loc="upper left",
    )

    date_note = f"; dashboard modified {modified_at[:10]}" if modified_at else ""
    fig.text(
        0.01,
        0.01,
        "Source: local Artemis Deal Directory index and Artemis cumulative-issuance "
        "dashboard. Dashboard excludes mortgage ILS; directory count is unfiltered"
        + date_note
        + ".",
        fontsize=8.5,
        color="#4b5563",
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--reference-html",
        type=Path,
        help="Use a saved dashboard page instead of the cache-first fetcher.",
    )
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-plot", type=Path, default=DEFAULT_PLOT)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not args.index.exists():
        raise SystemExit(f"missing {args.index}; run src/parse_index.py first")

    html = (
        args.reference_html.read_text(encoding="utf-8")
        if args.reference_html
        else fetch(REFERENCE_URL)
    )
    reference = parse_dashboard_reference(html)
    directory = count_directory_deals(pd.read_csv(args.index))
    result = compare_counts(directory, reference.counts)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_csv, index=False)
    write_plot(result, args.output_plot, reference.modified_at)

    missing = result[result["result"] == "FAIL_MISSING"]
    exact = int((result["result"] == "MATCH").sum())
    scope_gap = int(result["directory_minus_dashboard"].clip(lower=0).sum())
    print(f"wrote {args.output_csv}")
    print(f"wrote {args.output_plot}")
    print(
        f"directory={result['directory_count'].sum():,} "
        f"dashboard={result['artemis_dashboard_count'].sum():,} "
        f"scope_gap={scope_gap:,} exact_years={exact}/{len(result)}"
    )
    if missing.empty:
        print("PASS: no year has fewer parsed directory deals than the Artemis dashboard")
        return 0

    print("FAIL: parsed directory is below Artemis in year(s):")
    print(missing[["year", "directory_minus_dashboard"]].to_string(index=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
