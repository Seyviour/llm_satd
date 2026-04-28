import argparse
import itertools
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import chi2, mannwhitneyu

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from utils import CUTOFF_END, load_satd_dataset


def _days_between(start_series: pd.Series, end_series: pd.Series) -> pd.Series:
    start_dt = pd.to_datetime(start_series, errors="coerce", utc=True)
    end_dt = pd.to_datetime(end_series, errors="coerce", utc=True)
    valid = start_dt.notna() & end_dt.notna()
    if not valid.any():
        return pd.Series(dtype=float)
    return (end_dt[valid] - start_dt[valid]).dt.total_seconds() / 86400.0


def _age_since(series: pd.Series, reference: pd.Timestamp) -> pd.Series:
    start_dt = pd.to_datetime(series, errors="coerce", utc=True)
    valid = start_dt.notna()
    if not valid.any():
        return pd.Series(dtype=float)
    return (reference - start_dt[valid]).dt.total_seconds() / 86400.0


def mann_whitney_u(x: pd.Series, y: pd.Series) -> Optional[Dict[str, float]]:
    x = pd.to_numeric(pd.Series(x), errors="coerce").dropna().to_numpy()
    y = pd.to_numeric(pd.Series(y), errors="coerce").dropna().to_numpy()
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return None

    result = mannwhitneyu(x, y, alternative="two-sided", method="auto")
    u_stat = float(result.statistic)
    vargha_delaney_a = u_stat / (n1 * n2) if n1 and n2 else np.nan
    return {
        "u1": u_stat,
        "u_min": u_stat,
        "vargha_delaney_a": vargha_delaney_a,
        "z": np.nan,
        "p": float(result.pvalue),
        "n1": n1,
        "n2": n2,
    }


def effect_size_magnitude(vargha_delaney_a: float) -> str:
    if pd.isna(vargha_delaney_a):
        return "NA"

    if 0.44 <= vargha_delaney_a <= 0.56:
        return "negligible"
    if 0.36 <= vargha_delaney_a < 0.44 or 0.56 < vargha_delaney_a <= 0.64:
        return "small"
    if 0.29 <= vargha_delaney_a < 0.36 or 0.64 < vargha_delaney_a <= 0.71:
        return "medium"
    return "large"


def _normalise_first_flag(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower()


def _km_median(curve: pd.DataFrame) -> float:
    below = curve[curve["survival"] <= 0.5]
    if below.empty:
        return np.nan
    return float(below.iloc[0]["time"])


def _survival_at(curve: pd.DataFrame, days: float) -> float:
    observed = curve[curve["time"] <= days]
    if observed.empty:
        return 1.0
    return float(observed.iloc[-1]["survival"])


def _deleted_only(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["status"].astype(str).str.upper().eq("DELETED")].copy()


def _active_only(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["status"].astype(str).str.upper().eq("ACTIVE")].copy()


def _first_flag_subset(frame: pd.DataFrame, flag: str) -> pd.DataFrame:
    working = frame.copy()
    working["first_flag"] = _normalise_first_flag(working["line_is_in_first_commit"])
    return working[working["first_flag"] == flag].copy()


def _build_four_group_survival_datasets(llm_satd: pd.DataFrame, non_llm_satd: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    reference_timestamp = pd.to_datetime(CUTOFF_END, utc=True)
    specs = [
        ("LLM-SATD, first-file-commit", llm_satd, "true"),
        ("LLM-SATD, introduced later", llm_satd, "false"),
        ("Non-LLM-SATD, first-file-commit", non_llm_satd, "true"),
        ("Non-LLM-SATD, introduced later", non_llm_satd, "false"),
    ]
    datasets = {}
    for label, frame, flag in specs:
        subset = _first_flag_subset(frame, flag)
        datasets[label] = build_survival_dataset(
            _deleted_only(subset),
            _active_only(subset),
            reference_ts=reference_timestamp,
        )
    return datasets


def build_four_group_survival_summary(llm_satd: pd.DataFrame, non_llm_satd: pd.DataFrame) -> pd.DataFrame:
    rows = []
    km_datasets = _build_four_group_survival_datasets(llm_satd, non_llm_satd)
    specs = [
        ("LLM-SATD, first-file-commit", llm_satd, "true"),
        ("LLM-SATD, introduced later", llm_satd, "false"),
        ("Non-LLM-SATD, first-file-commit", non_llm_satd, "true"),
        ("Non-LLM-SATD, introduced later", non_llm_satd, "false"),
    ]
    for label, frame, flag in specs:
        subset = _first_flag_subset(frame, flag)
        repaid = _deleted_only(subset)
        surv = km_datasets[label]
        curve = kaplan_meier_curve(surv)
        rows.append(
            {
                "group": label,
                "n": int(len(surv)),
                "events": int(surv["event"].sum()) if not surv.empty else 0,
                "censored": int((surv["event"] == 0).sum()) if not surv.empty else 0,
                "deleted_share": float(surv["event"].mean()) if not surv.empty else np.nan,
                "median_observed_repayment_days_deleted_only": float(
                    _days_between(repaid["introducing_date"], repaid["deleting_date"]).median()
                )
                if not repaid.empty
                else np.nan,
                "km_median_days_to_resolution": _km_median(curve),
                "survival_at_30d": _survival_at(curve, 30),
                "survival_at_90d": _survival_at(curve, 90),
                "survival_at_180d": _survival_at(curve, 180),
            }
        )
    return pd.DataFrame(rows)


def build_four_group_survival_curve_table(llm_satd: pd.DataFrame, non_llm_satd: pd.DataFrame) -> pd.DataFrame:
    rows = []
    km_datasets = _build_four_group_survival_datasets(llm_satd, non_llm_satd)
    for label, dataset in km_datasets.items():
        curve = kaplan_meier_curve(dataset)
        for _, row in curve.iterrows():
            rows.append({"group": label, "time": float(row["time"]), "survival": float(row["survival"])})
    return pd.DataFrame(rows)


def build_four_group_pairwise_log_rank_table(llm_satd: pd.DataFrame, non_llm_satd: pd.DataFrame) -> pd.DataFrame:
    km_datasets = _build_four_group_survival_datasets(llm_satd, non_llm_satd)
    rows = []
    for (label_a, data_a), (label_b, data_b) in itertools.combinations(km_datasets.items(), 2):
        result = log_rank_test(data_a, data_b)
        rows.append(
            {
                "comparison": f"{label_a} vs {label_b}",
                "group_a": label_a,
                "group_b": label_b,
                "n_a": result["n1"] if result else np.nan,
                "n_b": result["n2"] if result else np.nan,
                "events_a": result["events1"] if result else np.nan,
                "events_b": result["events2"] if result else np.nan,
                "chi_square": result["chi_square"] if result else np.nan,
                "p_value": result["p"] if result else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("p_value")


def build_four_group_survival_plot(llm_satd: pd.DataFrame, non_llm_satd: pd.DataFrame, output_dir: Path) -> Path:
    km_datasets = _build_four_group_survival_datasets(llm_satd, non_llm_satd)
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    styles = {
        "LLM-SATD, first-file-commit": {"color": "#1f77b4", "linestyle": "-"},
        "LLM-SATD, introduced later": {"color": "#1f77b4", "linestyle": "--"},
        "Non-LLM-SATD, first-file-commit": {"color": "#d62728", "linestyle": "-"},
        "Non-LLM-SATD, introduced later": {"color": "#d62728", "linestyle": "--"},
    }
    for label, dataset in km_datasets.items():
        curve = kaplan_meier_curve(dataset)
        if curve.empty:
            continue
        style = styles[label]
        ax.step(
            curve["time"],
            curve["survival"],
            where="post",
            linewidth=2.0,
            label=label,
            color=style["color"],
            linestyle=style["linestyle"],
        )

    ax.set_xlabel("Days since introduction")
    ax.set_ylabel("Probability SATD remains unresolved")
    ax.set_ylim(0, 1.02)
    ax.set_xlim(left=0)
    ax.grid(axis="both", which="major", linewidth=0.7, alpha=0.35)
    ax.legend(frameon=False, loc="upper right")
    sns.despine(ax=ax)

    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    km_path = output_dir / "rq2_first_file_commit_km_four_groups.pdf"
    fig.savefig(km_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return km_path


def build_survival_dataset(resolved_df: pd.DataFrame, active_df: pd.DataFrame, *, reference_ts: pd.Timestamp) -> pd.DataFrame:
    resolved_days = _days_between(resolved_df["introducing_date"], resolved_df["deleting_date"]).dropna()
    active_days = _age_since(active_df["introducing_date"], reference_ts).dropna()
    resolved_frame = pd.DataFrame({"duration": resolved_days.values.astype(float), "event": 1})
    active_frame = pd.DataFrame({"duration": active_days.values.astype(float), "event": 0})
    combined = pd.concat([resolved_frame, active_frame], ignore_index=True)
    combined = combined[combined["duration"].notna() & (combined["duration"] >= 0)]
    return combined


def kaplan_meier_curve(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame(columns=["time", "survival"])
    working = dataset.copy()
    working.sort_values("duration", inplace=True)
    working.reset_index(drop=True, inplace=True)

    n_at_risk = len(working)
    survival = 1.0
    records = [(0.0, survival)]

    for time, group in working.groupby("duration", sort=True):
        events = group["event"].sum()
        if n_at_risk <= 0:
            break
        if events > 0:
            survival *= (1 - events / n_at_risk)
        records.append((float(time), survival))
        n_at_risk -= len(group)

    curve = pd.DataFrame(records, columns=["time", "survival"])
    curve = curve.sort_values("time").drop_duplicates(subset="time", keep="last")
    return curve


def log_rank_test(group_a: pd.DataFrame, group_b: pd.DataFrame) -> Optional[Dict[str, float]]:
    a = group_a[["duration", "event"]].copy()
    b = group_b[["duration", "event"]].copy()
    a["duration"] = pd.to_numeric(a["duration"], errors="coerce")
    b["duration"] = pd.to_numeric(b["duration"], errors="coerce")
    a["event"] = pd.to_numeric(a["event"], errors="coerce").fillna(0).astype(int)
    b["event"] = pd.to_numeric(b["event"], errors="coerce").fillna(0).astype(int)
    a = a[a["duration"].notna()]
    b = b[b["duration"].notna()]
    if a.empty or b.empty:
        return None

    a_by_time = a.groupby("duration")["event"].agg(["sum", "size"])
    b_by_time = b.groupby("duration")["event"].agg(["sum", "size"])
    if int(a["event"].sum() + b["event"].sum()) == 0:
        return None

    all_times = sorted(set(a_by_time.index).union(set(b_by_time.index)))
    a_events = a_by_time["sum"].to_dict()
    b_events = b_by_time["sum"].to_dict()
    a_removed = a_by_time["size"].to_dict()
    b_removed = b_by_time["size"].to_dict()

    n_a = float(len(a))
    n_b = float(len(b))
    observed_a = 0.0
    expected_a = 0.0
    variance_a = 0.0
    total_events = 0.0

    for time in all_times:
        d_a = float(a_events.get(time, 0.0))
        d_b = float(b_events.get(time, 0.0))
        d_total = d_a + d_b
        n_total = n_a + n_b

        if d_total > 0 and n_total > 1:
            observed_a += d_a
            expected_a += d_total * (n_a / n_total)
            variance_a += (n_a * n_b * d_total * (n_total - d_total)) / (n_total**2 * (n_total - 1))
            total_events += d_total

        n_a -= float(a_removed.get(time, 0.0))
        n_b -= float(b_removed.get(time, 0.0))

    if variance_a <= 0:
        statistic = np.nan
        p_value = np.nan
    else:
        statistic = (observed_a - expected_a) ** 2 / variance_a
        p_value = float(chi2.sf(statistic, df=1))

    return {
        "chi_square": float(statistic),
        "p": p_value,
        "n1": int(len(a)),
        "n2": int(len(b)),
        "events1": int(a["event"].sum()),
        "events2": int(b["event"].sum()),
        "censored1": int((a["event"] == 0).sum()),
        "censored2": int((b["event"] == 0).sum()),
        "observed1": observed_a,
        "expected1": expected_a,
        "variance1": variance_a,
        "total_events": int(total_events),
    }


def build_effort_boxplot(llm_repaid: pd.DataFrame, non_llm_repaid: pd.DataFrame, output_dir: Path) -> Path:
    sns.set_theme(style="whitegrid")
    boxplot_metrics = [
        ("Lines Modified", None),
        ("Files Modified", "num_modified_files_add"),
        ("AST Modifications", "ast_actions_count"),
    ]

    plot_frames = []
    for label, frame in [("LLM-SATD", llm_repaid), ("Non-LLM-SATD", non_llm_repaid)]:
        working = frame.copy()
        for col in ["lines_added", "lines_removed", "num_modified_files_add", "ast_actions_count"]:
            working[col] = pd.to_numeric(working.get(col), errors="coerce")
        working["lines_combined"] = working["lines_added"].fillna(0) + working["lines_removed"].fillna(0)

        metric_columns = {
            "Lines Modified": working["lines_combined"],
            "Files Modified": working["num_modified_files_add"],
            "AST Modifications": working["ast_actions_count"],
        }

        tidy = (
            pd.DataFrame(metric_columns)
            .melt(var_name="Effort Metric", value_name="Value")
            .assign(Group=label)
        )
        plot_frames.append(tidy)

    boxplot_data = pd.concat(plot_frames, ignore_index=True)
    boxplot_data.dropna(subset=["Value"], inplace=True)
    metric_order = [name for name, _ in boxplot_metrics]

    n_metrics = len(metric_order)
    fig_width = max(n_metrics * 2.4, 10)
    fig, axes = plt.subplots(1, n_metrics, figsize=(fig_width, 3.6), sharey=False)
    if n_metrics == 1:
        axes = np.array([axes])
    else:
        axes = np.ravel(axes)

    palette = {"LLM-SATD": "#6E96D7", "Non-LLM-SATD": "#F48E53"}
    group_order = ["Non-LLM-SATD", "LLM-SATD"]

    for idx, metric in enumerate(metric_order):
        ax = axes[idx]
        ax.tick_params(axis="x", labelbottom=False)
        ax.set_xlabel(None)
        subset = boxplot_data[boxplot_data["Effort Metric"] == metric]
        if subset.empty:
            ax.set_visible(False)
            continue

        sns.boxplot(
            data=subset,
            x="Group",
            y="Value",
            order=group_order,
            palette=palette,
            width=0.55,
            linewidth=1.0,
            showfliers=False,
            ax=ax,
        )

        ax.set_ylabel(metric, fontsize=12, fontweight="bold")
        meds = subset.groupby("Group")["Value"].median()
        for i, g in enumerate(group_order):
            if g in meds:
                y = meds[g]
                ax.text(i, y, f"{y:.0f}", ha="center", va="bottom", fontsize=12, color="black", clip_on=True, weight="bold")

        ax.tick_params(axis="x", rotation=0, labelsize=12)
        ax.tick_params(axis="y", labelsize=12)
        ax.grid(axis="y", linewidth=0.6, alpha=0.3)
        sns.despine(ax=ax)

    handles = [Line2D([0], [0], color=palette[g], lw=3) for g in group_order]
    fig.legend(handles, group_order, loc="upper center", frameon=False, ncol=2)

    fig.subplots_adjust(wspace=0.35)
    fig.tight_layout(rect=[0, 0, 1, 0.92])

    output_dir.mkdir(parents=True, exist_ok=True)
    boxplot_path = output_dir / "rq2_effort_boxplot.pdf"
    fig.savefig(boxplot_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return boxplot_path


def build_survival_plot(
    llm_repaid: pd.DataFrame,
    llm_active: pd.DataFrame,
    non_llm_repaid: pd.DataFrame,
    non_llm_active: pd.DataFrame,
    output_dir: Path,
) -> Path:
    reference_timestamp = pd.to_datetime(CUTOFF_END, utc=True)
    km_datasets = {
        "LLM-SATD": build_survival_dataset(llm_repaid, llm_active, reference_ts=reference_timestamp),
        "Non-LLM-SATD": build_survival_dataset(non_llm_repaid, non_llm_active, reference_ts=reference_timestamp),
    }
    km_curves = {label: kaplan_meier_curve(df) for label, df in km_datasets.items()}

    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    colours = {"LLM-SATD": "#4C72B0", "Non-LLM-SATD": "#DD8452"}
    for label, curve in km_curves.items():
        if curve.empty:
            continue
        ax.step(curve["time"], curve["survival"], where="post", label=label, linewidth=2.0, color=colours.get(label))

    ax.set_xlabel("Days since introduction")
    ax.set_ylabel("Probability SATD remains unresolved")
    ax.set_title("Kaplan-Meier survival curves for SATD resolution", pad=14)
    ax.set_ylim(0, 1.02)
    ax.set_xlim(left=0)
    ax.grid(axis="both", which="major", linewidth=0.7, alpha=0.35)
    ax.legend(frameon=False, loc="upper right")
    sns.despine(ax=ax)

    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    km_path = output_dir / "rq2_satd_survival.pdf"
    fig.savefig(km_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return km_path


def build_log_rank_table(
    llm_repaid: pd.DataFrame,
    llm_active: pd.DataFrame,
    non_llm_repaid: pd.DataFrame,
    non_llm_active: pd.DataFrame,
) -> pd.DataFrame:
    reference_timestamp = pd.to_datetime(CUTOFF_END, utc=True)
    llm_survival = build_survival_dataset(llm_repaid, llm_active, reference_ts=reference_timestamp)
    non_llm_survival = build_survival_dataset(non_llm_repaid, non_llm_active, reference_ts=reference_timestamp)
    result = log_rank_test(llm_survival, non_llm_survival)
    if result is None:
        return pd.DataFrame(
            [
                {
                    "Comparison": "LLM-SATD vs Non-LLM-SATD",
                    "LLM n": len(llm_survival),
                    "Non-LLM n": len(non_llm_survival),
                    "LLM events": int(llm_survival["event"].sum()) if not llm_survival.empty else 0,
                    "Non-LLM events": int(non_llm_survival["event"].sum()) if not non_llm_survival.empty else 0,
                    "LLM censored": int((llm_survival["event"] == 0).sum()) if not llm_survival.empty else 0,
                    "Non-LLM censored": int((non_llm_survival["event"] == 0).sum()) if not non_llm_survival.empty else 0,
                    "Observed LLM events": np.nan,
                    "Expected LLM events": np.nan,
                    "Variance": np.nan,
                    "chi-square": np.nan,
                    "p (log-rank)": np.nan,
                }
            ]
        )

    return pd.DataFrame(
        [
            {
                "Comparison": "LLM-SATD vs Non-LLM-SATD",
                "LLM n": result["n1"],
                "Non-LLM n": result["n2"],
                "LLM events": result["events1"],
                "Non-LLM events": result["events2"],
                "LLM censored": result["censored1"],
                "Non-LLM censored": result["censored2"],
                "Observed LLM events": result["observed1"],
                "Expected LLM events": result["expected1"],
                "Variance": result["variance1"],
                "chi-square": result["chi_square"],
                "p (log-rank)": result["p"],
            }
        ]
    )


def build_mann_whitney_table(llm_repaid: pd.DataFrame, non_llm_repaid: pd.DataFrame) -> pd.DataFrame:
    repayment_days = _days_between(llm_repaid["introducing_date"], llm_repaid["deleting_date"])
    repayment_days_non = _days_between(non_llm_repaid["introducing_date"], non_llm_repaid["deleting_date"])

    metrics_llm = {
        "Repayment Time (days)": repayment_days,
        "Lines Modified": pd.to_numeric(llm_repaid.get("lines_added"), errors="coerce").fillna(0)
        + pd.to_numeric(llm_repaid.get("lines_removed"), errors="coerce").fillna(0),
        "Files Modified": pd.to_numeric(llm_repaid.get("num_modified_files_add"), errors="coerce"),
        "AST Modifications": pd.to_numeric(llm_repaid.get("ast_actions_count"), errors="coerce"),
    }

    metrics_non = {
        "Repayment Time (days)": repayment_days_non,
        "Lines Modified": pd.to_numeric(non_llm_repaid.get("lines_added"), errors="coerce").fillna(0)
        + pd.to_numeric(non_llm_repaid.get("lines_removed"), errors="coerce").fillna(0),
        "Files Modified": pd.to_numeric(non_llm_repaid.get("num_modified_files_add"), errors="coerce"),
        "AST Modifications": pd.to_numeric(non_llm_repaid.get("ast_actions_count"), errors="coerce"),
    }

    rows = []
    for name in metrics_llm:
        res = mann_whitney_u(metrics_llm[name], metrics_non[name])
        if res is None:
            rows.append(
                {
                    "Metric": name,
                    "LLM n": 0,
                    "Non-LLM n": 0,
                    "U (LLM)": np.nan,
                    "Vargha-Delaney A": np.nan,
                    "Effect size": "NA",
                    "z": np.nan,
                    "p (two-sided)": np.nan,
                }
            )
            continue
        rows.append(
            {
                "Metric": name,
                "LLM n": res["n1"],
                "Non-LLM n": res["n2"],
                "U (LLM)": res["u1"],
                "Vargha-Delaney A": res["vargha_delaney_a"],
                "Effect size": effect_size_magnitude(res["vargha_delaney_a"]),
                "z": res["z"],
                "p (two-sided)": res["p"],
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ2: effort plots, Mann-Whitney U tests, and survival plots.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to dataset.csv")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Output directory (figures saved to outputs/figures).",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Generate first-file-commit split survival outputs, including four-group Kaplan-Meier tables and figure.",
    )
    args = parser.parse_args()

    subsets = load_satd_dataset(path=args.dataset)
    llm_satd = subsets.llm_satd.copy()
    non_llm_satd = subsets.non_llm_satd.copy()

    llm_repaid = llm_satd[llm_satd["status"].astype(str).str.upper().eq("DELETED")].copy()
    llm_active = llm_satd[llm_satd["status"].astype(str).str.upper().eq("ACTIVE")].copy()
    non_llm_repaid = non_llm_satd[non_llm_satd["status"].astype(str).str.upper().eq("DELETED")].copy()
    non_llm_active = non_llm_satd[non_llm_satd["status"].astype(str).str.upper().eq("ACTIVE")].copy()

    output_root = Path(args.output_dir)
    figures_dir = output_root / "figures"

    boxplot_path = build_effort_boxplot(llm_repaid, non_llm_repaid, figures_dir)
    km_path = build_survival_plot(llm_repaid, llm_active, non_llm_repaid, non_llm_active, figures_dir)

    llm_median_repayment = _days_between(llm_repaid["introducing_date"], llm_repaid["deleting_date"]).median()
    non_llm_median_repayment = _days_between(
        non_llm_repaid["introducing_date"], non_llm_repaid["deleting_date"]
    ).median()
    median_repayment_df = pd.DataFrame(
        [
            {"group": "LLM-SATD", "median_repayment_days": llm_median_repayment},
            {"group": "Non-LLM-SATD", "median_repayment_days": non_llm_median_repayment},
        ]
    )
    output_root.mkdir(parents=True, exist_ok=True)
    median_repayment_path = output_root / "rq2_median_repayment_times.csv"
    median_repayment_df.to_csv(median_repayment_path, index=False)

    mann_whitney_table = build_mann_whitney_table(llm_repaid, non_llm_repaid)
    csv_path = output_root / "rq2_mann_whitney_u_results.csv"
    tex_path = output_root / "rq2_mann_whitney_u_results.tex"
    mann_whitney_table.to_csv(csv_path, index=False)
    mann_whitney_table.to_latex(tex_path, index=False, float_format=lambda x: f"{x:.4f}")

    log_rank_table = build_log_rank_table(llm_repaid, llm_active, non_llm_repaid, non_llm_active)
    log_rank_csv_path = output_root / "rq2_log_rank_survival.csv"
    log_rank_tex_path = output_root / "rq2_log_rank_survival.tex"
    log_rank_table.to_csv(log_rank_csv_path, index=False)
    log_rank_table.to_latex(
        log_rank_tex_path,
        index=False,
        float_format=lambda x: f"{x:.4f}",
        formatters={"p (log-rank)": lambda x: f"{x:.2e}" if pd.notna(x) else ""},
    )

    print("RQ2 effort plot written to:", boxplot_path)
    print("RQ2 survival plot written to:", km_path)
    print("RQ2 median repayment times written to:", median_repayment_path)
    print("RQ2 Mann-Whitney U results written to:", csv_path)
    print("RQ2 log-rank survival results written to:", log_rank_csv_path)
    print(median_repayment_df.to_string(index=False))
    print(mann_whitney_table.to_string(index=False))
    print(log_rank_table.to_string(index=False))

    if args.extended:
        four_group_km_summary = build_four_group_survival_summary(llm_satd, non_llm_satd)
        four_group_km_summary_path = output_root / "rq2_first_file_commit_km_four_groups_summary.csv"
        four_group_km_summary.to_csv(four_group_km_summary_path, index=False)

        four_group_km_curves = build_four_group_survival_curve_table(llm_satd, non_llm_satd)
        four_group_km_curves_path = output_root / "rq2_first_file_commit_km_four_groups_curves.csv"
        four_group_km_curves.to_csv(four_group_km_curves_path, index=False)

        four_group_log_rank = build_four_group_pairwise_log_rank_table(llm_satd, non_llm_satd)
        four_group_log_rank_path = output_root / "rq2_first_file_commit_km_four_groups_pairwise_logrank.csv"
        four_group_log_rank.to_csv(four_group_log_rank_path, index=False)

        four_group_km_plot_path = build_four_group_survival_plot(llm_satd, non_llm_satd, figures_dir)
        print("Extended four-group KM summary written to:", four_group_km_summary_path)
        print("Extended four-group KM curves written to:", four_group_km_curves_path)
        print("Extended four-group log-rank results written to:", four_group_log_rank_path)
        print("Extended four-group KM plot written to:", four_group_km_plot_path)


if __name__ == "__main__":
    main()
