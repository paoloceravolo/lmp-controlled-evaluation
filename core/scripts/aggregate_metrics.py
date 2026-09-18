#!/usr/bin/env python3
"""Join discovery/classical/entropia/lmp raw result shards into one long-form
metric table (Section 12 schema of experiments.MD). Idempotent: regenerates
the whole table from source-of-truth shards every run, so reruns are safe.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT, canonical_json

FIELDS = [
    "run_id", "dataset_id", "model_id", "sample_id", "sample_fraction", "sample_seed",
    "metric", "metric_params_json", "fitness_filter", "score", "lower_bound", "upper_bound",
    "exact", "numerator_mass", "log_numerator_mass", "denominator_estimate",
    "denominator_lower", "denominator_upper", "enumeration_k", "tail_bound",
    "reachability_states", "dfa_states", "runtime_s", "core_runtime_s", "peak_rss_mb",
    "alphabet_hash", "prior_hash", "status", "error_type", "tool_version",
]


def _row(**kwargs: Any) -> dict[str, Any]:
    row: dict[str, Any] = {field: None for field in FIELDS}
    row.update(kwargs)
    return row


def load_manifest_lookup() -> dict[tuple[str, str, str], str]:
    """(stage, dataset_id, model_id) -> job_id, for legacy raw result shards
    that predate embedding run_id directly in the record (classical,
    entropia). Records written by the current compute_classical_metrics.py
    carry their own run_id and don't need this lookup."""
    lookup: dict[tuple[str, str, str], str] = {}
    for stage in ("classical", "entropia"):
        manifest = PROJECT_ROOT / "work" / "manifests" / f"{stage}.jsonl"
        if not manifest.is_file():
            continue
        with manifest.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                job = json.loads(line)
                lookup[(stage, job["dataset_id"], job["model_id"])] = job["job_id"]
    return lookup


def classical_rows(manifest_by_key: dict[tuple[str, str, str], str]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((PROJECT_ROOT / "results" / "raw" / "classical").glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            record = json.load(handle)
        # Newer records embed their own run_id; older ones rely on the
        # manifest lookup below (kept for backward compatibility).
        job_id = record.get("run_id") or manifest_by_key.get(
            ("classical", record["dataset_id"], record["model_id"])
        )
        for metric in record.get("metrics", []):
            rows.append(_row(
                run_id=job_id,
                dataset_id=record["dataset_id"],
                model_id=record["model_id"],
                metric=metric["metric"],
                status=metric["status"],
                score=metric.get("value"),
                runtime_s=metric.get("elapsed_seconds"),
                core_runtime_s=metric.get("elapsed_seconds"),
                error_type=metric.get("error_type"),
                tool_version=record.get("pm4py_version"),
            ))
    return rows


def _shard_rows(subdir: str) -> list[dict[str, Any]]:
    """entropia and lmp shards already write one record per (model, metric)
    in (a superset of) the Section 12 field names."""
    rows = []
    directory = PROJECT_ROOT / "results" / "raw" / subdir
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            record = json.load(handle)
        rows.append(_row(**{field: record.get(field) for field in FIELDS}))
    return rows


def main() -> int:
    manifest_by_key = load_manifest_lookup()
    rows = classical_rows(manifest_by_key) + _shard_rows("entropia") + _shard_rows("lmp")
    rows.sort(key=lambda r: (r["dataset_id"] or "", r["model_id"] or "", r["metric"] or "", r["run_id"] or ""))
    if not rows:
        raise SystemExit("No result shards found under results/raw/{classical,entropia,lmp}")

    destination = PROJECT_ROOT / "results" / "aggregated" / "metrics_long.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            if isinstance(out.get("metric_params_json"), dict):
                out["metric_params_json"] = canonical_json(out["metric_params_json"])
            writer.writerow(out)
    temporary.replace(destination)
    print(f"{destination}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
