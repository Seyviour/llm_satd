Replication package for LLM-SATD: An Empirical Study of Self-Admitted Technical Debt in Software Integrating Large Language Models

## Requirements
- Python environment plus dependencies in `requirements.txt`.
- The validation notebook references the `AltTest` submodule, however it is not needed for execution. If needed, initialize submodules with:
  `git submodule update --init --recursive`

## Data
- The extracted dataset must be available before running the analysis scripts.
- `data/llm_satd_dataset.csv` is the canonical SATD dataset used by the main analysis scripts.
- `data/ratings_rq3/` contains the taxonomy labels used by `analysis/rq3.py`.
- `data/enclosing_functions_all_with_removals.csv` is used by `analysis/complexity_repayment.py` to compute function-level complexity metrics.

## Validation
The validation scripts and artifacts for "Classification with an LLM" are under `classify_validation/`.

- `llm_validate_labels.csv`: validation labels with `gpt4o_is_llm_satd` and `annotator1_is_llm_satd`.
- `alt_test_labels.csv`: 100-row overlap sample with `gpt4o`, `annotator1`, `annotator2`, and `annotator3`.
- `alt_test_metrics.csv`: Alt-Test, annotator agreement, majority-consensus, and model-vs-consensus metrics.

Run `classify_validation/run_alt_test.ipynb` to regenerate the validation metrics CSVs fromr the the 100-row Alt-Test validation subset.

## Analysis
The `analysis/` folder contains scripts for reproducing the findings reported in the study.

- `analysis/rq1.py`: dataset prevalence stats + prevalence plot.  
  Run: `python analysis/rq1.py`
- `analysis/rq2.py`: effort plots, Mann-Whitney U tests, and median repayment times.  
  Run: `python analysis/rq2.py`
- `analysis/complexity_repayment.py`: function-level complexity metrics, repayment relationship analyses, and plots.  
  Run: `python analysis/complexity_repayment.py`
- `analysis/rq3.py`: Cohen’s kappa and taxonomy frequency table.  
  Run: `python analysis/rq3.py`
- `analysis/discussion.py`: discussion tables (rankings by category + developer roles).  
  Run: `python analysis/discussion.py`

## Outputs
- `outputs/` contains figures and CSV tables produced by the analysis scripts.
- Complexity-specific outputs include `outputs/rq2_complexity_group_comparisons.csv`, `outputs/complexity_group_comparisons.csv`, and `outputs/figures/rq2_complexity_metric_boxplots.{png,pdf}`.

## Dataset construction tools
Scripts used during dataset construction are under `dataset_construction/`:
- `dataset_construction/repo_identification/open_source_insights` for Open Source Insights
- `dataset_construction/repo_identification/github_topic_search` for GitHub topic search
- `dataset_construction/comment_extraction` for cloning and processing repositories
- `satd_filtering` for SATD identification and LLM-use heuristics
- `classify` for final classification with GPT-4o
