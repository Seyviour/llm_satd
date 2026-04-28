from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import mannwhitneyu

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from utils import DEFAULT_DATASET_PATH, METRIC_COLUMNS, compute_complexity_metrics, load_satd_dataset

MERGE_KEYS = [
    "full_name",
    "file_path",
    "context_at_introduction",
    "context_at_deletion_or_current",
    "comment",
    "introducing_commit",
]

HEADLINE_COMPLEXITY_METRICS = [
    "cyclomatic_complexity",
    "cognitive_complexity",
    "halstead_volume",
    "maintainability_index",
    "loc",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate complexity metric boxplots and group comparisons."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Canonical SATD dataset CSV.",
    )
    parser.add_argument(
        "--enclosing-functions",
        type=Path,
        default=Path("data") / Path("enclosing_functions_all_with_removals.csv"),
        help="CSV enriched with enclosing function extraction output.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Output directory for CSV and figures.",
    )
    return parser.parse_args()


def _load_enclosing_enrichment(path: Path) -> pd.DataFrame:
    enrichment = pd.read_csv(path, low_memory=False)
    missing_keys = [key for key in MERGE_KEYS if key not in enrichment.columns]
    if missing_keys:
        raise ValueError(
            "Enclosing-function file is missing required merge keys: "
            + ", ".join(missing_keys)
        )

    enrichment_columns = ["enclosing_function_source", "extraction_status"]
    missing_columns = [column for column in enrichment_columns if column not in enrichment.columns]
    if missing_columns:
        raise ValueError(
            "Enclosing-function file is missing required columns: "
            + ", ".join(missing_columns)
        )

    # Some repositories have repeated records for identical SATD keys; keep the highest-quality
    # extraction record to preserve a one-to-one merge with canonical SATD rows.
    status_rank = {
        "ok": 0,
        "module_level": 1,
        "parse_error": 2,
    }
    enrichment = enrichment.copy()
    enrichment["_status_rank"] = (
        enrichment["extraction_status"].astype(str).str.strip().str.lower().map(status_rank).fillna(3)
    )
    enrichment["_has_source"] = (
        enrichment["enclosing_function_source"].fillna("").astype(str).str.strip().ne("")
    )
    enrichment.sort_values(
        by=["_status_rank", "_has_source"],
        ascending=[True, False],
        inplace=True,
        kind="stable",
    )
    enrichment = enrichment.drop_duplicates(subset=MERGE_KEYS, keep="first")

    return enrichment.loc[:, MERGE_KEYS + enrichment_columns].copy()


def build_complexity_base_frame(dataset_path: Path, enclosing_functions_path: Path) -> pd.DataFrame:
    strict = load_satd_dataset(path=dataset_path).satd.copy()
    enrichment = _load_enclosing_enrichment(enclosing_functions_path)
    strict = strict.merge(enrichment, how="left", on=MERGE_KEYS)

    strict["status"] = strict["status"].astype(str).str.upper().str.strip()
    strict["satd_group"] = np.where(
        strict["is_llm_satd"].fillna(False).astype(bool),
        "llm_satd",
        "non_llm_satd",
    )

    strict["introducing_date_dt"] = pd.to_datetime(strict.get("introducing_date"), errors="coerce", utc=True)
    deleting_dates = strict.get("deleting_date", pd.Series(pd.NA, index=strict.index)).replace(
        {"<<unavailable>>": pd.NA, "unavailable": pd.NA}
    )
    strict["deleting_date_dt"] = pd.to_datetime(deleting_dates, errors="coerce", utc=True)

    strict["repayment_days"] = np.where(
        strict["status"].eq("DELETED"),
        (strict["deleting_date_dt"] - strict["introducing_date_dt"]).dt.total_seconds() / 86400.0,
        np.nan,
    )
    strict["lines_modified"] = (
        pd.to_numeric(strict.get("lines_added"), errors="coerce").fillna(0.0)
        + pd.to_numeric(strict.get("lines_removed"), errors="coerce").fillna(0.0)
    )
    strict["files_modified"] = pd.to_numeric(strict.get("num_modified_files_add"), errors="coerce")
    strict["ast_modifications"] = pd.to_numeric(strict.get("ast_actions_count"), errors="coerce")
    strict["repayment_commits"] = pd.to_numeric(strict.get("between_commits"), errors="coerce")
    return strict


def _metric_ready_subset(frame: pd.DataFrame) -> pd.DataFrame:
    if "metric_status" not in frame.columns:
        return cast(pd.DataFrame, frame.head(0).copy())
    return cast(pd.DataFrame, frame[frame["metric_status"].astype(str).eq("ok")].copy())

def add_complexity_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    source_present = enriched.get("enclosing_function_source", pd.Series("", index=enriched.index)).fillna("").ne("")
    extraction_ok = enriched.get("extraction_status", pd.Series("", index=enriched.index)).fillna("").eq("ok")
    eligible_mask = source_present & extraction_ok

    metric_status = pd.Series("missing_source", index=enriched.index, dtype="object")
    skipped_mask = source_present & ~extraction_ok
    metric_status.loc[skipped_mask] = "skipped_" + enriched.loc[skipped_mask, "extraction_status"].astype(str)
    metric_status.loc[eligible_mask] = "pending"
    enriched["metric_status"] = metric_status

    for column in METRIC_COLUMNS:
        enriched[column] = np.nan

    if not eligible_mask.any():
        return enriched

    unique_sources = enriched.loc[eligible_mask, "enclosing_function_source"].drop_duplicates()
    if len(unique_sources) > 1000 and (os.cpu_count() or 1) > 1:
        max_workers = min(8, os.cpu_count() or 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            metric_pairs = executor.map(_compute_source_metric_pair, unique_sources.tolist(), chunksize=64)
            metric_lookup = dict(metric_pairs)
    else:
        metric_lookup = {source: compute_complexity_metrics(source) for source in unique_sources}
    mapped = enriched.loc[eligible_mask, "enclosing_function_source"].map(metric_lookup)
    metrics = pd.DataFrame.from_records(mapped.tolist(), index=mapped.index)
    for column in METRIC_COLUMNS + ["metric_status"]:
        enriched.loc[eligible_mask, column] = metrics[column].to_numpy()
    return enriched


def _compute_source_metric_pair(source: str) -> tuple[str, dict[str, float | str | None]]:
    return source, compute_complexity_metrics(source)


def build_group_comparisons(frame: pd.DataFrame) -> pd.DataFrame:
    subset = _metric_ready_subset(frame)
    llm = subset.loc[subset["satd_group"] == "llm_satd"]
    non_llm = subset.loc[subset["satd_group"] == "non_llm_satd"]

    rows = []
    for metric in METRIC_COLUMNS:
        x = pd.to_numeric(llm.get(metric, pd.Series(index=llm.index, dtype=float)), errors="coerce").dropna()
        y = pd.to_numeric(non_llm.get(metric, pd.Series(index=non_llm.index, dtype=float)), errors="coerce").dropna()
        if x.empty or y.empty:
            rows.append(
                {
                    "metric": metric,
                    "llm_n": int(x.shape[0]),
                    "non_llm_n": int(y.shape[0]),
                    "llm_median": float(x.median()) if not x.empty else np.nan,
                    "non_llm_median": float(y.median()) if not y.empty else np.nan,
                    "u_statistic": np.nan,
                    "p_value": np.nan,
                    "rank_biserial_effect_size": np.nan,
                    "status": "insufficient_data",
                }
            )
            continue

        result = mannwhitneyu(x, y, alternative="two-sided", method="auto")
        u_statistic = float(result.statistic)
        rank_biserial = (2.0 * u_statistic / (len(x) * len(y))) - 1.0
        rows.append(
            {
                "metric": metric,
                "llm_n": int(x.shape[0]),
                "non_llm_n": int(y.shape[0]),
                "llm_median": float(x.median()),
                "non_llm_median": float(y.median()),
                "u_statistic": u_statistic,
                "p_value": float(result.pvalue),
                "rank_biserial_effect_size": float(rank_biserial),
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)

def build_metric_boxplots(frame: pd.DataFrame, output_dir: Path) -> Dict[str, Path]:
    subset = _metric_ready_subset(frame)
    pooled = subset.copy()
    pooled["satd_group"] = "all_satd"
    plot_frame = pd.concat([subset, pooled], ignore_index=True)

    tidy = plot_frame.melt(
        id_vars=["satd_group"],
        value_vars=HEADLINE_COMPLEXITY_METRICS,
        var_name="metric",
        value_name="value",
    )
    tidy.dropna(subset=["value"], inplace=True)

    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, len(HEADLINE_COMPLEXITY_METRICS), figsize=(16, 4.2), sharex=False)
    if tidy.empty:
        for axis in np.ravel(axes):
            axis.axis("off")
        fig.suptitle("No eligible function-level SATD rows available for complexity boxplots")
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / "rq2_complexity_metric_boxplots.png"
        pdf_path = output_dir / "rq2_complexity_metric_boxplots.pdf"
        fig.savefig(png_path, dpi=300, bbox_inches="tight")
        fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return {"png": png_path, "pdf": pdf_path}

    palette = {"llm_satd": "#4C72B0", "non_llm_satd": "#DD8452", "all_satd": "#55A868"}
    order = ["llm_satd", "non_llm_satd", "all_satd"]

    for axis, metric in zip(np.ravel(axes), HEADLINE_COMPLEXITY_METRICS):
        current = tidy.loc[tidy["metric"] == metric]
        sns.boxplot(
            data=current,
            x="satd_group",
            y="value",
            hue="satd_group",
            order=order,
            palette=palette,
            dodge=False,
            legend=False,
            showfliers=False,
            linewidth=1.0,
            ax=axis,
        )
        axis.set_title(metric.replace("_", " ").title())
        axis.set_xlabel("")
        axis.set_ylabel("")
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", linewidth=0.6, alpha=0.35)

    fig.supylabel("Metric value")
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "rq2_complexity_metric_boxplots.png"
    pdf_path = output_dir / "rq2_complexity_metric_boxplots.pdf"
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {"png": png_path, "pdf": pdf_path}

def run_analysis(
    *,
    dataset_path: Path,
    enclosing_functions_path: Path,
    output_dir: Path,
) -> Dict[str, Path]:
    """Generate complexity metric boxplots and group comparisons."""
    strict_satd = build_complexity_base_frame(dataset_path, enclosing_functions_path)
    analyzed = add_complexity_metrics(strict_satd)

    comparisons = build_group_comparisons(analyzed)

    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    comparison_output = output_dir / "rq2_complexity_group_comparisons.csv"
    comparisons.to_csv(comparison_output, index=False)

    boxplot_paths = build_metric_boxplots(analyzed, figures_dir)

    return {
        "comparisons": comparison_output,
        "boxplot_png": boxplot_paths["png"],
        "boxplot_pdf": boxplot_paths["pdf"],
    }


def main() -> None:
    args = parse_args()
    outputs = run_analysis(
        dataset_path=args.dataset,
        enclosing_functions_path=args.enclosing_functions,
        output_dir=args.output_dir,
    )
    print("Complexity analysis outputs written:")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
