#!/bin/bash
set -euo pipefail

REPO_FILE="${1:-chosen_repo_names.txt}"
CLONE_BASE_DIR="${2:-cloned_repos}"
DATA_BASE_DIR="${3:-extracted_comments}"
MAX_JOBS="${4:-10}"  # Max concurrent jobs
LOG_FILE="${5:-clone_errors_$(date +%Y%m%d_%H%M%S).log}"

if [ ! -f "$REPO_FILE" ]; then
    echo "File $REPO_FILE not found!" >&2
    exit 1
fi

process_repo() {
    local path="$1"
    local username repo
    username=$(echo "$path" | cut -d/ -f1)
    repo=$(echo "$path" | cut -d/ -f2)

    local clone_target="$CLONE_BASE_DIR/$username/$repo"
    local data_target_file="$DATA_BASE_DIR/$username/$repo.csv"
    local tarball="${CLONE_BASE_DIR}/${username}/${repo}.tar.gz"

    mkdir -p "$clone_target"
    mkdir -p "$(dirname "$data_target_file")"

    if [[ ! -f "$tarball" ]]; then
        echo "Tarball $tarball not found" >> "$LOG_FILE"
        return
    fi

    if ! tar -xzf "$tarball" -C "$clone_target" --strip-components=1; then
        echo "Failed to extract $tarball for repo $path" >> "$LOG_FILE"
        return
    fi

    if ! python extract_comments.py --output "$data_target_file" "$clone_target"; then
        echo "Failed to extract comments for $path" >> "$LOG_FILE"
    else
        echo "Successfully processed $path; extracted data stored at $data_target_file" >> "$LOG_FILE"
    fi
    rm -rf "$clone_target"
    echo "Deleted clone directory $clone_target for $path" >> "$LOG_FILE"
}

job_count=0
while read -r repo; do
    process_repo "$repo" &
    ((job_count++))

    if (( job_count >= MAX_JOBS )); then
        wait -n
        ((job_count--))
    fi
done < "$REPO_FILE"

wait
echo "Done. Processed $(wc -l < "$REPO_FILE") repos."
echo "Check $LOG_FILE for any errors or logs."