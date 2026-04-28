
from datetime import datetime
import argparse
import pandas as pd
import ast

def parse_datetime(datetime_str):
  """Parses a datetime string in the format 'YYYY-MM-DDTHH:MM:SSZ'."""
  try:
    parsed_datetime = datetime.fromisoformat(datetime_str)
    return parsed_datetime
  except ValueError:
    print(f"Invalid datetime format: {datetime_str}")
    return None

def filter_repos(full_data, language=None, updated_at=None, stars_count=None, forks_count = None, output_file=None):
    """
    Filters repositories based on language, updated_at, and stars_count.
    - language: filter by programming language (str)
    - updated_at: filter repos updated after this datetime (datetime object)
    - stars_count: filter repos with more than this number of stars (int)
    - output_file: optional file path to write the filtered output (str)
    """
    print(f"Filtering with arguments: language={language}, updated_at={updated_at}, stars_count={stars_count}, output_file={output_file}")
    # Ensure 'updated_at' column is parsed as datetime
    full_data = full_data.copy()
    full_data = full_data.drop_duplicates()
    full_data['pushed_at'] = full_data['pushed_at'].apply(lambda x: parse_datetime(x) if isinstance(x, str) else None)
    
    filters = []
    if language is not None:
        filters.append(full_data["language"].str.lower()==language)
    if updated_at is not None:
        filters.append(full_data["pushed_at"] > updated_at)
    if stars_count is not None:
        if forks_count is not None:
            filters.append((full_data["stargazers_count"] > stars_count) | (full_data["forks_count"] > forks_count))
        else:
            filters.append(full_data["stargazers_count"] > stars_count)
    if "topics" in full_data.columns:
        # Parse topics column if it's a string representation of a list
        full_data["topics"] = full_data["topics"].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) else x
        )
        filters.append(full_data["topics"].apply(lambda t: isinstance(t, list) and len(t) > 0))
    # Always filter by commit_count_local > 10
    # filters.append(full_data["commit_count_local"] > 10)
    for i, f in enumerate(filters):
        filtered_count = full_data[f].shape[0]
        print(f"Filter {i+1}: {filtered_count} rows match after applying this filter.")
    if filters:
        all_filters = filters[0]
        for f in filters[1:]:
            all_filters &= f
        filtered = full_data[all_filters]
    else:
        filtered = full_data

    filtered = filtered.drop_duplicates(subset=["full_name"])
    if output_file is not None:
        filtered.to_csv(output_file, index=False)
    return filtered

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Filter repositories based on criteria.")
    parser.add_argument("input_file", help="Path to the input CSV file containing repository data")
    parser.add_argument("--language", help="Programming language to filter by", default="Python")
    parser.add_argument("--updated-after", help="Filter repos updated after this ISO datetime (e.g., 2024-06-30T23:59:59Z)", default=None)
    parser.add_argument("--stars", type=int, help="Minimum number of stars", default=5)
    parser.add_argument("--forks-count", type=int, help="Minimum number of forks", default=4)
    parser.add_argument("--output-file", help="Path to save the filtered CSV", default=None)

    args = parser.parse_args()

    df = pd.read_csv(args.input_file)

    updated_at = parse_datetime(args.updated_after) if args.updated_after else None

    filtered = filter_repos(
        df,
        language=args.language,
        updated_at=updated_at,
        stars_count=args.stars,
        output_file=args.output_file,
        forks_count=args.forks_count
    )

    if args.output_file is None:
        print(filtered)