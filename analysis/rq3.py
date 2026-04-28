import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score


def cohen_kappa(annotator1: pd.Series, annotator2: pd.Series) -> float:
    valid = annotator1.notna() & annotator2.notna()
    if not valid.any():
        return float("nan")

    a = annotator1[valid]
    b = annotator2[valid]
    return float(cohen_kappa_score(a, b))


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ3: compute Cohen's kappa for labelled samples.")
    parser.add_argument(
        "--labels",
        type=str,
        default="data/labelled_sample.csv",
        help="Path to labelled_sample.csv containing annotator1 and annotator2 columns.",
    )
    parser.add_argument(
        "--annotator1-file",
        type=str,
        default=None,
        help="Path to annotator1.csv (processed separately).",
    )
    parser.add_argument(
        "--annotator2-file",
        type=str,
        default=None,
        help="Path to annotator2.csv (processed separately).",
    )
    parser.add_argument(
        "--annotator1-col",
        type=str,
        default="annotator1",
        help="Column name for annotator 1.",
    )
    parser.add_argument(
        "--annotator2-col",
        type=str,
        default="annotator2",
        help="Column name for annotator 2.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Output directory for the kappa summary.",
    )
    args = parser.parse_args()

    label_path = Path(args.labels)
    if args.annotator1_file and args.annotator2_file:
        annotator1_df = pd.read_csv(args.annotator1_file)
        annotator2_df = pd.read_csv(args.annotator2_file)
        df = pd.DataFrame(
            {
                "annotator1": annotator1_df[args.annotator1_col],
                "annotator2": annotator2_df[args.annotator2_col],
            }
        )
        annotator1_col = "annotator1"
        annotator2_col = "annotator2"
    else:
        df = pd.read_csv(label_path)
        annotator1_col = args.annotator1_col
        annotator2_col = args.annotator2_col

    mapped_a1 = df[annotator1_col]
    mapped_a2 = df[annotator2_col]

    agreed_path = Path("data/ratings_rq3/consensus.csv")
    agreed_df = pd.read_csv(agreed_path)
    freq_series = agreed_df["consensus"].dropna()
    category_series = agreed_df["category"].dropna()
    subcategory_series = agreed_df["subcategory"].dropna()

    category_counts = category_series.value_counts()
    total_labels = int(category_counts.sum())
    category_pct = category_counts / total_labels * 100.0
    subcategory_counts = (
        pd.DataFrame({"category": category_series, "subcategory": subcategory_series})
        .groupby(["category", "subcategory"], dropna=False)
        .size()
        .reset_index(name="subcategory_count")
    )

    category_table = (
        subcategory_counts
        .assign(
            category_count=subcategory_counts["category"].map(category_counts),
            category_pct=subcategory_counts["category"].map(category_pct).round(1),
        )
        .sort_values(
            by=["category_count", "subcategory_count", "category", "subcategory"],
            ascending=[False, False, True, True],
        )
        .reset_index(drop=True)
    )

    filtered = pd.DataFrame({"a1": mapped_a1, "a2": mapped_a2}).dropna()
    kappa = cohen_kappa(filtered["a1"], filtered["a2"])
    n_rows = int(filtered.shape[0])
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / "rq3_kappa.json"
    payload = {"cohen_kappa": kappa, "n_rows": n_rows}
    output_path.write_text(json.dumps(payload, indent=2))

    category_table_path = output_root / "rq3_category_subcategory_table.csv"
    category_table.to_csv(category_table_path, index=False)

    print("RQ3 kappa written to:", output_path)
    print("RQ3 category/subcategory table written to:", category_table_path)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
