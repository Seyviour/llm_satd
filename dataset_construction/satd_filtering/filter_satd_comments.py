import re
import csv
import sys

csv.field_size_limit(sys.maxsize)

satd_regex = re.compile(
    r"\b(to[\W_]*do|fix[\W_]*me|xxx|hac\w*)\b",
    re.IGNORECASE
)

input_path = "../comment_extraction/consolidated.csv"
output_path = "has_satd.csv"

def filter_satd_comments(input_path, output_path):
    with open(input_path, newline='', encoding='utf-8') as infile, \
        open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        
        reader = csv.DictReader(infile)
        writer = None
        total_rows = 0
        matched_rows = 0

        for row in reader:
            total_rows += 1
            comment = row.get("comment", "")
            if satd_regex.search(comment):
                matched_rows += 1
                if writer is None:
                    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
                    writer.writeheader()
                writer.writerow(row)
            # if total_rows > 5000:
            #     break  # Limit to 5000 rows for testing purposes

    print(f"Number of SATD matches: {matched_rows}")
    print(f"Total Number of Incoming Comments: {total_rows}")
    print("\n")

if __name__ == "__main__":
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    if not input_path or not output_path:
        print("Usage: python filter_satd_comments.py <input_path> <output_path>")
        sys.exit(1)
    filter_satd_comments(input_path, output_path)
