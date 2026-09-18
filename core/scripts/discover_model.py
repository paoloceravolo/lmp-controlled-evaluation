#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

import _bootstrap  # noqa: F401
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_json, dataset_path, find_dataset, find_job, load_config
from lmp_real.logs import load_event_table


def discover(frame, dataset, algorithm, parameters):
    common = {
        "activity_key": dataset["activity"],
        "case_id_key": dataset["case_id"],
        "timestamp_key": dataset.get("timestamp", "time:timestamp"),
    }
    if algorithm == "imf":
        return pm4py.discover_petri_net_inductive(frame, **parameters, **common)
    if algorithm == "heuristics":
        return pm4py.discover_petri_net_heuristics(frame, **parameters, **common)
    if algorithm == "alpha":
        return pm4py.discover_petri_net_alpha(frame, **common)
    raise NotImplementedError(f"No in-process adapter for {algorithm!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one discovery-manifest job.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_config(args.config)
    manifest = PROJECT_ROOT / "work" / "manifests" / "discovery.jsonl"
    job = find_job(manifest, args.job_id)
    if not job.get("ready", True):
        raise SystemExit(f"Job is blocked: {job.get('blocked_reason')}")
    dataset = find_dataset(config, job["dataset_id"])
    source = dataset_path(config, dataset)
    frame = load_event_table(source, dataset)

    started = time.perf_counter()
    net, initial_marking, final_marking = discover(frame, dataset, job["algorithm"], job["parameters"])
    elapsed = time.perf_counter() - started

    model_dir = PROJECT_ROOT / "work" / "models" / dataset["id"] / job["job_id"]
    model_dir.mkdir(parents=True, exist_ok=True)
    pnml = model_dir / "model.pnml"
    pm4py.write_pnml(net, initial_marking, final_marking, str(pnml))
    metadata = {
        **job,
        "source_path": str(source),
        "model_path": str(pnml),
        "elapsed_seconds": elapsed,
        "places": len(net.places),
        "transitions": len(net.transitions),
        "visible_transitions": sum(transition.label is not None for transition in net.transitions),
        "silent_transitions": sum(transition.label is None for transition in net.transitions),
        "arcs": len(net.arcs),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pm4py_version": pm4py.__version__,
    }
    atomic_write_json(model_dir / "metadata.json", metadata)
    atomic_write_json(PROJECT_ROOT / "results" / "raw" / "discovery" / f"{job['job_id']}.json", metadata)
    print(pnml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
