#!/usr/bin/env python3
"""P4 frozen-snapshot validation (Section 10 / A7 role).

Validates uniqueness, expected-cell coverage, score ranges, interval
containment, hash consistency within ranking groups, and completion
coverage over the current results/aggregated/metrics_long.csv. On success,
writes a versioned, immutable snapshot manifest under
results/aggregated/snapshots/ that is the only input paper tables/figures
may cite.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")
EXPECTED_MODELS_PER_DATASET = 9  # 5 imf + 3 heuristics + 1 alpha


def load_rows():
    path = PROJECT_ROOT / "results" / "aggregated" / "metrics_long.csv"
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle)), path


def check_uniqueness(rows):
    seen = Counter((r["dataset_id"], r["model_id"], r["metric"], r["run_id"]) for r in rows)
    duplicates = {k: v for k, v in seen.items() if v > 1}
    return {"passed": not duplicates, "duplicate_count": len(duplicates), "examples": list(duplicates)[:5]}


def check_expected_coverage(rows):
    """Every discovered model has at least one classical (token/alignment)
    record, since classical metrics are computed for the whole grid before
    LMP is attempted. Use that as the ground truth for "which models were
    discovered" rather than the work/models/ PNML tree, which is a
    regenerable build artifact and isn't part of the archived snapshot."""
    discovered_models = defaultdict(set)
    for r in rows:
        if not r["metric"].startswith("lmp_"):
            discovered_models[r["dataset_id"]].add(r["model_id"])

    issues = []
    for dataset_id in IN_SCOPE_DATASETS:
        n = len(discovered_models[dataset_id])
        if n != EXPECTED_MODELS_PER_DATASET:
            issues.append(
                f"{dataset_id}: {n} discovered models (by classical-metric coverage), "
                f"expected {EXPECTED_MODELS_PER_DATASET}"
            )

        models_with_lmp = {r["model_id"] for r in rows if r["dataset_id"] == dataset_id and r["metric"].startswith("lmp_")}
        missing_lmp = discovered_models[dataset_id] - models_with_lmp
        if missing_lmp:
            issues.append(f"{dataset_id}: {len(missing_lmp)} models missing any LMP record: {sorted(missing_lmp)[:3]}")

    return {"passed": not issues, "issues": issues}


def check_score_ranges(rows):
    issues = []
    for r in rows:
        if r["status"] != "ok":
            continue
        metric = r["metric"]
        if metric.startswith("lmp_"):
            for field in ("score", "lower_bound", "upper_bound"):
                v = r.get(field)
                if v not in (None, ""):
                    fv = float(v)
                    if not (-1e-6 <= fv <= 1.0 + 1e-6):
                        issues.append(f"{r['run_id']} {metric} {field}={fv} out of [0,1]")
            lower, upper = r.get("lower_bound"), r.get("upper_bound")
            if lower not in (None, "") and upper not in (None, ""):
                if float(lower) - 1e-9 > float(upper) + 1e-9:
                    issues.append(f"{r['run_id']} {metric} lower({lower}) > upper({upper})")
        elif "perc" in metric or "percentage" in metric:
            v = r.get("score")
            if v not in (None, ""):
                fv = float(v)
                if not (-1e-6 <= fv <= 100.0 + 1e-6):
                    issues.append(f"{r['run_id']} {metric} score={fv} out of [0,100]")
        else:
            v = r.get("score")
            if v not in (None, ""):
                fv = float(v)
                if not (-1e-6 <= fv <= 1.0 + 1e-6):
                    issues.append(f"{r['run_id']} {metric} score={fv} out of [0,1]")
    return {"passed": not issues, "issue_count": len(issues), "examples": issues[:10]}


def check_hash_consistency(rows):
    """Within a (dataset_id, metric) ranking group, alphabet_hash must be
    identical across all models; prior_hash must be identical for the same
    (prior, parameter) across all models of the dataset."""
    issues = []
    by_dataset_metric = defaultdict(set)
    for r in rows:
        if r["metric"].startswith("lmp_") and r.get("alphabet_hash"):
            by_dataset_metric[(r["dataset_id"], "alphabet")].add(r["alphabet_hash"])
        if r["metric"].startswith("lmp_") and r.get("prior_hash") and r.get("metric_params_json"):
            by_dataset_metric[(r["dataset_id"], r["metric_params_json"])].add(r["prior_hash"])
    for key, hashes in by_dataset_metric.items():
        if len(hashes) > 1:
            issues.append(f"{key}: {len(hashes)} distinct hashes, expected 1")
    return {"passed": not issues, "issues": issues}


def check_completion_status(rows):
    status_by_dataset_metric_family = defaultdict(Counter)
    for r in rows:
        family = r["metric"].split(".")[0]
        status_by_dataset_metric_family[(r["dataset_id"], family)][r["status"]] += 1
    return {family: dict(counts) for family, counts in status_by_dataset_metric_family.items()}


def git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except Exception:
        return None


def next_snapshot_version(snapshot_dir) -> int:
    if not snapshot_dir.is_dir():
        return 1
    versions = [int(p.stem.split("_v")[-1]) for p in snapshot_dir.glob("snapshot_v*.json") if p.stem.split("_v")[-1].isdigit()]
    return (max(versions) + 1) if versions else 1


def main() -> int:
    rows, aggregate_path = load_rows()
    aggregate_hash = hashlib.sha256(aggregate_path.read_bytes()).hexdigest()

    checks = {
        "uniqueness": check_uniqueness(rows),
        "expected_coverage": check_expected_coverage(rows),
        "score_ranges": check_score_ranges(rows),
        "hash_consistency": check_hash_consistency(rows),
    }
    completion = check_completion_status(rows)

    all_passed = all(c["passed"] for c in checks.values())

    print("=" * 100)
    print("P4 frozen-snapshot validation")
    print("=" * 100)
    for name, result in checks.items():
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] {name}: {result if not result['passed'] else 'ok'}")
    print("\n  Completion status by (dataset, metric family):")
    for (dataset_id, family), counts in sorted(completion.items()):
        print(f"    {dataset_id:12} {family:22} {counts}")

    if not all_passed:
        print("\nVALIDATION FAILED -- not writing a frozen snapshot. Fix the issues above first.")
        return 1

    snapshot_dir = PROJECT_ROOT / "results" / "aggregated" / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    version = next_snapshot_version(snapshot_dir)
    snapshot = {
        "snapshot_id": f"snapshot_v{version}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "in_scope_datasets": list(IN_SCOPE_DATASETS),
        "aggregate_path": str(aggregate_path.relative_to(PROJECT_ROOT)),
        "aggregate_sha256": aggregate_hash,
        "row_count": len(rows),
        "checks": checks,
        "completion_status": {f"{k[0]}|{k[1]}": v for k, v in completion.items()},
    }
    destination = snapshot_dir / f"snapshot_v{version}.json"
    destination.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nAll checks passed. Frozen snapshot written: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
