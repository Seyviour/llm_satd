import argparse
import csv
import os
from datetime import datetime
from pydriller import Repository
from git import Repo, GitCommandError
from functools import lru_cache
from collections import Counter
from pathlib import Path
import sys
import re
from git import Repo, GitCommandError, BadName

# ,Repo Name,Commit Hash,Commit Date,File Path,Comment,still_exists,line_number,context,Context,kl_satd,
SINCE_DATE = datetime(2023, 8, 1)
UNAVAILABLE = "<<unavailable>>"

# from git import GitCommandError

@lru_cache(maxsize=128)
def get_file_content_at_commit(repo, commit_hash, path):
    try:
        return repo.git.show(f"{commit_hash}:{path}")
    except GitCommandError:
        return ""

def blame_for_line(repo, filepath, line_content):
    try:
        blame_output = repo.git.blame('--line-porcelain', filepath)
        for block in blame_output.split('\n\n'):
            if line_content in block:
                return block.splitlines()[0].split()[0]  # commit hash
    except GitCommandError:
        pass
    return None

def get_introducing_commit(repo, line_content, filepath, target_commit):
    line_is_in_first_commit = False
    try:
        # Step 1: Try to find the commit that added the file
        creation_commits = repo.git.log(
            '--diff-filter=A',
            '--pretty=format:%H',
            '--', filepath
        ).splitlines()

        if creation_commits:
            creation_commit = creation_commits[-1]
            file_content = get_file_content_at_commit(repo, creation_commit, filepath)
            if line_content in file_content:
                line_is_in_first_commit = True

        # Step 2: Try -S and -G grep-style searches
        grep_strategies = [
            ('-S', line_content),
            ('-G', re.escape(line_content)),
        ]

        for grep_flag, pattern in grep_strategies:
            log_args = [
            '--reverse',
            grep_flag, pattern,
            '--name-only',
            '--pretty=format:%H',
            f'{target_commit}^',
            '--', filepath
            ]
            if grep_flag == '-G':
                log_args.prepend('--follow')
            logs = repo.git.log(*log_args).splitlines()

            if len(logs) >= 2:
                return {'hash': logs[0], 'filepath': logs[1], "method":f'LOG{grep_flag}', "line_is_in_first_commit": line_is_in_first_commit}

        # Step 3: Fallback to blame if line still exists
        commit_from_blame = blame_for_line(repo, filepath, line_content)
        if commit_from_blame:
            return {'hash': commit_from_blame, 'filepath': filepath, 'method':'BLAME', "line_is_in_first_commit": line_is_in_first_commit}

        if line_is_in_first_commit:
            return {'hash': creation_commit, 'filepath': filepath, 'method':"FIRST", "line_is_in_first_commit": line_is_in_first_commit}

        return {'hash': UNAVAILABLE, 'filepath': filepath, 'method':UNAVAILABLE, 'line_is_in_first_commit': line_is_in_first_commit}

    except (GitCommandError, Exception):
        return {'hash': UNAVAILABLE, 'filepath': UNAVAILABLE, 'method':UNAVAILABLE, 'line_is_in_first_commit': UNAVAILABLE}

def get_commit_info(repo: Repo, commit_hash: str) -> dict:
    """Retrieves metadata (author, date, etc.) for a given commit hash using GitPython."""
    try:
        commit = repo.commit(commit_hash)
        return {
            "hash": commit.hexsha,
            "author": commit.author.name,
            "author_email": commit.author.email,
            "date": commit.authored_datetime.isoformat(),
            "num_modified_files": len(commit.stats.files)
        }
    except (GitCommandError, BadName, ValueError, AttributeError) as e:
        return {
            "hash": UNAVAILABLE,
            "author": UNAVAILABLE,
            "author_email": UNAVAILABLE,
            "date": UNAVAILABLE,
            "num_modified_files": UNAVAILABLE
        }


def get_context(file_content_lines, line_index, context_size=10):
    """
    Extracts a window of lines around a specific line index from a list of lines.
    Handles edge cases where the line is near the start or end of the file.
    """
    if not file_content_lines or line_index < 0:
        return UNAVAILABLE
        
    start = max(0, line_index - context_size)
    end = min(len(file_content_lines), line_index + context_size + 1)
    
    context_lines = file_content_lines[start:end]
    return "\n".join(context_lines)

def analyze_deleted_comments(repo_path, repo):
    """
    Analyzes the commit history to find deleted comments and the context
    surrounding them at the time of introduction and deletion.
    """
    print("Scanning for DELETED comments...")
    results = []
    for commit in Repository(repo_path, since=SINCE_DATE, only_modifications_with_file_types=['.py'], histogram_diff=False).traverse_commits():
        is_merge_commit = len(commit.parents) > 1
        for mod in commit.modified_files:
            if not mod.filename.endswith(".py") or not mod.diff_parsed: 
                continue

            num_modified_files_deletion = len(commit.modified_files)
            
            # Count lines added and removed in this commit for this file
            lines_added = sum(1 for _ in mod.diff_parsed.get("added", []))
            lines_removed = sum(1 for _ in mod.diff_parsed.get("deleted", []))
            
            # Only count lines added/removed in the current file (not all files in the commit)
            file_lines_added = sum(1 for ln, _ in mod.diff_parsed.get("added", []) if mod.new_path and (mod.new_path == mod.old_path or mod.old_path is None))
            file_lines_removed = sum(1 for ln, _ in mod.diff_parsed.get("deleted", []) if mod.old_path and (mod.old_path == mod.new_path or mod.new_path is None))
    
            filepath = mod.old_path or mod.new_path
            source_before_lines = mod.source_code_before.splitlines() if mod.source_code_before else []

            # line_num is 1-based, so we convert to 0-based index for list access

            added_lines = mod.diff_parsed.get("added", [])
            added_line_contents = [line_content.strip() for _, line_content in added_lines]
            added_line_counts = Counter(added_line_contents)
            for line_num, line_content in mod.diff_parsed.get("deleted", []):
                #spurious if the line is not in the difference between deleted and added lines    
                line_stripped = line_content.strip()
                if line_stripped in added_line_counts and added_line_counts[line_stripped] > 0:
                    # If the line was added in this commit, we skip it
                    added_line_counts[line_stripped] -= 1
                    is_spurious = True
                else:
                    is_spurious = False
                if not line_stripped.startswith("#"):
                    continue

                # Get context from the state *before* this deleting commit
                deleting_context = get_context(source_before_lines, line_num - 1)
                origin_data = get_introducing_commit(repo, line_stripped, filepath, commit.hash)
                origin_hash, origin_filepath = origin_data.get("hash"), origin_data.get("filepath")
                origin_track_method = origin_data.get("method", UNAVAILABLE)
                line_is_in_first_commit = origin_data.get("line_is_in_first_commit", UNAVAILABLE)

                # Get context from the introducing commit
                introducing_context = UNAVAILABLE
                intro_line_index = -1
                try:
                    intro_content = repo.git.show(f"{origin_hash}:{filepath}")
                    intro_content_lines = intro_content.splitlines()
                    for i, line in enumerate(intro_content_lines):
                        if line.strip() == line_stripped:
                            intro_line_index = i
                            break
                    if intro_line_index != -1:
                        introducing_context = get_context(intro_content_lines, intro_line_index)
                except (GitCommandError, Exception):
                    introducing_context = UNAVAILABLE # File might not be retrievable at that hash

                add_info = get_commit_info(repo, origin_hash)
                del_info = get_commit_info(repo, commit.hash)

                if not add_info or not del_info:
                    continue
                
                # Count commits between introducing and deleting commit (inclusive)
                try:
                    between_commits = sum(1 for _ in repo.iter_commits(f"{add_info['hash']}..{del_info['hash']}")) + 1
                except Exception:
                    between_commits = UNAVAILABLE

                results.append({
                    "status": "DELETED",
                    "file_path": filepath,
                    "id_in_repo": len(results),
                    "comment": line_stripped,
                    "introducing_commit": add_info["hash"],
                    "introducing_author": add_info["author"],
                    "introducing_date": add_info["date"],
                    "intro_line_index": intro_line_index,
                    "delete_line_index": line_num-1,
                    "deleting_commit": del_info["hash"],
                    "deleting_author": del_info["author"],
                    "deleting_date": del_info["date"],
                    "context_at_introduction": introducing_context,
                    "context_at_deletion_or_current": deleting_context,
                    "lines_added": lines_added,
                    "lines_removed": lines_removed,
                    "file_lines_added": file_lines_added,
                    "file_lines_removed": file_lines_removed,
                    "between_commits": between_commits,
                    "introducing_track_method": origin_track_method,
                    "num_modified_files_add": add_info.get("num_modified_files", UNAVAILABLE),
                    "num_modified_files_deletion": del_info.get("num_modified_files", UNAVAILABLE),
                    "introducing_author_email": add_info.get("author_email", UNAVAILABLE),
                    "deleting_author_email": del_info.get("author_email", UNAVAILABLE),
                    "spurious": is_spurious,
                    "is_merge_commit": is_merge_commit,
                    "line_is_in_first_commit": line_is_in_first_commit
                })
    print(f"Found {len(results)} deleted comments.\n")
    return results

def analyze_current_comments(repo_path, repo):
    """
    Analyzes the current repository state (HEAD) to find active comments
    and their context at introduction and in the current version.
    """
    print("Scanning for ACTIVE comments in current repository state...")
    results = []
    try:
        tracked_files = [item for item in repo.git.ls_files().split('\n') if item.endswith('.py')]
    except (GitCommandError, Exception):
        print("Could not list files. Is the repository empty?")
        return []

    for filepath in tracked_files:
        try:
            content = repo.git.show(f"HEAD:{filepath}")
            content_lines = content.splitlines()
        except (GitCommandError, Exception):
            continue

        for line_index, line in enumerate(content_lines):
            line_stripped = line.strip()
            if not line_stripped.startswith("#"):
                continue

            # Context from the current file state (HEAD)
            current_context = get_context(content_lines, line_index)
            origin_data = get_introducing_commit(repo, line_stripped, filepath, "HEAD")
            origin_hash, origin_filepath = origin_data.get("hash"), origin_data.get("filepath")
            origin_track_method = origin_data.get("method", UNAVAILABLE)
            line_is_in_first_commit = origin_data.get("line_is_in_first_commit", UNAVAILABLE)

            # Context from the introducing commit
            introducing_context = None
            intro_line_index = -1
            try:
                intro_content = repo.git.show(f"{origin_hash}:{origin_filepath}")
                intro_content_lines = intro_content.splitlines()
                for i, intro_line in enumerate(intro_content_lines):
                    if intro_line.strip() == line_stripped:
                        intro_line_index = i
                        break
                if intro_line_index != -1:
                    introducing_context = get_context(intro_content_lines, intro_line_index)
            except (GitCommandError, Exception):
                pass
            add_info = get_commit_info(repo, origin_hash)
               
            # Count commits between introducing commit and HEAD (inclusive)
            try:
                between_commits = sum(1 for _ in repo.iter_commits(f"{add_info['hash']}..HEAD")) + 1
            except Exception:
                between_commits = UNAVAILABLE

            results.append({
                "status": "ACTIVE",
                "id_in_repo": len(results),
                "file_path": filepath,
                "comment": line_stripped,
                "introducing_commit": add_info["hash"],
                "introducing_author": add_info["author"],
                "introducing_date": add_info["date"],
                "intro_line_index": intro_line_index,
                "delete_line_index": UNAVAILABLE, 
                "deleting_commit": UNAVAILABLE,
                "deleting_author": UNAVAILABLE,
                "deleting_date": UNAVAILABLE,
                "context_at_introduction": introducing_context,
                "context_at_deletion_or_current": current_context,
                "lines_added": 0,
                "lines_removed": 0,
                "file_lines_added": 0,
                "file_lines_removed": 0,
                "between_commits": between_commits,
                "introducing_track_method": origin_track_method,
                "num_modified_files_add": add_info.get("num_modified_files", UNAVAILABLE),
                "num_modified_files_deletion": UNAVAILABLE,
                "introducing_author_email": add_info.get("author_email", UNAVAILABLE),
                "deleting_author_email": UNAVAILABLE,
                "spurious": UNAVAILABLE,
                "is_merge_commit": UNAVAILABLE,
                "line_is_in_first_commit": line_is_in_first_commit
            })
    print(f"Found {len(results)} active comments.\n")
    return results

def run_analysis(repo_path, csv_path=None):
    """
    Main function to run analyses and print/save results.
    """
    if not os.path.isdir(repo_path):
        print(f"Error: Repository path not found at '{repo_path}'")
        return

    try:
        repo = Repo(repo_path)
    except Exception as e:
        print(f"Error initializing repository at '{repo_path}': {e}")
        return
    
    # Count commits in the repository's default branch
    try:
        default_branch = repo.head.reference.name
        commit_count = sum(1 for _ in repo.iter_commits(default_branch))
        print(f"Total commits in default branch '{default_branch}': {commit_count}")
    except Exception as e:
        print(f"Could not count commits in default branch: {e}")
        commit_count = -1
        
    repo_name = os.path.basename(os.path.abspath(repo_path))
    username = os.path.basename(os.path.dirname(os.path.abspath(repo_path)))
    full_name = f"{username}/{repo_name}"

    deleted = analyze_deleted_comments(repo_path, repo)
    active = analyze_current_comments(repo_path, repo)
    all_results = deleted + active
    
    print("-" * 60)
    print(f"Analysis Complete for repository: {full_name}")
    print(f"Total comments found: {len(all_results)} ({len(active)} ACTIVE, {len(deleted)} DELETED)")
    print("-" * 60)


    if csv_path:
        print(f"Writing {len(all_results)} results to {csv_path}...")
        if not all_results:
            print("No data to write.")
            return

        with open(csv_path, "w", newline="", encoding="utf-8", errors='replace') as f:
            headers = [
                "full_name", "status", "id_in_repo", "file_path", "comment",
                "introducing_commit", "introducing_author", "introducing_author_email", "introducing_date",
                "deleting_commit", "deleting_author", "deleting_author_email", "deleting_date",
                "context_at_introduction", "context_at_deletion_or_current", 
                "intro_line_index", "delete_line_index", "lines_added", "lines_removed",
                "file_lines_added", "file_lines_removed", "commit_count", "between_commits",
                "introducing_track_method", "num_modified_files_add", "num_modified_files_deletion", "is_merge_commit", "spurious",
                "line_is_in_first_commit"
            ]
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for res in all_results:
                res["full_name"] = full_name
                res["commit_count"] = commit_count
                writer.writerow(res)
        print("Successfully wrote results to CSV.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Finds the origin and context of all active and deleted comments in a Git repository."
    )
    parser.add_argument("repo", help="Path to the local Git repository.")
    parser.add_argument(
        "--output",
        help="Optional. Path to save the output CSV file.",
        nargs='?',
        default=None
    )
    args = parser.parse_args()
    
    csv_output_path = args.output
    if csv_output_path is None:
        repo_name = os.path.basename(os.path.abspath(args.repo))
        csv_output_path = f"{repo_name}_comment_analysis.csv"

    run_analysis(args.repo, csv_output_path)
