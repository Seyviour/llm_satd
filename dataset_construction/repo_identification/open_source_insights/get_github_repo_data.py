import argparse
import csv
import requests
import os
import time

# Define the fields to extract
FIELDNAMES = [
    "id", "description", "full_name", "watchers", "stargazers_count", "watchers_count",
    "homepage", "topics", "forks_count", "language", "size", "created_at", "updated_at",
    "pushed_at", "open_issues_count", "network_count", "subscribers_count"
]

GITHUB_API = "https://api.github.com/repos/"

def get_repo_info(repo_url, session, token=None):
    # Extract owner/repo from URL
    try:
        parts = repo_url.strip().rstrip('/').split('/')
        owner, repo = parts[-2], parts[-1]
    except Exception as e:
        print(e)
        return None

    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'

    retries = 3
    for attempt in range(retries):
        try:
            resp = session.get(f"{GITHUB_API}{owner}/{repo}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                topics = data.get("topics", [])
                return {
                    "id": data.get("id"),
                    "description": data.get("description"),
                    "full_name": data.get("full_name"),
                    "watchers": data.get("watchers"),
                    "stargazers_count": data.get("stargazers_count"),
                    "watchers_count": data.get("watchers_count"),
                    "homepage": data.get("homepage"),
                    "topics": topics,
                    "forks_count": data.get("forks_count"),
                    "language": data.get("language"),
                    "size": data.get("size"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "pushed_at": data.get("pushed_at"),
                    "open_issues_count": data.get("open_issues_count"),
                    "network_count": data.get("network_count"),
                    "subscribers_count": data.get("subscribers_count")
                }
            else:
                print(f"Attempt {attempt+1}: Failed to fetch {repo_url} - Status code: {resp.status_code}")
        except Exception as e:
            print(f"Attempt {attempt+1}: Exception occurred for {repo_url} - {e}")
        time.sleep(2 ** attempt)
    print(f"Failed to fetch info for {repo_url} after {retries} attempts.")
    return None

def main():
    parser = argparse.ArgumentParser(description="Fetch GitHub repo info from a list of URLs.")
    parser.add_argument("input_file", help="Path to input file with GitHub repo URLs (one per line)")
    parser.add_argument("output_csv", help="Path to output CSV file")
    parser.add_argument("--token", help="GitHub API token (optional)", default=os.environ.get("GITHUB_TOKEN"))
    args = parser.parse_args()

    with open(args.input_file, "r") as infile:
        repo_urls = [line.strip() for line in infile if line.strip()]

    session = requests.Session()
    results = []
    with open(args.output_csv, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()
        # for row in results:
        #     writer.writerow(row)
        
        for url in repo_urls:
            info = get_repo_info(url, session, args.token)
            if info:
                results.append(info)
                writer.writerow(info)
            else:
                print(f"Failed to fetch info for {url}")
            time.sleep(0.5)

    # with open(args.output_csv, "w", newline='', encoding="utf-8") as csvfile:
    #     writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
    #     writer.writeheader()
    #     for row in results:
    #         writer.writerow(row)

if __name__ == "__main__":
    main()