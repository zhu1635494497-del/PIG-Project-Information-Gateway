"""Repeatable synthetic V2.3 basic-format benchmark; never uses customer data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import tempfile
from threading import Event, Thread
from time import perf_counter, sleep

from pig.application.content_contracts import ExtractContextRevisionsRequest, SearchContextContentRequest
from pig.application.contracts import (
    CreateProjectRequest, GetWorkspaceTreeRequest, ImportProjectItemsRequest,
    InspectImportSessionRequest, PromoteWorkspaceItemToContextRequest,
)
from pig.bootstrap import create_local_application


def _memory_sampler(stop: Event, peaks: list[int]) -> None:
    try:
        import psutil
    except ImportError:
        return
    process = psutil.Process()
    while not stop.is_set():
        try:
            values = (process, *process.children(recursive=True))
            peaks.append(sum(value.memory_info().rss for value in values if value.is_running()))
        except (psutil.Error, OSError):
            pass
        sleep(0.05)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_dir.resolve(strict=True)
    extraction_times = []
    search_times = []
    database_sizes = []
    peak_rss = []
    with tempfile.TemporaryDirectory(prefix="pig-v23-bench-", dir=base) as temporary:
        root = Path(temporary)
        for index in range(3):
            run_root = root / f"run-{index}"
            run_root.mkdir()
            source = run_root / "synthetic.txt"
            source.write_text((("record alpha synthetic " * 7) + "\n") * 8_000 + "needle unique\n",
                              encoding="utf-8")
            app = create_local_application(run_root / "projects")
            project = app.create_project(CreateProjectRequest(name="Benchmark", actor="benchmark"))
            imported = app.import_project_items(ImportProjectItemsRequest(
                project_id=project.project_id, database_path=project.database_path,
                input_paths=(source,), actor="benchmark",
            ))
            app.inspect_import_session(InspectImportSessionRequest(
                project_id=project.project_id, database_path=project.database_path,
                import_session_id=imported.import_session_id, actor="benchmark",
            ))
            tree = app.get_workspace_tree(GetWorkspaceTreeRequest(
                project_id=project.project_id, database_path=project.database_path,
            ))
            promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
                project_id=project.project_id, database_path=project.database_path,
                workspace_item_id=tree.items[0].item.id, actor="benchmark",
                expected_workspace_revision=tree.workspace_revision, expected_context_revision=0,
            ))
            stop = Event()
            samples: list[int] = []
            monitor = Thread(target=_memory_sampler, args=(stop, samples), daemon=True)
            monitor.start()
            started = perf_counter()
            app.extract_context_revisions(ExtractContextRevisionsRequest(
                project.project_id, project.database_path,
                (promoted.capture.context_revision_id,), "benchmark",
            ))
            extraction_times.append(perf_counter() - started)
            stop.set()
            monitor.join(timeout=1)
            peak_rss.append(max(samples) if samples else None)
            started = perf_counter()
            result = app.search_context_content(SearchContextContentRequest(
                project.project_id, project.database_path, "needle",
            ))
            search_times.append(perf_counter() - started)
            assert result.total == 1
            database_sizes.append(project.database_path.stat().st_size)
    print(json.dumps({
        "fixture": "approximately 1.2 MiB synthetic UTF-8 TXT, 8,001 lines",
        "runs": 3,
        "extract_seconds": extraction_times,
        "median_extract_seconds": median(extraction_times),
        "search_seconds": search_times,
        "median_search_seconds": median(search_times),
        "peak_process_tree_rss_bytes": peak_rss,
        "sqlite_bytes": database_sizes,
    }, indent=2))


if __name__ == "__main__":
    main()
