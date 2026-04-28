import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from utils import assign_role, load_repo_maintainers, load_satd_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discussion analysis: repayment rankings by category and developer roles."
    )
    parser.add_argument("--dataset", type=str, default=None, help="Path to dataset.csv")
    parser.add_argument(
        "--maintainers",
        type=str,
        default=None,
        help="Path to repo_maintainers.json",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Output directory for discussion CSVs.",
    )
    args = parser.parse_args()

    subsets = load_satd_dataset(path=args.dataset)
    satd = subsets.satd.copy()

    def _lowercase_item(item: object) -> object:
        if isinstance(item, str):
            return item.lower()
        if isinstance(item, list):
            return [_lowercase_item(value) for value in item]
        if isinstance(item, dict):
            return {str(key).lower(): _lowercase_item(value) for key, value in item.items()}
        return item

    maintainers = load_repo_maintainers(path=args.maintainers)
    maintainers = {str(key).lower(): _lowercase_item(value) for key, value in maintainers.items()}
    satd["developer_role"] = satd.apply(
        assign_role,
        axis=1,
        login_col="introduction_github_id",
        repo_col="full_name",
        maintainers=maintainers,
    )

    llm_satd = subsets.llm_satd.copy()
    llm_satd_repaid = subsets.llm_satd_repaid.copy()
    non_llm_satd = subsets.non_llm_satd.copy()
    non_llm_satd_repaid = subsets.non_llm_satd_repaid.copy()

    for frame in [llm_satd, llm_satd_repaid, non_llm_satd, non_llm_satd_repaid]:
        frame["introducer_role"] = frame.apply(
            assign_role,
            axis=1,
            login_col="introduction_github_id",
            repo_col="full_name",
            maintainers=maintainers,
        )
        frame["remover_role"] = frame.apply(
            assign_role,
            axis=1,
            login_col="removal_github_id",
            repo_col="full_name",
            maintainers=maintainers,
        )

    llm_satd_repaid["resolution_days"] = (
        pd.to_datetime(llm_satd_repaid["deleting_date"], errors="coerce", utc=True)
        - pd.to_datetime(llm_satd_repaid["introducing_date"], errors="coerce", utc=True)
    ).dt.total_seconds() / 86400.0
    llm_satd_repaid["resolution_days"] = llm_satd_repaid["resolution_days"].round(1)

    for col in [
        "lines_added",
        "lines_removed",
        "ast_actions_count",
        "between_commits",
        "num_modified_files_add",
    ]:
        llm_satd_repaid[col] = pd.to_numeric(llm_satd_repaid[col], errors="coerce")
    llm_satd_repaid["lines_modified"] = llm_satd_repaid["lines_added"] + llm_satd_repaid["lines_removed"]
    llm_satd_repaid["files_modified"] = llm_satd_repaid["num_modified_files_add"]

    repayment_time_by_category = (
        llm_satd_repaid
        .dropna(subset=["category", "resolution_days"])
        .groupby("category")
        .agg(
            median_resolution_days=("resolution_days", "median"),
            median_resolution_commits=("between_commits", "median"),
            sample_count=("resolution_days", "size"),
        )
        .reset_index()
        .sort_values(by="median_resolution_days", ascending=False)
    )
    repayment_time_by_category = repayment_time_by_category.round(1)
    repayment_time_by_category["sample_count"] = repayment_time_by_category["sample_count"].astype(int)

    repayment_effort_by_category = (
        llm_satd_repaid
        .dropna(subset=["category", "lines_modified", "ast_actions_count", "files_modified"])
        .groupby("category")
        .agg(
            median_lines_modified=("lines_modified", "median"),
            median_ast_actions=("ast_actions_count", "median"),
            median_files_modified=("files_modified", "median"),
            sample_count=("lines_modified", "size"),
        )
        .reset_index()
        .sort_values(by="median_lines_modified", ascending=False)
    )
    repayment_effort_by_category = repayment_effort_by_category.round(1)
    repayment_effort_by_category["sample_count"] = repayment_effort_by_category["sample_count"].astype(int)

    developer_roles = (
        satd
        .dropna(subset=["developer_role"])
        .groupby("developer_role")
        .size()
        .reset_index(name="count")
        .sort_values(by="count", ascending=False)
    )
    developer_roles["count"] = developer_roles["count"].astype(int)

    def repayment_cross_table(df_repaid: pd.DataFrame) -> pd.DataFrame:
        roles = ["CONTRIBUTOR", "MAINTAINER"]
        subset = df_repaid[
            df_repaid["introducer_role"].isin(roles)
            & df_repaid["remover_role"].isin(roles)
        ]
        counts = (
            pd.crosstab(subset["remover_role"], subset["introducer_role"])
            .reindex(index=roles, columns=roles, fill_value=0)
        )
        counts["Total"] = counts.sum(axis=1)
        counts.loc["Total"] = counts.sum(axis=0)
        perc = counts / counts.loc["Total", "Total"] * 100
        perc.index.name = "repayer_role"
        return perc.round(2)

    def repayment_cross_table_output(table: pd.DataFrame, label: str) -> pd.DataFrame:
        output = table.reset_index()
        output.insert(0, "satd_type", label)
        return output

    def _format_value(value: object) -> object:
        if pd.isna(value):
            return value
        if isinstance(value, (int,)):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return str(value)
        return value

    def _format_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        formatted = frame.copy()
        for column in columns:
            if column in formatted.columns:
                formatted[column] = formatted[column].map(_format_value)
        return formatted

    repayment_time_by_category = _format_frame(
        repayment_time_by_category,
        ["median_resolution_days", "median_resolution_commits", "sample_count"],
    )
    repayment_effort_by_category = _format_frame(
        repayment_effort_by_category,
        ["median_lines_modified", "median_ast_actions", "median_files_modified", "sample_count"],
    )
    developer_roles = _format_frame(developer_roles, ["count"])
    llm_repayment_share = repayment_cross_table(llm_satd_repaid)
    non_llm_repayment_share = repayment_cross_table(non_llm_satd_repaid)
    repayment_share_output = pd.concat(
        [
            repayment_cross_table_output(llm_repayment_share, "LLM-SATD"),
            repayment_cross_table_output(non_llm_repayment_share, "Non-LLM-SATD"),
        ],
        ignore_index=True,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repayment_time_by_category.to_csv(
        output_dir / "discussion_repayment_time_by_category.csv",
        index=False,
    )
    repayment_effort_by_category.to_csv(
        output_dir / "discussion_repayment_effort_by_category.csv",
        index=False,
    )
    repayment_share_output.to_csv(
        output_dir / "discussion_repayment_share_by_role.csv",
        index=False,
    )

    print("Discussion outputs written to:", output_dir)
    print("\nRepayment time by category:")
    print(repayment_time_by_category.to_string(index=False))
    print("\nRepayment effort by category:")
    print(repayment_effort_by_category.to_string(index=False))
    print("\nDeveloper roles:")
    print(developer_roles.to_string(index=False))
    print("\nLLM-SATD repayment share (%):")
    print(llm_repayment_share.to_string())
    print("\nNon-LLM-SATD repayment share (%):")
    print(non_llm_repayment_share.to_string())


if __name__ == "__main__":
    main()
