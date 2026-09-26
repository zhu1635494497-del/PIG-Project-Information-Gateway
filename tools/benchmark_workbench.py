from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import statistics
import tempfile
import threading
import time
import uuid
import zipfile

import psutil
from sqlalchemy import insert

from pig.application import (
    AddWorkspaceInputsRequest,
    CreateProjectRequest,
    ExportWorkspaceItemsRequest,
    GetWorkspaceTreeRequest,
    OperationControl,
    OperationProgressSnapshot,
    SearchWorkspaceItemsRequest,
)
from pig.application.contracts import (
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
    MaterializeWorkspaceItemRequest,
    RefreshWorkingArtifactRequest,
)
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    WorkingContentStatus,
    WorkingRefreshReason,
    WorkspaceExportKind,
    WorkspaceItemKind,
    WorkspaceItemLifecycleStatus,
    WorkspaceMaterializationStatus,
)
from pig.infrastructure.database.engine import create_project_engine
from pig.infrastructure.database.models import WorkspaceItemModel, WorkspacePlacementModel


_ABSOLUTE_SECONDS_GATES = {
    "workspace_tree_10k": 1.5,
    "workspace_search_10k": 0.75,
    "snapshot_import_2k": 8.5,
    "zip_inspection_10k": 35.0,
    "folder_export": 25.0,
    "zip_export": 13.0,
}
_MAX_PEAK_RSS_BYTES = 300 * 1024 * 1024
_MAX_FIRST_PROGRESS_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class Measurement:
    seconds: float
    peak_rss_bytes: int


@dataclass(frozen=True, slots=True)
class ResponsiveMeasurement:
    seconds: float
    first_progress_seconds: float
    peak_rss_bytes: int


def _measure(action) -> tuple[object, Measurement]:
    process = psutil.Process()
    peak = process.memory_info().rss
    stop = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stop.wait(0.01):
            peak = max(peak, process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        value = action()
    finally:
        elapsed = time.perf_counter() - started
        stop.set()
        sampler.join()
        peak = max(peak, process.memory_info().rss)
    return value, Measurement(seconds=elapsed, peak_rss_bytes=peak)


def _summary(values: list[Measurement], units: int) -> dict[str, object]:
    median_seconds = statistics.median(value.seconds for value in values)
    return {
        "runs": [asdict(value) for value in values],
        "median_seconds": round(median_seconds, 6),
        "throughput_per_second": round(units / median_seconds, 3),
        "peak_rss_bytes": max(value.peak_rss_bytes for value in values),
        "ui_busy_duration_seconds": round(median_seconds, 6),
    }


def _measure_with_progress(action) -> tuple[object, ResponsiveMeasurement]:
    process = psutil.Process()
    peak = process.memory_info().rss
    stop = threading.Event()
    started = time.perf_counter()
    first_progress: float | None = None

    def sample() -> None:
        nonlocal peak
        while not stop.wait(0.01):
            peak = max(peak, process.memory_info().rss)

    def progress(_snapshot: OperationProgressSnapshot) -> None:
        nonlocal first_progress
        if first_progress is None:
            first_progress = time.perf_counter() - started

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        value = action(OperationControl(callback=progress))
    finally:
        elapsed = time.perf_counter() - started
        stop.set()
        sampler.join()
        peak = max(peak, process.memory_info().rss)
    if first_progress is None:
        raise AssertionError("long operation did not publish progress")
    return value, ResponsiveMeasurement(
        seconds=elapsed,
        first_progress_seconds=first_progress,
        peak_rss_bytes=peak,
    )


def _responsive_summary(
    values: list[ResponsiveMeasurement], units: int
) -> dict[str, object]:
    median_seconds = statistics.median(value.seconds for value in values)
    return {
        "runs": [asdict(value) for value in values],
        "median_seconds": round(median_seconds, 6),
        "median_first_progress_seconds": round(
            statistics.median(value.first_progress_seconds for value in values), 6
        ),
        "throughput_per_second": round(units / median_seconds, 3),
        "peak_rss_bytes": max(value.peak_rss_bytes for value in values),
        "ui_busy_duration_seconds": round(median_seconds, 6),
    }


def _seed_workspace(database_path: Path, project_id: str, count: int) -> None:
    now = datetime.now(timezone.utc)
    namespace = uuid.UUID(project_id)
    items = []
    placements = []
    for index in range(count):
        item_id = str(uuid.uuid5(namespace, f"workspace:{index}"))
        items.append(
            {
                "id": item_id,
                "project_id": project_id,
                "origin_source_node_id": None,
                "item_kind": WorkspaceItemKind.FOLDER,
                "display_name": f"benchmark-{index:05d}",
                "lifecycle_status": WorkspaceItemLifecycleStatus.ACTIVE,
                "materialization_status": WorkspaceMaterializationStatus.VIRTUAL,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )
        placements.append(
            {
                "workspace_item_id": item_id,
                "project_id": project_id,
                "parent_workspace_item_id": None,
                "ordinal": index,
                "previous_parent_id": None,
                "previous_ordinal": None,
                "updated_at": now,
            }
        )
    engine = create_project_engine(database_path)
    with engine.begin() as connection:
        for start in range(0, count, 1_000):
            connection.execute(insert(WorkspaceItemModel), items[start : start + 1_000])
            connection.execute(
                insert(WorkspacePlacementModel), placements[start : start + 1_000]
            )
    engine.dispose()


def _write_files(root: Path, count: int, size: int = 32) -> None:
    root.mkdir(parents=True)
    payload = b"x" * size
    for index in range(count):
        (root / f"file-{index:05d}.txt").write_bytes(payload)


def _query_plan(database_path: Path, sql: str, parameters: tuple[object, ...]) -> list[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("EXPLAIN QUERY PLAN " + sql, parameters).fetchall()
    return [str(row[3]) for row in rows]


def _query_plan_evidence(database_path: Path, project_id: str) -> dict[str, object]:
    plans = {
        "workspace_path_index": _query_plan(
            database_path,
            "SELECT wi.id, wi.display_name, wi.lifecycle_status, "
            "wp.parent_workspace_item_id FROM workspace_items wi "
            "JOIN workspace_placements wp ON wp.workspace_item_id = wi.id "
            "WHERE wi.project_id = ? AND wi.lifecycle_status <> 'PURGED'",
            (project_id,),
        ),
        "workspace_projection": _query_plan(
            database_path,
            "SELECT wi.id, wp.ordinal, n.id, wa.id FROM workspace_items wi "
            "JOIN workspace_placements wp ON wp.workspace_item_id = wi.id "
            "LEFT JOIN nodes n ON n.id = wi.origin_source_node_id "
            "LEFT JOIN working_artifacts wa ON wa.workspace_item_id = wi.id "
            "WHERE wi.project_id = ? AND wi.lifecycle_status <> 'PURGED'",
            (project_id,),
        ),
        "recent_project_events": _query_plan(
            database_path,
            "SELECT id FROM processing_events WHERE project_id = ? "
            "ORDER BY occurred_at DESC LIMIT 300",
            (project_id,),
        ),
    }
    flattened = " ".join(detail for plan in plans.values() for detail in plan)
    return {
        "plans": plans,
        "observed_indexes": sorted(
            set(re.findall(r"USING (?:COVERING )?INDEX ([^ ]+)", flattened))
        ),
        "decision": "existing_indexes_sufficient_no_0009",
    }


def run(
    root: Path,
    *,
    repeats: int,
    tree_items: int,
    snapshot_files: int,
    zip_entries: int,
    large_file_mib: int,
    export_files: int,
    contrast_large_mib: int,
    contrast_files: int,
    contrast_file_kib: int,
) -> dict[str, object]:
    results: dict[str, object] = {}
    sqlite_sizes: list[int] = []

    application = create_local_application(root / "tree-projects")
    tree_project = application.create_project(
        CreateProjectRequest(name="Tree baseline", actor="benchmark")
    )
    _seed_workspace(tree_project.database_path, tree_project.project_id, tree_items)
    tree_runs: list[Measurement] = []
    search_runs: list[Measurement] = []
    for _ in range(repeats):
        tree, measured = _measure(
            lambda: application.get_workspace_tree(
                GetWorkspaceTreeRequest(
                    project_id=tree_project.project_id,
                    database_path=tree_project.database_path,
                )
            )
        )
        assert len(tree.items) == tree_items
        tree_runs.append(measured)
        search, measured = _measure(
            lambda: application.search_workspace_items(
                SearchWorkspaceItemsRequest(
                    project_id=tree_project.project_id,
                    database_path=tree_project.database_path,
                    query=f"benchmark-{tree_items - 1:05d}",
                    limit=20,
                )
            )
        )
        assert search.total == 1
        search_runs.append(measured)
    results["workspace_tree_10k"] = _summary(tree_runs, tree_items)
    results["workspace_search_10k"] = _summary(search_runs, tree_items)
    query_plans = _query_plan_evidence(
        tree_project.database_path, tree_project.project_id
    )
    sqlite_sizes.append(tree_project.database_path.stat().st_size)

    snapshot_source = root / "fixtures" / "snapshot-2k"
    _write_files(snapshot_source, snapshot_files)
    snapshot_runs: list[Measurement] = []
    for index in range(repeats):
        app = create_local_application(root / f"snapshot-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"Snapshot {index}", actor="benchmark")
        )
        result, measured = _measure(
            lambda: app.import_project_items(
                ImportProjectItemsRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    input_paths=(snapshot_source,),
                    actor="benchmark",
                    idempotency_key=f"snapshot-{index}",
                )
            )
        )
        assert result.accepted_item_count == 1
        snapshot_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)
    results["snapshot_import_2k"] = _summary(snapshot_runs, snapshot_files)

    archive = root / "fixtures" / "entries-10k.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", allowZip64=True) as output:
        for index in range(zip_entries):
            output.writestr(f"folder/file-{index:05d}.txt", b"")
    zip_runs: list[Measurement] = []
    for index in range(repeats):
        app = create_local_application(root / f"zip-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"ZIP {index}", actor="benchmark")
        )
        imported = app.import_project_items(
            ImportProjectItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                input_paths=(archive,),
                actor="benchmark",
                idempotency_key=f"zip-{index}",
            )
        )
        inspected, measured = _measure(
            lambda: app.inspect_import_session(
                InspectImportSessionRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    import_session_id=imported.import_session_id,
                    actor="benchmark",
                )
            )
        )
        assert inspected.node_count >= zip_entries
        zip_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)
    results["zip_inspection_10k"] = _summary(zip_runs, zip_entries)

    large_file = root / "fixtures" / "large.bin"
    with large_file.open("wb") as stream:
        stream.truncate(large_file_mib * 1024 * 1024)
    materialize_runs: list[Measurement] = []
    refresh_runs: list[Measurement] = []
    for index in range(repeats):
        app = create_local_application(root / f"large-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"Large {index}", actor="benchmark")
        )
        app.add_workspace_inputs(
            AddWorkspaceInputsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                input_paths=(large_file,),
                actor="benchmark",
                expected_workspace_revision=0,
            )
        )
        tree = app.get_workspace_tree(
            GetWorkspaceTreeRequest(
                project_id=project.project_id,
                database_path=project.database_path,
            )
        )
        item_id = tree.items[0].item.id
        materialized, measured = _measure(
            lambda: app.materialize_workspace_item(
                MaterializeWorkspaceItemRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    workspace_item_id=item_id,
                    actor="benchmark",
                )
            )
        )
        materialize_runs.append(measured)
        with materialized.path.open("r+b") as stream:
            stream.write(b"PIG")
        refreshed, measured = _measure(
            lambda: app.refresh_working_artifact(
                RefreshWorkingArtifactRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    workspace_item_id=item_id,
                    actor="benchmark",
                    reason=WorkingRefreshReason.EXPLICIT,
                )
            )
        )
        assert refreshed.working_artifact.content_status == WorkingContentStatus.MODIFIED
        refresh_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)
    large_bytes = large_file_mib * 1024 * 1024
    results["large_file_materialize"] = _summary(materialize_runs, large_bytes)
    results["large_file_refresh_hash"] = _summary(refresh_runs, large_bytes)

    export_source = root / "fixtures" / "export-folder"
    _write_files(export_source, export_files, 128)
    (root / "exports").mkdir(parents=True, exist_ok=True)
    folder_runs: list[Measurement] = []
    zip_export_runs: list[Measurement] = []
    for index in range(repeats):
        app = create_local_application(root / f"export-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"Export {index}", actor="benchmark")
        )
        app.add_workspace_inputs(
            AddWorkspaceInputsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                input_paths=(export_source,),
                actor="benchmark",
                expected_workspace_revision=0,
            )
        )
        tree = app.get_workspace_tree(
            GetWorkspaceTreeRequest(
                project_id=project.project_id,
                database_path=project.database_path,
            )
        )
        root_item = next(
            value for value in tree.items if value.placement.parent_workspace_item_id is None
        )
        _, measured = _measure(
            lambda: app.export_workspace_items(
                ExportWorkspaceItemsRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    workspace_item_ids=(root_item.item.id,),
                    destination_path=root / "exports" / f"folder-{index}",
                    actor="benchmark",
                )
            )
        )
        folder_runs.append(measured)
        _, measured = _measure(
            lambda: app.export_workspace_items(
                ExportWorkspaceItemsRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    workspace_item_ids=tuple(
                        value.item.id
                        for value in tree.items
                        if value.item.item_kind == WorkspaceItemKind.FILE
                    ),
                    destination_path=root / "exports" / f"folder-{index}.zip",
                    actor="benchmark",
                )
            )
        )
        zip_export_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)
    results["folder_export"] = _summary(folder_runs, export_files)
    results["zip_export"] = _summary(zip_export_runs, export_files)

    contrast_large = root / "fixtures" / "contrast-large.bin"
    with contrast_large.open("wb") as stream:
        stream.truncate(contrast_large_mib * 1024 * 1024)
    contrast_many = root / "fixtures" / "contrast-many"
    _write_files(contrast_many, contrast_files, contrast_file_kib * 1024)
    contrast_large_runs: list[ResponsiveMeasurement] = []
    contrast_many_runs: list[ResponsiveMeasurement] = []
    for index in range(repeats):
        app = create_local_application(root / f"contrast-large-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"Contrast large {index}", actor="benchmark")
        )
        _, measured = _measure_with_progress(
            lambda control: app.add_workspace_inputs(
                AddWorkspaceInputsRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    input_paths=(contrast_large,),
                    actor="benchmark",
                    expected_workspace_revision=0,
                ),
                control=control,
            )
        )
        contrast_large_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)

        app = create_local_application(root / f"contrast-many-projects-{index}")
        project = app.create_project(
            CreateProjectRequest(name=f"Contrast many {index}", actor="benchmark")
        )
        _, measured = _measure_with_progress(
            lambda control: app.add_workspace_inputs(
                AddWorkspaceInputsRequest(
                    project_id=project.project_id,
                    database_path=project.database_path,
                    input_paths=(contrast_many,),
                    actor="benchmark",
                    expected_workspace_revision=0,
                ),
                control=control,
            )
        )
        contrast_many_runs.append(measured)
        sqlite_sizes.append(project.database_path.stat().st_size)
    results["add_contrast_single_file"] = _responsive_summary(
        contrast_large_runs, contrast_large_mib * 1024 * 1024
    )
    results["add_contrast_many_files"] = _responsive_summary(
        contrast_many_runs, contrast_files
    )

    return {
        "schema": "pig.workbench-performance-baseline",
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_environment": {
            "platform": __import__("platform").platform(),
            "python": __import__("sys").version,
            "logical_cpu_count": psutil.cpu_count(),
        },
        "fixture": {
            "tree_items": tree_items,
            "snapshot_files": snapshot_files,
            "zip_entries": zip_entries,
            "large_file_mib": large_file_mib,
            "export_files": export_files,
            "contrast_large_mib": contrast_large_mib,
            "contrast_files": contrast_files,
            "contrast_file_kib": contrast_file_kib,
            "repeats": repeats,
        },
        "results": results,
        "query_plan_evidence": query_plans,
        "maximum_sqlite_bytes": max(sqlite_sizes),
        "regression_policy": {
            "comparison": "same reference environment",
            "failure_threshold_percent": 25,
        },
        "interpretation": (
            "这是参考主机基线，不是跨设备 SLA。 / "
            "This is a reference-host baseline, not a cross-device SLA."
        ),
    }


def _qualification_failures(result: dict[str, object]) -> list[str]:
    failures = []
    values = result["results"]
    for name, maximum in _ABSOLUTE_SECONDS_GATES.items():
        measured = float(values[name]["median_seconds"])
        if measured > maximum:
            failures.append(f"{name}: {measured:.6f}s exceeds {maximum:.6f}s")
    for name in ("snapshot_import_2k", "zip_inspection_10k"):
        measured = int(values[name]["peak_rss_bytes"])
        if measured > _MAX_PEAK_RSS_BYTES:
            failures.append(
                f"{name}: peak RSS {measured} exceeds {_MAX_PEAK_RSS_BYTES} bytes"
            )
    for name in ("add_contrast_single_file", "add_contrast_many_files"):
        measured = float(values[name]["median_first_progress_seconds"])
        if measured > _MAX_FIRST_PROGRESS_SECONDS:
            failures.append(
                f"{name}: first progress {measured:.6f}s exceeds "
                f"{_MAX_FIRST_PROGRESS_SECONDS:.6f}s"
            )
    return failures


def _compare(current: dict[str, object], baseline: dict[str, object]) -> list[str]:
    failures = []
    current_results = current["results"]
    baseline_results = baseline["results"]
    for name, value in current_results.items():
        if name not in baseline_results:
            continue
        current_seconds = float(value["median_seconds"])
        baseline_seconds = float(baseline_results[name]["median_seconds"])
        if baseline_seconds > 0 and current_seconds > baseline_seconds * 1.25:
            failures.append(
                f"{name}: {current_seconds:.6f}s exceeds 125% of {baseline_seconds:.6f}s"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the PIG Workbench V1 loop")
    parser.add_argument("--output", type=Path, default=Path("release/performance-baseline.json"))
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    scale = (
        dict(
            tree_items=200,
            snapshot_files=20,
            zip_entries=100,
            large_file_mib=1,
            export_files=10,
            contrast_large_mib=1,
            contrast_files=20,
            contrast_file_kib=4,
        )
        if args.quick
        else dict(
            tree_items=10_000,
            snapshot_files=2_000,
            zip_entries=10_000,
            large_file_mib=64,
            export_files=500,
            contrast_large_mib=80,
            contrast_files=2_000,
            contrast_file_kib=40,
        )
    )
    with tempfile.TemporaryDirectory(prefix="pig-workbench-benchmark-") as directory:
        result = run(Path(directory), repeats=3, **scale)
    failures = _qualification_failures(result)
    comparison_failures = []
    if args.compare is not None:
        comparison_failures = _compare(
            result, json.loads(args.compare.read_text(encoding="utf-8"))
        )
    result["qualification"] = {
        "status": "PASS" if not failures and not comparison_failures else "BLOCKED",
        "absolute_gate_failures": failures,
        "comparison_failures": comparison_failures,
        "absolute_seconds_gates": _ABSOLUTE_SECONDS_GATES,
        "maximum_peak_rss_bytes": _MAX_PEAK_RSS_BYTES,
        "maximum_first_progress_seconds": _MAX_FIRST_PROGRESS_SECONDS,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures or comparison_failures:
        print("\n".join(failures + comparison_failures))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
