import csv
import sys
import asyncio
from classify import llm_utils

csv.field_size_limit(sys.maxsize)

cache = {}

# with open("already_classified.csv", "r", encoding="utf-8") as f:
#     reader = csv.DictReader(f)
#     for row in reader:
#         cache[(row["comment"], row["context_at_introduction"])] = {
#             "is_context_llm": row["is_context_llm"] == "True",
#             "is_comment_satd": row["is_comment_satd"] == "True",
#             "explanation": row["llm_explanation"]
#         }

async def classify_row(classifier, row, idx):
    context = row.get("context_at_introduction", "")
    comment = row.get("comment", "")
    # if (comment, context) in cache:
    #     cached_result = cache[(comment, context)]
    #     row["is_context_llm"] = cached_result["is_context_llm"]
    #     row["is_comment_satd"] = cached_result["is_comment_satd"]
    #     row["llm_explanation"] = cached_result["explanation"]
    #     return idx, row
    # else: print("not found in cache")
    response = await classifier.classify(comment, context)
    row["is_context_llm"] = response["is_context_llm"]
    row["is_comment_satd"] = response["is_comment_satd"]
    row["llm_explanation"] = response["explanation"]
    return idx, row

async def classify_satds(input_path, output_path):
    classifier = llm_utils.SATDLLMClassifier() 

    with open(input_path, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)

    # Submit all tasks with row index
    tasks = [
        classify_row(classifier, row, idx)
        for idx, row in enumerate(rows)
    ]
    results = await asyncio.gather(*tasks)

    # Sort results by original order
    results.sort(key=lambda x: x[0])
    rows_with_predictions = [row for _, row in results]

    # Write output
    fieldnames = reader.fieldnames + ["is_context_llm", "is_comment_satd", "llm_explanation"]
    with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_with_predictions:
            writer.writerow(row)

    matched_rows = sum(
        1 for row in rows_with_predictions
        if row["is_context_llm"] and row["is_comment_satd"]
    )
    print(f"Number of LLM SATD: {matched_rows}")
    print(f"Total Number of Incoming Comments: {len(rows_with_predictions)}\n")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python filter_code_contexts.py <input_path> <output_path>")
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2]

    asyncio.run(classify_satds(input_path, output_path))
