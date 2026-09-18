#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT


def main() -> int:
    source_dir = PROJECT_ROOT / "results" / "raw" / "profiles"
    profiles = []
    for path in sorted(source_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            profiles.append(json.load(handle))
    if not profiles:
        raise SystemExit("No profile shards found")
    destination = PROJECT_ROOT / "results" / "aggregated" / "dataset_profiles.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "dataset_id", "source_path", "source_sha256", "events", "cases", "activities", "variants",
        "case_length_min", "case_length_median", "case_length_mean", "case_length_p95", "case_length_max",
        "variant_length_min", "variant_length_median", "variant_length_mean", "variant_length_p95",
        "variant_length_max", "timestamp_parse_failures", "lifecycle_policy",
    ]
    temporary = destination.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(profiles)
    temporary.replace(destination)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
