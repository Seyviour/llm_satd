from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH: Path = PROJECT_ROOT / "data" / "llm_satd_dataset.csv"
DEFAULT_LABELLED_SAMPLE_PATH: Path = PROJECT_ROOT / "data" / "ratings_rq3" / "consensus.csv"
DEFAULT_MAINTAINERS_PATH: Path = PROJECT_ROOT / "data" / "repo_maintainers.json"

CUTOFF_START = pd.Timestamp("2022-11-30", tz="UTC")
CUTOFF_END = pd.Timestamp("2025-06-30", tz="UTC")


def _convert_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if "between_commits" in frame.columns:
        cleaned = frame["between_commits"].replace({"<<unavailable>>": None})
        frame["between_commits"] = pd.to_numeric(cleaned, errors="coerce")
    if "ast_actions_count" in frame.columns:
        frame["ast_actions_count"] = pd.to_numeric(frame["ast_actions_count"], errors="coerce")
    return frame


def _attach_category_labels(frame: pd.DataFrame, label_path: Path) -> pd.DataFrame:
    labels = pd.read_csv(label_path)
    labels = labels[
        labels["category"].notna()
        & (labels["category"] != "")
    ]
    labels = labels[
        "full_name file_path context_at_introduction "
        "context_at_deletion_or_current comment category subcategory introducing_commit"
        .split()
    ]
    join_keys = [
        "full_name",
        "file_path",
        "context_at_introduction",
        "context_at_deletion_or_current",
        "comment",
        "introducing_commit",
    ]
    duplicate_labels = labels.duplicated(subset=join_keys, keep=False)
    if duplicate_labels.any():
        duplicates = labels.loc[duplicate_labels, join_keys]
        raise ValueError(
            "Labelled sample contains duplicate rows for the join keys; "
            "cannot uniquely map categories/sub-categories.\n"
            f"{duplicates.head(5).to_string(index=False)}"
        )
    merged = frame.merge(
        labels,
        how="left",
        on=join_keys,
        suffixes=("", "_label"),
    )
    if len(merged) != len(frame):
        raise ValueError(
            "Labelled sample mapping is not one-to-one; merge expanded rows. "
            "Ensure the labelled_sample entries are unique for the join keys."
        )
    return merged


def load_dataset(path: Optional[Union[str, Path]] = None) -> pd.DataFrame:
    dataset_path = Path(path) if path is not None else DEFAULT_DATASET_PATH
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found at: {dataset_path}")

    frame = pd.read_csv(dataset_path)
    frame = _convert_numeric_columns(frame)

    if "spurious" in frame.columns:
        mask = ~frame["spurious"].astype(str).str.lower().eq("true")
        frame = frame.loc[mask].copy()
    return frame


@dataclass(frozen=True)
class SATDSubsets:
    source_path: Path
    satd: pd.DataFrame
    satd_active: pd.DataFrame
    satd_repaid: pd.DataFrame
    llm_satd: pd.DataFrame
    llm_satd_active: pd.DataFrame
    llm_satd_repaid: pd.DataFrame
    non_llm_satd: pd.DataFrame
    non_llm_satd_active: pd.DataFrame
    non_llm_satd_repaid: pd.DataFrame

    def as_dict(self) -> Dict[str, pd.DataFrame]:
        """Return all subsets in a plain dictionary keyed by subset name."""
        return {
            "satd": self.satd,
            "satd_active": self.satd_active,
            "satd_repaid": self.satd_repaid,
            "llm_satd": self.llm_satd,
            "llm_satd_active": self.llm_satd_active,
            "llm_satd_repaid": self.llm_satd_repaid,
            "non_llm_satd": self.non_llm_satd,
            "non_llm_satd_active": self.non_llm_satd_active,
            "non_llm_satd_repaid": self.non_llm_satd_repaid,
        }

    def __getitem__(self, key: str) -> pd.DataFrame:
        return self.as_dict()[key]

def load_satd_dataset(
    path = None,
    *,
    labelled_sample_path = None,
) -> SATDSubsets:
    dataset_path = Path(path) if path is not None else DEFAULT_DATASET_PATH
    all_data = load_dataset(dataset_path).copy()
    label_path = (
        Path(labelled_sample_path)
        if labelled_sample_path is not None
        else DEFAULT_LABELLED_SAMPLE_PATH
    )
    if label_path.exists():
        all_data = _attach_category_labels(all_data, label_path)
    deleting_dates = all_data["deleting_date"].replace({"<<unavailable>>": pd.NA, "unavailable": pd.NA})
    rem_dt = pd.to_datetime(deleting_dates, errors="coerce", utc=True)
    future_mask = rem_dt > CUTOFF_END
    all_data.loc[future_mask, "deleting_date"] = "<<unavailable>>"
    introducing_dt = pd.to_datetime(all_data.get("introducing_date"), errors="coerce", utc=True)
    date_mask = introducing_dt.notna()
    date_mask &= introducing_dt >= CUTOFF_START
    date_mask &= introducing_dt < CUTOFF_END
    all_data = all_data.loc[date_mask].copy()

    if "introduction_github_id" in all_data.columns:
        bot_mask = ~all_data["introduction_github_id"].fillna("").str.lower().str.endswith("[bot]")
        all_data = all_data.loc[bot_mask].copy()

    if "spurious" in all_data.columns:
        spurious_mask = ~all_data["spurious"].astype(str).str.lower().eq("true")
        all_data = all_data.loc[spurious_mask].copy()

    if "file_path" in all_data.columns:
        site_packages_mask = ~all_data["file_path"].fillna("").str.contains(
            "/site-packages/",
            case=False,
            regex=False,
        )
        all_data = all_data.loc[site_packages_mask].copy()

    all_data = all_data.copy()
    all_data["is_llm_satd"] = (
        all_data.get("is_context_llm", False).fillna(False).astype(bool)
        & all_data.get("is_comment_satd", False).fillna(False).astype(bool)
    )
    if "has_code_in_context" in all_data.columns:
        all_data = all_data[all_data["has_code_in_context"].fillna(False).astype(bool)].copy()
    if "full_name" in all_data.columns:
        all_data["project_has_both"] = all_data.groupby("full_name")["is_llm_satd"].transform(
            lambda x: x.any() and (~x).any()
        )
    status_normalised = all_data["status"].astype(str).str.upper().str.strip()
    all_data_active = all_data.loc[status_normalised == "ACTIVE"].copy()
    all_data_repaid = all_data.loc[status_normalised == "DELETED"].copy()

    satd = all_data.copy()
    satd_status = satd["status"].astype(str).str.upper().str.strip()
    satd_active = satd.loc[satd_status == "ACTIVE"].copy()
    satd_repaid = satd.loc[satd_status == "DELETED"].copy()

    llm_satd_mask = satd["is_llm_satd"].fillna(False).astype(bool)
    llm_satd = satd.loc[llm_satd_mask].copy()
    llm_status = llm_satd["status"].astype(str).str.upper().str.strip()
    llm_satd_active = llm_satd.loc[llm_status == "ACTIVE"].copy()
    llm_satd_repaid = llm_satd.loc[llm_status == "DELETED"].copy()

    non_llm_satd = satd.loc[~llm_satd_mask].copy()
    non_llm_status = non_llm_satd["status"].astype(str).str.upper().str.strip()
    non_llm_satd_active = non_llm_satd.loc[non_llm_status == "ACTIVE"].copy()
    non_llm_satd_repaid = non_llm_satd.loc[non_llm_status == "DELETED"].copy()

    return SATDSubsets(
        source_path=dataset_path.resolve(),
        satd=satd,
        satd_active=satd_active,
        satd_repaid=satd_repaid,
        llm_satd=llm_satd,
        llm_satd_active=llm_satd_active,
        llm_satd_repaid=llm_satd_repaid,
        non_llm_satd=non_llm_satd,
        non_llm_satd_active=non_llm_satd_active,
        non_llm_satd_repaid=non_llm_satd_repaid,
    )


def load_repo_maintainers(path: Optional[Union[str, Path]] = None) -> Dict[str, Dict[str, object]]:
    maintainers_path = Path(path) if path is not None else DEFAULT_MAINTAINERS_PATH
    return json.loads(maintainers_path.read_text())


def assign_role(
    row: pd.Series,
    login_col: str,
    repo_col: str,
    maintainers: Dict[str, Dict[str, object]],
) -> str:
    login = row[login_col]
    repo = str(row[repo_col]).lower()
    if str(login).lower() in ["<<unavailable>>", "unavailable"]:
        return "UNAVAILABLE"
    repo_maintainers = maintainers.get(repo, {})
    login_lower = str(login).lower()
    if login_lower in repo_maintainers:
        return "MAINTAINER"
    return "CONTRIBUTOR"
