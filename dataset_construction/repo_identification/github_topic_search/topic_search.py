from collections import Counter
from csv import DictWriter
import random
import time
import requests
import pandas as pd
import os
import ast
import argparse

# Base URL for GitHub API
BASE_URL = 'https://api.github.com'

# Headers for authentication
HEADERS = {
    'Accept': 'application/vnd.github.v3+json'
}

FIELDNAMES = [
        "id", "description", "full_name", "watchers", "stargazers_count", "watchers_count",
        "homepage", "topics", "forks_count", "language", "size", "created_at", "updated_at",
        "pushed_at", "open_issues_count", "network_count", "subscribers_count"
]

def search_repositories_by_topics(topics:list, max_stars=None, min_stars=4, sort='stars', store_file=None):
    """Search for repositories by a list of topics and handle pagination."""
    topic_groups = [topics[i:i+5] for i in range(0, len(topics), 5)]
    
    repo_data = []
    try:
        os.makedirs(os.path.dirname(store_file), exist_ok=True)
    except:
        raise Exception("Invalid store file")
    
    
    start_max_stars = max_stars
    
    for topic_group in topic_groups:
        max_stars = start_max_stars
        print(f"Searching for topic group: {topic_group}")
        topic_query = " OR ".join(topic for topic in topic_group)
        topic_query += " in:topics"
        if max_stars is not None:
            topic_query += f' stars:<={max_stars}'
        print(f"Query: {topic_query}")
        url = f'{BASE_URL}/search/repositories'
        params = {
            'q': f"{topic_query}",
            'sort': sort,
            'order': 'desc', #force descending to take advantage of structure to repeat search
            'per_page': 100,  # Max results per page
            'page': 1
        }
        print(f"Request params: {params}")
        next_max_stars = -1
        
        while max_stars is None or max_stars > min_stars:
            print(f"Current max_stars: {max_stars}, min_stars: {min_stars}")
            
            topic_query = " OR ".join(topic for topic in topic_group)
            topic_query += " in:topics"
            if max_stars is not None:
                topic_query += f' stars:<={max_stars}'
                params['q'] = f"{topic_query}"
            print(f"Query: {topic_query}")
            
            print(f"Request params: {params}")
                
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 200:
                data = response.json()
                repositories = data.get('items', [])          
                for repo in repositories:
                    repo_dict = {field: repo.get(field) for field in FIELDNAMES}
                    repo_dict["topics"] = repo_dict.get("topics") or []
                    next_max_stars = repo.get("stargazers_count", 0)
                    repo_data.append(repo_dict)                            
                if 'next' in response.links:
                    params['page'] += 1
                    url = response.links["next"]['url']
                else:
                    if max_stars is not None and  next_max_stars <= min_stars:
                        print(f"Pagination stopped: max_stars ({max_stars}) <= next_max_stars ({next_max_stars})")
                        break
                    elif max_stars is None or max_stars > next_max_stars:
                        max_stars = next_max_stars
                        params['page'] = 1
                    elif max_stars == next_max_stars:
                        max_stars -= 1
                        params['page'] = 1
            else:
                print(f"Failed to fetch repositories. Status Code: {response.content}")
                break 
            time.sleep(10 + random.randint(-5, 5))
         

    with open(store_file, "w") as f:
        writer = DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(repo_data)
    return next_max_stars
            
def read_topics(topic_file_path):
    topics = None 
    with open(topic_file_path, "r") as f:
        topics = f.readlines()
        topics = [x.strip() for x in topics if x.strip() and not x.strip().startswith("#") ]
    return topics

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Search GitHub repositories by topics.")
    parser.add_argument('--topics-file', type=str, required=True, help='Path to the file containing topics (one per line)')
    parser.add_argument('--save-file', type=str, default=None, required=False, help='Path to save the results CSV file')
    parser.add_argument('--max-stars', type=int, default=None, required=False, help='minimum number of stars to consider during search')
    parser.add_argument('--min-stars', type=int, default=4, required=False, help='minimum number of stars to consider during search')
    args = parser.parse_args()
    topics = read_topics(args.topics_file)
    # print(topics)
    search_repositories_by_topics(topics, 
                                  store_file=args.save_file,
                                  max_stars=args.max_stars,
                                  min_stars=args.min_stars
                                  )
