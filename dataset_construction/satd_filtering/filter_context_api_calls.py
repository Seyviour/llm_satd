import re
import csv
import sys
from llm_usage import identify_llm_api_usage
csv.field_size_limit(sys.maxsize)

input_path = "has_satd_code.csv"
output_path = "has_satd_code_llm.csv"

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

        fieldnames = reader.fieldnames + ["llm_api_usage"]

        for row in reader:
            total_rows += 1
            context = row.get("context_at_introduction", "")
            llm_usage = identify_llm_api_usage(context)
            if llm_usage:
                matched_rows += 1
                if writer is None:
                    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                    writer.writeheader()
                row["llm_api_usage"] = llm_usage
                writer.writerow(row)
            # if total_rows > 5000:
            #     break
            
    print(f"Number of Context LLM API Matches: {matched_rows}")
    print(f"Total Number of Incoming Comments: {total_rows}")
    print("\n")


if __name__ == "__main__":
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    if not input_path or not output_path:
        print("Usage: python filter_context_api_calls.py <input_path> <output_path>")
        sys.exit(1)
    filter_code_contexts(input_path, output_path)