#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_jsonl, load_config, stable_id
from lmp_real.priors import alpha_from_median_length, lambda_from_median_length


def load_models():
    for path in sorted((PROJECT_ROOT / "work" / "models").glob("*/*/metadata.json")):
        with path.open(encoding="utf-8") as handle:
            yield json.load(handle)


def load_profiles():
    profiles = {}
    for path in sorted((PROJECT_ROOT / "results" / "raw" / "profiles").glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            profile = json.load(handle)
        profiles[profile["dataset_id"]] = profile
    return profiles


def metric_jobs(models, stage):
    for model in models:
        payload = {"stage": stage, "dataset_id": model["dataset_id"], "model_id": model["job_id"]}
        yield {**payload, "job_id": stable_id(stage, payload), "ready": True}


def lmp_jobs(models, profiles):
    engine_ready = (PROJECT_ROOT / "scripts" / "compile_automaton.py").is_file()
    for model in models:
        profile = profiles.get(model["dataset_id"])
        if profile is None:
            raise ValueError(f"Missing log profile for {model['dataset_id']}")
        median_length = profile["variant_length_median"]
        priors = [
            ("geometric", lambda_from_median_length(median_length)),
            ("power_law", alpha_from_median_length(median_length)),
        ]
        for prior, parameter in priors:
            payload = {
                "stage": "lmp_default",
                "dataset_id": model["dataset_id"],
                "model_id": model["job_id"],
                "prior": prior,
                "parameter": parameter,
                "calibration_basis": "distinct_variants",
            }
            yield {
                **payload,
                "job_id": stable_id("lmp", payload),
                "ready": engine_ready,
                "blocked_reason": None if engine_ready else "Exact/certified automaton LMP engine has not passed its acceptance tests.",
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manifests after discovery/profile artifacts exist.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "work" / "manifests")
    args = parser.parse_args()
    config = load_config(args.config)
    models = list(load_models())
    profiles = load_profiles()
    if not models:
        raise SystemExit("No discovered model metadata found")

    entropia_path = PROJECT_ROOT / config["paths"]["entropia_jar"]
    entropia_ready = shutil.which("java") is not None and entropia_path.is_file()
    classical = list(metric_jobs(models, "classical"))
    entropia = [
        {
            **job,
            "ready": entropia_ready,
            "blocked_reason": None if entropia_ready else "Java and/or the configured Entropia JAR is unavailable.",
        }
        for job in metric_jobs(models, "entropia")
    ]
    lmp = list(lmp_jobs(models, profiles))
    counts = {
        "classical": atomic_write_jsonl(args.output_dir / "classical.jsonl", classical),
        "entropia": atomic_write_jsonl(args.output_dir / "entropia.jsonl", entropia),
        "lmp_default": atomic_write_jsonl(args.output_dir / "lmp_default.jsonl", lmp),
    }
    for stage, count in counts.items():
        print(f"{stage}: {count} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
