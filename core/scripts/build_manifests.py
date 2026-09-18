#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_jsonl, grid_product, load_config, stable_id


def profile_jobs(config):
    for dataset in config["datasets"]:
        if dataset.get("enabled", True):
            payload = {"stage": "profile", "dataset_id": dataset["id"]}
            yield {**payload, "job_id": stable_id("profile", payload), "ready": True}


def discovery_jobs(config):
    for dataset in config["datasets"]:
        if not dataset.get("enabled", True):
            continue
        for algorithm in config["discovery"]:
            for parameters in grid_product(algorithm.get("grid", {})):
                payload = {
                    "stage": "discovery",
                    "dataset_id": dataset["id"],
                    "algorithm": algorithm["id"],
                    "implementation": algorithm["implementation"],
                    "parameters": parameters,
                }
                yield {
                    **payload,
                    "job_id": stable_id("model", payload),
                    "ready": bool(algorithm.get("ready", False)),
                    "blocked_reason": algorithm.get("blocked_reason"),
                }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic bootstrap job manifests.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "work" / "manifests")
    args = parser.parse_args()
    config = load_config(args.config)
    counts = {
        "profile": atomic_write_jsonl(args.output_dir / "profile.jsonl", profile_jobs(config)),
        "discovery": atomic_write_jsonl(args.output_dir / "discovery.jsonl", discovery_jobs(config)),
    }
    for stage, count in counts.items():
        print(f"{stage}: {count} jobs -> {args.output_dir / (stage + '.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
