REPO_FILE="chosen_repo_names.txt"
MAX_JOBS="10"  # Max concurrent clone jobs
LOG_FILE="clone_errors_$(date +%Y%m%d_%H%M%S).log"

bash clone_repos.sh "$REPO_FILE" "$MAX_JOBS" "$LOG_FILE"
