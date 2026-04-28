import re
import csv
import sys

csv.field_size_limit(sys.maxsize)

input_path = "has_satd.csv"
output_path = "has_satd_code.csv"

def has_python_code_line(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def filter_code_contexts(input_path, output_path):
    with open(input_path, newline='', encoding='utf-8') as infile, \
        open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        
        reader = csv.DictReader(infile)
        writer = None
        total_rows = 0
        matched_rows = 0

        for row in reader:
            total_rows += 1
            context = row.get("context_at_introduction", "")
            if has_python_code_line(context):
                matched_rows += 1
                if writer is None:
                    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
                    writer.writeheader()
                writer.writerow(row)

    print(f"Number of Code matches: {matched_rows}")
    print(f"Total Number of Incoming Comments: {total_rows}")
    print("\n")


if __name__ == "__main__":
    input_path = sys.argv[1]
    output_path = sys.argv[2]

    if not input_path or not output_path:
        print("Usage: python filter_code_contexts.py <input_path> <output_path>")
        sys.exit(1)
    filter_code_contexts(input_path, output_path)