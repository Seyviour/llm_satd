# #!/bin/bash

# # python repo_sampling/topic_search.py \
# #     --topics-file repo_sampling/topics_search.txt \
# #     --save-file repo_sampling/output/search_output.csv \
# #     --min-stars 4 

# # python repo_sampling/snowball.py \
# #     --csv-path repo_sampling/output/search_output.csv\
# #     --topics-file repo_sampling/topics_search.txt \
# #     --store-file repo_sampling/output/snowball_output.csv 

# # python repo_sampling/topic_search.py \
# #     --topics-file repo_sampling/snowball_search.txt \
# #     --save-file repo_sampling/output/snowball_search_output.csv \
# #     --min-stars 4 

# # python repo_sampling/get_github_repo_data.py \
# #         repo_sampling/projects.txt \
# #         repo_sampling/output/deps.repo_data.csv \
# #         --token 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

# python concat_csvs.py \
#     repo_sampling/output/search_output.csv \
#     repo_sampling/output/snowball_search_output.csv \
#     repo_sampling/output/deps.repo_data.csv \
#     --output repo_sampling/output/combined_output.csv

# python repo_sampling/choose_repos.py \
#     --output-file repo_sampling/output/chosen_repos.csv \
#     --stars 5 \
#     --forks-count 4 \
#     --updated-after "2024-06-30T23:59:59Z" \
#     --language python \
#     repo_sampling/output/combined_output.csv \

