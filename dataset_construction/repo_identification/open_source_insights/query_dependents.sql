SELECT
  Name AS PackageName,
  Version AS PackageVersion,
  Dependent.Name AS DependentName,
  Dependent.Version AS DependentVersion
FROM
  `bigquery-public-data.deps_dev_v1.Dependents`
WHERE
  System = "PYPI"
  AND Package IN ("openai", "anthropic", "google-genai", "cohere", "langchain", "mistralai", "ollama")
  AND TIMESTAMP_TRUNC(SnapshotAt, DAY) BETWEEN TIMESTAMP("2025-01-06") AND TIMESTAMP("2025-01-07")
