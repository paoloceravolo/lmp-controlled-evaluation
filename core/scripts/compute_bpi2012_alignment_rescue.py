#!/usr/bin/env python3
"""Probe whether BPI 2012 alignment failures are caused by log scale.

This is deliberately an additional study.  It never overwrites the primary
full-log classical shards.  Complete cases are sampled deterministically and
each PM4Py call runs in a killable child process because SIGALRM is not a
reliable backstop while alignment code is executing in C extensions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT, dataset_path, find_dataset, load_config
from lmp_real.logs import load_event_table


DEFAULT_MODELS = (
    "model-459ddf1e0ba3",
    "model-47e145cbcaa4",
    "model-7462247286ae",
    "model-9a05213e090a",
    # Known successful alignment-precision control.
    "model-64f7d91e2636",
)
DEFAULT_METRICS = (
    "alignment_precision",
    "alignment_fitness",
    "automaton_after_align_precision",
)


def _sample_cases(frame, case_key: str, fraction: float, seed: int):
    """Return a nested, deterministic complete-case sample."""
    cases = frame[case_key].drop_duplicates().tolist()
    ranked = sorted(
        cases,
        key=lambda case: hashlib.sha256(f"{seed}:{case}".encode("utf-8")).digest(),
    )
    count = max(1, round(len(ranked) * fraction))
    selected = set(ranked[:count])
    return frame[frame[case_key].isin(selected)].copy(), count


def _metric_worker(
    queue,
    metric: str,
    frame,
    model_path: str,
    activity_key: str,
    case_id_key: str,
    timestamp_key: str,
    multi_processing: bool,
    cores: int,
) -> None:
    """Compute one metric; isolated so the parent can enforce a hard timeout."""
    try:
        import pm4py
        from pm4py.algo.evaluation.precision.variants import automaton_after_align

        net, initial_marking, final_marking = pm4py.read_pnml(model_path)
        common = {
            "activity_key": activity_key,
            "case_id_key": case_id_key,
            "timestamp_key": timestamp_key,
        }
        variant_parameters = {**common, "show_progress_bar": False}
        if metric == "alignment_precision":
            value = pm4py.precision_alignments(
                frame, net, initial_marking, final_marking,
                multi_processing=multi_processing, **common,
            )
        elif metric == "alignment_fitness":
            value = pm4py.fitness_alignments(
                frame, net, initial_marking, final_marking,
                multi_processing=multi_processing, **common,
            )
            # Keep the same fitness field used by the primary aggregate.
            value = value.get("average_trace_fitness", value.get("averageFitness"))
        elif metric == "automaton_after_align_precision":
            value = automaton_after_align.apply(
                frame, net, initial_marking, final_marking,
                parameters={
                    **variant_parameters,
                    "multiprocessing": multi_processing,
                    "cores": cores,
                },
            )
        else:
            raise ValueError(f"unknown metric: {metric}")
        queue.put({"status": "ok", "value": float(value), "pm4py_version": pm4py.__version__})
    except Exception as exc:  # scientific failures remain explicit
        queue.put({
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })


def run_metric(ctx, metric: str, frame, model_path: Path, dataset: dict[str, Any], timeout: int, multi_processing: bool, cores: int):
    queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_metric_worker,
        args=(
            queue, metric, frame, str(model_path), dataset["activity"],
            dataset["case_id"], dataset.get("timestamp", "time:timestamp"),
            multi_processing, cores,
        ),
    )
    started = time.perf_counter()
    process.start()
    process.join(timeout)
    elapsed = time.perf_counter() - started
    if process.is_alive():
        process.terminate()
        process.join(10)
        if process.is_alive():
            process.kill()
            process.join()
        return {
            "status": "metric_timeout",
            "error_type": "Timeout",
            "error": f"metric exceeded hard wall-clock budget of {timeout} seconds",
            "elapsed_seconds": elapsed,
        }
    result = queue.get() if not queue.empty() else {
        "status": "failed",
        "error_type": "WorkerExit",
        "error": f"worker exited with code {process.exitcode} without a result",
    }
    result["elapsed_seconds"] = elapsed
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "experiments.json")
    parser.add_argument("--fractions", default="0.01,0.025,0.05,0.10")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="Defaults to execution.bpi2012_alignment_timeout_seconds in the config (5400s / 90 minutes in the paper's protocol).",
    )
    parser.add_argument("--multi-processing", action="store_true")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "results" / "additional" / "bpi_2012_alignment_rescue.jsonl")
    args = parser.parse_args()

    config = load_config(args.config)
    timeout_seconds = args.timeout_seconds or int(config["execution"]["bpi2012_alignment_timeout_seconds"])
    dataset = find_dataset(config, "bpi_2012")
    frame = load_event_table(dataset_path(config, dataset), dataset)
    fractions = [float(value) for value in args.fractions.split(",") if value.strip()]
    models = [value.strip() for value in args.models.split(",") if value.strip()]
    metrics = [value.strip() for value in args.metrics.split(",") if value.strip()]
    if any(not 0 < fraction <= 1 for fraction in fractions):
        raise SystemExit("fractions must be in (0, 1]")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    ctx = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    for model_id in models:
        model_path = PROJECT_ROOT / "work" / "models" / "bpi_2012" / model_id / "model.pnml"
        if not model_path.is_file():
            raise SystemExit(f"missing model: {model_path}")
        for fraction in sorted(set(fractions)):
            sample, case_count = _sample_cases(frame, dataset["case_id"], fraction, args.seed)
            variant_count = int(sample.groupby(dataset["case_id"], sort=False)[dataset["activity"]].apply(tuple).nunique())
            for metric in metrics:
                print(f"{model_id} fraction={fraction:g} cases={case_count} variants={variant_count} metric={metric}", flush=True)
                result = run_metric(
                    ctx, metric, sample, model_path, dataset, timeout_seconds,
                    args.multi_processing, args.cores,
                )
                records.append({
                    "experiment": "bpi_2012_alignment_rescue_v1",
                    "dataset_id": "bpi_2012",
                    "model_id": model_id,
                    "sample_fraction": fraction,
                    "sample_seed": args.seed,
                    "sample_cases": case_count,
                    "sample_events": int(len(sample)),
                    "sample_variants": variant_count,
                    "metric": metric,
                    "timeout_seconds": timeout_seconds,
                    "multi_processing": args.multi_processing,
                    "cores": args.cores,
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                    **result,
                })

    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
