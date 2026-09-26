from __future__ import annotations

from tools.benchmark_workbench import _compare, _qualification_failures


def _result(seconds: float = 0.1) -> dict[str, object]:
    metrics = {
        name: {"median_seconds": seconds, "peak_rss_bytes": 1}
        for name in (
            "workspace_tree_10k",
            "workspace_search_10k",
            "snapshot_import_2k",
            "zip_inspection_10k",
            "folder_export",
            "zip_export",
        )
    }
    metrics["add_contrast_single_file"] = {
        "median_seconds": seconds,
        "median_first_progress_seconds": 0.1,
        "peak_rss_bytes": 1,
    }
    metrics["add_contrast_many_files"] = {
        "median_seconds": seconds,
        "median_first_progress_seconds": 0.1,
        "peak_rss_bytes": 1,
    }
    return {"results": metrics}


def test_workbench_benchmark_absolute_gates_pass_for_bounded_results() -> None:
    assert _qualification_failures(_result()) == []


def test_workbench_benchmark_comparison_reports_a_25_percent_regression() -> None:
    baseline = _result(1.0)
    current = _result(1.0)
    current["results"]["workspace_tree_10k"]["median_seconds"] = 1.26

    failures = _compare(current, baseline)

    assert failures == [
        "workspace_tree_10k: 1.260000s exceeds 125% of 1.000000s"
    ]
