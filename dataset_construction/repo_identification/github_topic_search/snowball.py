from collections import Counter
from csv import DictWriter
import pandas as pd
import ast
import argparse

from repo_identification.github_topic_search.topic_search import read_topics

def get_snowball_repos(csv_path, original_topics, store_file=None, num_repos=None):
    original_topics = list(original_topics)
    if not original_topics:
        return
    data_df = pd.read_csv(csv_path)
    result_topics = [ast.literal_eval(i) for i in data_df["topics"]]
    counter = Counter([item for sublist in result_topics for item in sublist])
    
    exclude = []
    for key in counter.keys():
        for otopic in original_topics:
            if otopic in key:
                exclude.append(key)
    
    all_direct_topics = set([*exclude, *original_topics])
    with open(store_file, 'w') as f:
        writer = DictWriter(f, fieldnames=["topic", "frequency", "is_direct"])
        writer.writeheader()
        for topic, frequency in counter.most_common(num_repos):
            if topic in all_direct_topics:
                continue
            to_write = {'topic': topic, 'frequency':frequency, 'is_direct':topic in all_direct_topics}
            writer.writerow(to_write)
            

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze topic frequency in repositories.")
    parser.add_argument("--csv-path", help="Path to the CSV file containing repository data.")
    parser.add_argument("--topics-file", help="Path to a file containing the list of original topics (one per line).")
    parser.add_argument("--store-file", default=None, help="File to store the results (CSV).")
    parser.add_argument("--num-repos", type=int, default=None, help="Number of top topics to include.")
    args = parser.parse_args()

    topics = read_topics(args.topics_file)
    get_snowball_repos(
        csv_path=args.csv_path,
        original_topics=topics,
        store_file=args.store_file,
        num_repos=args.num_repos
    )