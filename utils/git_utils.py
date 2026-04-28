from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd
from git import Repo
from git.exc import BadName, InvalidGitRepositoryError, NoSuchPathError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Keep default in sync with clone_repositories.sh output layout:
# cloned_repos/<owner>/<repo>
DEFAULT_REPO_ROOT = PROJECT_ROOT / "cloned_repos"
UNAVAILABLE_TOKEN = "<<unavailable>>"
PathLike = Union[str, Path]


def get_repo(repo_loc: PathLike, repo_name: str) -> Repo:
    """
    Retrieve a Git repository object given its location and name.

    :param repo_loc: The location (directory) of the repository.
    :param repo_name: The name of the repository.
    """
    if not repo_name:
        raise ValueError("repo_name must be provided")

    base_path = Path(repo_loc).expanduser()
    repo_path = (base_path / repo_name).resolve()

    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    try:
        return Repo(repo_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise ValueError(f"Path is not a Git repository: {repo_path}") from exc


def get_file_at_commit(repo: Repo, commit_sha: str, file_path: PathLike) -> str:
    """
    Retrieve the contents of a file at a specific commit in a Git repository.

    :param repo: The Git repository object.
    :param commit_sha: The SHA of the commit.
    :param file_path: The path to the file within the repository.
    :return: The contents of the file as a string.
    """
    if not commit_sha:
        raise ValueError("commit_sha must be provided")

    normalized_path = str(file_path).strip().replace("\\", "/").lstrip("/")
    if not normalized_path:
        raise ValueError("file_path must not be empty")

    try:
        commit = repo.commit(commit_sha)
    except (BadName, ValueError) as exc:
        raise ValueError(f"Unknown commit: {commit_sha}") from exc

    try:
        blob = commit.tree / normalized_path
    except KeyError as exc:
        raise FileNotFoundError(
            f"File '{normalized_path}' does not exist in commit '{commit_sha}'"
        ) from exc

    if blob.type != "blob":
        raise IsADirectoryError(
            f"Path '{normalized_path}' in commit '{commit_sha}' is a directory"
        )

    data = blob.data_stream.read()
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)


def _normalize_commit_sha(value: object) -> Optional[str]:
    if value is None:
        return None
    commit = str(value).strip()
    if not commit or commit == UNAVAILABLE_TOKEN:
        return None
    return commit


def _resolve_repo(full_name: str, repo_root: Path, cache: Dict[str, Optional[Repo]]) -> Optional[Repo]:
    if full_name in cache:
        return cache[full_name]

    parts = full_name.split("/", 1)
    if len(parts) != 2:
        print(f"[WARN] Unexpected repository name format: '{full_name}'")
        cache[full_name] = None
        return None
    owner, repo_name = parts
    if not repo_name:
        cache[full_name] = None
        return None

    repo_loc = repo_root / owner
    try:
        cache[full_name] = get_repo(repo_loc, repo_name)
    except Exception as exc:
        print(f"[WARN] Unable to open repo for {full_name}: {exc}")
        cache[full_name] = None
    return cache[full_name]


def _safe_file_contents(repo: Optional[Repo], commit_sha: Optional[str], file_path: str) -> Optional[str]:
    if repo is None or not commit_sha:
        return None
    try:
        return get_file_at_commit(repo, commit_sha, file_path)
    except Exception as exc:
        print(f"[WARN] Failed to read '{file_path}' at {commit_sha}: {exc}")
        return None


def _previous_commit_sha(repo: Optional[Repo], commit_sha: Optional[str]) -> Optional[str]:
    if repo is None or not commit_sha:
        return None
    try:
        commit = repo.commit(commit_sha)
    except Exception as exc:
        print(f"[WARN] Could not load commit {commit_sha}: {exc}")
        return None
    parent = commit.parents[0] if commit.parents else None
    return parent.hexsha if parent else None


def collect_commit_file_snapshots(
    frame: pd.DataFrame,
    *,
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> pd.DataFrame:
    """
    Augment SATD dataset rows with file contents from key commits.

    Adds three columns containing the file contents at the introducing commit,
    the deleting (repaying) commit, and the commit immediately before deleting.
    Repositories are expected under ``repo_root/<owner>/<repo>``, matching the
    layout produced by ``clone_repositories.sh``.

    :param frame: DataFrame mirroring has_satd_code_classified.csv schema.
    :param repo_root: Directory containing cloned repositories organised
        as cloned_repos/<owner>/<repo>.
    :return: Copy of the frame with additional columns.
    """

    required_columns = {"full_name", "file_path", "introducing_commit", "deleting_commit"}
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")

    repo_root = Path(repo_root).expanduser()
    if not repo_root.exists():
        raise FileNotFoundError(f"Repository root not found: {repo_root}")

    repo_cache: Dict[str, Optional[Repo]] = {}
    intro_out: list[Optional[str]] = []
    delete_out: list[Optional[str]] = []
    pre_delete_out: list[Optional[str]] = []

    for idx, row in frame.iterrows():
        full_name = str(row["full_name"]).strip()
        file_path = str(row["file_path"]).strip()
        introducing_sha = _normalize_commit_sha(row["introducing_commit"])
        deleting_sha = _normalize_commit_sha(row["deleting_commit"])

        repo = _resolve_repo(full_name, repo_root, repo_cache)
        intro_out.append(_safe_file_contents(repo, introducing_sha, file_path))
        delete_out.append(_safe_file_contents(repo, deleting_sha, file_path))

        prior_sha = _previous_commit_sha(repo, deleting_sha)
        pre_delete_out.append(_safe_file_contents(repo, prior_sha, file_path))

        if idx and idx % 500 == 0:
            print(f"Processed {idx} rows...")

    enriched = frame.copy()
    enriched["introducing_file_contents"] = intro_out
    enriched["deleting_file_contents"] = delete_out
    enriched["pre_deleting_file_contents"] = pre_delete_out
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Attach file contents from introducing and repaying commits to the SATD dataset. "
            "Run clone_repositories.sh first to ensure repos exist locally."
        )
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Path to a CSV dataset with columns matching has_satd_code_classified.csv",
    )
    parser.add_argument(
        "--full-name",
        type=str,
        help="Restrict processing to a single repository full_name (e.g., owner/repo).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Directory containing cloned repositories (default: cloned_repos under project root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to save the enriched CSV. Defaults to <dataset>_with_files.csv",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of rows processed (useful for testing).",
    )
    args = parser.parse_args()

    dataset_path = args.dataset.expanduser()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    frame = pd.read_csv(dataset_path)
    if args.full_name:
        target = args.full_name.strip()
        frame = frame.loc[frame["full_name"].astype(str).str.strip() == target].copy()
        print(f"Filtered dataset to repository '{target}', {len(frame)} rows to process")

    if args.limit is not None:
        frame = frame.head(args.limit)

    enriched = collect_commit_file_snapshots(frame, repo_root=args.repo_root)
    output_path = args.output or dataset_path.with_name(f"{dataset_path.stem}_with_files.csv")
    enriched.to_csv(output_path, index=False)
    print(f"Wrote enriched dataset with file contents to {output_path}")


if __name__ == "__main__":
    main()
