#!/bin/bash

REPO_FILE="${1:-../sample_projects.txt}"
MAX_JOBS="${2:-10}"  # Max concurrent clone jobs
LOG_FILE="${3:-clone_errors_$(date +%Y%m%d_%H%M%S).log}"
BASE_DIR="${4:-cloned_repos}"

if [ ! -f "$REPO_FILE" ]; then
    echo "File $REPO_FILE not found!"
    exit 1
fi


clone_into_user_dir() {
    path="$1"

    # Extract username and repo from the URL
    # path=$(echo "$url" | sed -E 's#(https?://)?github\.com/([^/]+)/([^/]+)(\.git)?/?#\2/\3#')
    url="https://github.com/$path"

    username=$(echo "$path" | cut -d/ -f1)
    repo=$(echo "$path" | cut -d/ -f2)

    # Create the username directory if it doesn't exist
    mkdir -p "$BASE_DIR/$username"

    # Clone into username/repo
    target="$BASE_DIR/$username/$repo"
    tarball="${target}.tar.gz"
    if [ -d "$target/.git" ]; then
        echo "Repo already cloned: $target" >>"$LOG_FILE"
        echo "Compressing $target to $tarball"
        tar -czf "$tarball" -C "$BASE_DIR/$username" "$repo"
        rm -rf "$target"
    elif [ -f "${target}.tar.gz" ]; then
        echo "Tarball already exists: ${target}.tar.gz" >>"$LOG_FILE"
        return
    else
        echo "Cloning $url into $target"
        GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch "$url" "$target"  2>>"$LOG_FILE"
        if [ $? -ne 0 ]; then
            echo "Failed: $repo" >> "$LOG_FILE"
        else
            # Compress the repo after successful clone
            echo "Compressing $target to $tarball"
            tar -czf "$tarball" -C "$BASE_DIR/$username" "$repo"
            rm -rf "$target"
        fi
    fi
}

job_count=0
while read -r repo; do
    clone_into_user_dir "$repo" &
    ((job_count++))

    # Wait if we reach the max job count
    if (( job_count >= MAX_JOBS )); then
        wait -n  # Wait for any job to finish
        ((job_count--))
    fi
done < "$REPO_FILE"

wait  # Wait for remaining jobs
echo "Done. Check $LOG_FILE for any failed clones."
