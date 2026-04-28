import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.dates as mdates
from matplotlib.ticker import FixedLocator, MaxNLocator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from utils import load_satd_dataset


def compute_prevalence_df(satd: pd.DataFrame) -> pd.DataFrame:
    working = satd.copy()
    working["introducing_dt"] = pd.to_datetime(working["introducing_date"], errors="coerce", utc=True)
    working["deleting_dt"] = pd.to_datetime(working["deleting_date"], errors="coerce", utc=True)
    working["status_norm"] = working["status"].astype(str).str.upper().str.strip()

    start_dt = working["introducing_dt"].dropna().min()
    end_candidates = [working["introducing_dt"].dropna().max(), working["deleting_dt"].dropna().max()]
    end_candidates = [dt for dt in end_candidates if pd.notna(dt)]
    end_dt = max(end_candidates) if end_candidates else start_dt

    start_dt = start_dt.tz_convert("UTC") if start_dt.tzinfo else start_dt.tz_localize("UTC")
    end_dt = end_dt.tz_convert("UTC") if end_dt.tzinfo else end_dt.tz_localize("UTC")
    start_dt = start_dt.normalize()
    end_dt = end_dt.normalize()

    months = pd.date_range(start=start_dt, end=end_dt, freq="MS", tz="UTC")
    if months.empty:
        months = pd.DatetimeIndex([start_dt])
    month_ends = months + pd.offsets.MonthEnd(1)

    active_rows = []
    for month_start, month_end in zip(months, month_ends):
        active_mask = (
            (working["introducing_dt"] <= month_end)
            & (
                working["deleting_dt"].isna()
                | (working["deleting_dt"] > month_end)
                | working["status_norm"].eq("ACTIVE")
            )
        )
        active_total = int(active_mask.sum())
        if active_total == 0:
            active_rows.append(
                {"month": month_start, "active_total": 0, "active_llm": 0, "fraction": np.nan}
            )
            continue
        active_llm = int(working.loc[active_mask, "is_llm_satd"].sum())
        active_rows.append(
            {
                "month": month_start,
                "active_total": active_total,
                "active_llm": active_llm,
                "fraction": active_llm / active_total if active_total else np.nan,
            }
        )

    prevalence_df = pd.DataFrame(active_rows)
    prevalence_df["fraction_pct"] = prevalence_df["fraction"] * 100
    prevalence_df.sort_values("month", inplace=True)
    return prevalence_df


def build_prevalence_plot(prevalence_df: pd.DataFrame, output_dir: Path) -> Path:
    plot_df = prevalence_df.dropna(subset=["fraction_pct"]).copy()

    plot_df["month"] = plot_df["month"].dt.tz_convert(None)
    plot_df.reset_index(drop=True, inplace=True)

    fig, ax = plt.subplots(figsize=(11.5, 6.1))
    sns.set(style="whitegrid")

    line_color = "#1f4eaa"
    marker_color = "#6d8fe5"

    ax.plot(
        plot_df["month"],
        plot_df["fraction_pct"],
        color=line_color,
        linewidth=1.5,
        marker="o",
        markersize=5,
        markerfacecolor=marker_color,
        markeredgecolor="white",
        alpha=0.9,
    )

    ax.set_ylabel("LLM-SATD Proportion (%)", fontdict={"weight": "bold"})
    ax.set_xlabel("Month", fontdict={"weight": "bold"})

    first_month = plot_df["month"].min().normalize()
    last_month = plot_df["month"].max().normalize()
    quarter_starts = pd.date_range(first_month, last_month, freq="QS-JAN")
    major_dates = pd.Index([first_month, last_month]).append(quarter_starts).unique().sort_values()
    ax.xaxis.set_major_locator(FixedLocator(mdates.date2num(major_dates.to_pydatetime())))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator())
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))

    major_grid_color = "#c0c8d2"
    minor_grid_color = "#e1e6ee"
    ax.set_axisbelow(True)
    ax.grid(axis="x", which="major", color=major_grid_color, linewidth=0.85, linestyle="-", alpha=1.0)
    # ax.grid(axis="x", which="minor", color=minor_grid_color, linewidth=0.5, linestyle="-", alpha=1.0)
    # ax.grid(axis="y", which="major", color=major_grid_color, linewidth=0.85, linestyle="-", alpha=1.0)
    plt.setp(ax.get_xticklabels(), rotation=90, ha="center")

    ax.set_xlim(first_month - pd.DateOffset(days=12), last_month + pd.DateOffset(days=12))
    ax.set_ylim(0, max(5.5, plot_df["fraction_pct"].max() * 1.1))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    output_dir.mkdir(parents=True, exist_ok=True)
    figure_path = output_dir / "rq1_llm_satd_prevalence_monthly.pdf"
    fig.tight_layout()
    fig.savefig(figure_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return figure_path


def build_prevalence_summary(prevalence_df: pd.DataFrame) -> list[tuple[str, object]]:
    valid = prevalence_df.dropna(subset=["fraction_pct"]).copy()
    if valid.empty:
        return [
            ("start_month", np.nan),
            ("start_month_prevalence_pct", np.nan),
            ("max_month", np.nan),
            ("max_month_prevalence_pct", np.nan),
            ("end_month", np.nan),
            ("end_month_prevalence_pct", np.nan),
        ]

    valid["month"] = valid["month"].dt.tz_convert(None)
    valid.sort_values("month", inplace=True)

    start_row = valid.iloc[0]
    end_row = valid.iloc[-1]
    max_row = valid.loc[valid["fraction_pct"].idxmax()]

    def month_label(value: pd.Timestamp) -> str:
        return value.strftime("%Y-%m")

    return [
        ("start_month", month_label(start_row["month"])),
        ("start_month_prevalence_pct", start_row["fraction_pct"]),
        ("max_month", month_label(max_row["month"])),
        ("max_month_prevalence_pct", max_row["fraction_pct"]),
        ("end_month", month_label(end_row["month"])),
        ("end_month_prevalence_pct", end_row["fraction_pct"]),
    ]


def build_summary(
    satd: pd.DataFrame,
    llm_satd: pd.DataFrame,
    non_llm_satd: pd.DataFrame,
    prevalence_rows: list[tuple[str, object]],
) -> pd.DataFrame:
    total_satd = len(satd)
    llm_count = len(llm_satd)
    non_llm_count = len(non_llm_satd)

    llm_prop = (llm_count / total_satd * 100) if total_satd else np.nan
    non_llm_prop = (non_llm_count / total_satd * 100) if total_satd else np.nan

    llm_repaid = llm_satd[llm_satd["status"].astype(str).str.upper().eq("DELETED")]
    non_llm_repaid = non_llm_satd[non_llm_satd["status"].astype(str).str.upper().eq("DELETED")]

    llm_repaid_prop = (len(llm_repaid) / llm_count * 100) if llm_count else np.nan
    non_llm_repaid_prop = (len(non_llm_repaid) / non_llm_count * 100) if non_llm_count else np.nan

    rows = [
        ("num_satd", total_satd),
        ("num_llm_satd", llm_count),
        ("num_non_llm_satd", non_llm_count),
        ("pct_llm_satd", llm_prop),
        ("pct_non_llm_satd", non_llm_prop),
        ("num_llm_satd_repaid", len(llm_repaid)),
        ("num_non_llm_satd_repaid", len(non_llm_repaid)),
        ("pct_llm_satd_repaid", llm_repaid_prop),
        ("pct_non_llm_satd_repaid", non_llm_repaid_prop),
    ]
    rows.extend(prevalence_rows)
    return pd.DataFrame(rows, columns=["metric", "value"])


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ1: LLM-SATD prevalence plot and dataset statistics.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to dataset.csv")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Output directory (figures saved to outputs/figures).",
    )
    args = parser.parse_args()

    subsets = load_satd_dataset(path=args.dataset)
    satd = subsets.satd.copy()
    llm_satd = subsets.llm_satd.copy()
    non_llm_satd = subsets.non_llm_satd.copy()

    output_root = Path(args.output_dir)
    figures_dir = output_root / "figures"

    prevalence_df = compute_prevalence_df(satd)
    prevalence_rows = build_prevalence_summary(prevalence_df)
    summary_df = build_summary(satd, llm_satd, non_llm_satd, prevalence_rows)
    summary_path = output_root / "rq1_summary.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(summary_path, index=False)

    figure_path = build_prevalence_plot(prevalence_df, figures_dir)

    print("RQ1 summary written to:", summary_path)
    print("RQ1 prevalence plot written to:", figure_path)
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
