
import argparse
import os
import re
import time
from typing import Optional

import pandas as pd
import requests

try:
    # Load GITHUB_TOKEN from a local .env if python-dotenv is available.
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

GITHUB_API_URL = "https://api.github.com/repos/"
LINK_LAST_RE = re.compile(r"[?&]page=(\d+)>; rel=\"last\"")


def parse_last_page(link_header: str) -> Optional[int]:
    """Extract the last page number from a GitHub Link header."""
    if not link_header:
        return None
    match = LINK_LAST_RE.search(link_header)
    if match:
        return int(match.group(1))
    return None


def handle_rate_limit(response: requests.Response) -> bool:
    """Sleep until the GitHub rate limit resets. Returns True if we should retry."""
    if response.status_code != 403:
        return False
    if response.headers.get("X-RateLimit-Remaining") != "0":
        return False

    reset_at = response.headers.get("X-RateLimit-Reset")
    if reset_at:
        sleep_for = max(int(reset_at) - int(time.time()), 0) + 1
        print(f"Rate limit reached. Sleeping {sleep_for} seconds before retrying.")
        time.sleep(sleep_for)
        return True
    return False


def fetch_commit_count(full_name: str, session: requests.Session, token: Optional[str]) -> Optional[int]:
    """Return the commit count for a repository or None if it cannot be determined."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"{GITHUB_API_URL}{full_name}/commits"
    params = {"per_page": 1, "page": 1}

    for attempt in range(3):
        resp = session.get(url, headers=headers, params=params, timeout=30)

        if handle_rate_limit(resp):
            continue

        if resp.status_code == 409:  # Empty repository
            return 0
        if resp.status_code == 404:
            print(f"Repository not found: {full_name}")
            return None
        if resp.ok:
            last_page = parse_last_page(resp.headers.get("Link", ""))
            if last_page is not None:
                return last_page

            # No Link header means 0 or 1 commits; count the returned items.
            try:
                return len(resp.json())
            except Exception:
                return None

        print(f"Attempt {attempt + 1} failed for {full_name} with status {resp.status_code}. Retrying...")
        time.sleep(2 ** attempt)

    print(f"Failed to fetch commit count for {full_name} after multiple attempts.")
    return None


def main():
    parser = argparse.ArgumentParser(description="Count commits for repositories listed in a CSV file.")
    parser.add_argument(
        "--input-file",
        default="repo_sampling/output/chosen_repos.csv",
        help="CSV containing a 'full_name' column (e.g., owner/repo). Default: repo_sampling/output/chosen_repos.csv",
    )
    parser.add_argument(
        "--output-file",
        default="repo_sampling/output/chosen_repos_with_commits.csv",
        help="Where to write the CSV with an added commit_count column.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub token for authenticated requests (defaults to GITHUB_TOKEN env var).",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.input_file)
    if "full_name" not in df.columns:
        raise ValueError("Input CSV must contain a 'full_name' column with owner/repo values")

    session = requests.Session()
    commit_counts = []
    for full_name in df["full_name"]:
        if not isinstance(full_name, str) or not full_name.strip():
            commit_counts.append(None)
            continue
        count = fetch_commit_count(full_name.strip(), session, args.token)
        # print(f"{full_name}: {count}")
        commit_counts.append(count)

    df["commit_count"] = commit_counts
    df.to_csv(args.output_file, index=False)
    print(f"Wrote commit counts for {len(df)} repositories to {args.output_file}")


if __name__ == "__main__":
    main()
