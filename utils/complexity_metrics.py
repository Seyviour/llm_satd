from __future__ import annotations

from typing import Dict

from complexipy import code_complexity
from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_visit
from radon.raw import analyze

METRIC_COLUMNS = [
    "cyclomatic_complexity",
    "halstead_volume",
    "halstead_difficulty",
    "halstead_effort",
    "maintainability_index",
    "cognitive_complexity",
    "loc",
    "lloc",
    "sloc",
]

def _empty_metrics(status: str) -> Dict[str, float | str | None]:
    metrics: Dict[str, float | str | None] = {column: None for column in METRIC_COLUMNS}
    metrics["metric_status"] = status
    return metrics


def _compute_cognitive_complexity_complexipy(source: str) -> float:
    """Compute cognitive complexity using complexipy library."""
    result = code_complexity(source)
    return float(result.complexity)


def _radon_metrics(source: str) -> Dict[str, float]:
    cc_blocks = cc_visit(source)
    cc_value = float(cc_blocks[0].complexity) if cc_blocks else 1.0
    halstead = h_visit(source)
    raw = analyze(source)

    cognitive_complexity = _compute_cognitive_complexity_complexipy(source)

    return {
        "cyclomatic_complexity": cc_value,
        "halstead_volume": float(halstead.total.volume),
        "halstead_difficulty": float(halstead.total.difficulty),
        "halstead_effort": float(halstead.total.effort),
        "maintainability_index": float(mi_visit(source, multi=True)),
        "loc": float(raw.loc),
        "lloc": float(raw.lloc),
        "sloc": float(raw.sloc),
        "cognitive_complexity": cognitive_complexity,
    }


def compute_complexity_metrics(source: str) -> Dict[str, float | str | None]:
    if source is None or not str(source).strip():
        return _empty_metrics("missing_source")

    try:
        metrics: Dict[str, float | str | None] = dict(_radon_metrics(source))
    except SyntaxError:
        return _empty_metrics("parse_error")

    metrics["metric_status"] = "ok"
    return metrics
