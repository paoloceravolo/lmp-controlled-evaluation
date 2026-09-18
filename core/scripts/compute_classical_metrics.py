#!/usr/bin/env python3
from __future__ import annotations

import argparse
import numbers
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

# PM4Py's multi_processing=True path for precision_alignments pickles results
# back from worker processes; on larger/denser nets this can exceed Python's
# default pickling recursion depth (RecursionError, not a real timeout).
sys.setrecursionlimit(20000)

import _bootstrap  # noqa: F401
from lmp_real.common import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    atomic_write_json,
    dataset_path,
    find_dataset,
    load_config,
    stable_id,
)
from lmp_real.logs import load_event_table


def timed(name, function, timeout_seconds, *args, **kwargs):
    started = time.perf_counter()
    previous_handler = signal.getsignal(signal.SIGALRM)

    def handle_timeout(_signum, _frame):
        raise TimeoutError(f"metric exceeded {timeout_seconds} seconds")

    try:
        signal.signal(signal.SIGALRM, handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        value = function(*args, **kwargs)
        elapsed = time.perf_counter() - started
        if isinstance(value, dict):
            return [
                {"metric": f"{name}.{key}", "value": float(item), "elapsed_seconds": elapsed, "status": "ok"}
                for key, item in sorted(value.items())
                if isinstance(item, numbers.Real)
            ]
        return [{"metric": name, "value": float(value), "elapsed_seconds": elapsed, "status": "ok"}]
    except Exception as exc:
        return [{
            "metric": name,
            "value": None,
            "elapsed_seconds": time.perf_counter() - started,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute classical metrics for one discovered model.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--metrics",
        default="alignment_precision,token_precision,alignment_fitness,token_fitness",
        help="Comma-separated metric names; useful for sharded or smoke runs.",
    )
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument(
        "--multi-processing",
        action="store_true",
        help="Pass multi_processing=True to PM4Py's alignment-based functions (parallelizes across variants).",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    dataset = find_dataset(config, args.dataset)
    frame = load_event_table(dataset_path(config, dataset), dataset)
    model_path = PROJECT_ROOT / "work" / "models" / dataset["id"] / args.model_id / "model.pnml"
    net, initial_marking, final_marking = pm4py.read_pnml(str(model_path))
    common = {
        "activity_key": dataset["activity"],
        "case_id_key": dataset["case_id"],
        "timestamp_key": dataset.get("timestamp", "time:timestamp"),
    }
    alignment_common = {**common, "multi_processing": args.multi_processing}
    functions = {
        "alignment_precision": (pm4py.precision_alignments, alignment_common),
        "token_precision": (pm4py.precision_token_based_replay, common),
        "alignment_fitness": (pm4py.fitness_alignments, alignment_common),
        "token_fitness": (pm4py.fitness_token_based_replay, common),
    }
    selected = [name.strip() for name in args.metrics.split(",") if name.strip()]
    unknown = sorted(set(selected).difference(functions))
    if unknown:
        raise SystemExit(f"Unknown metrics: {unknown}")
    timeout_seconds = args.timeout_seconds or int(config["execution"]["metric_timeout_seconds"])
    metrics = []
    for name in selected:
        function, kwargs = functions[name]
        metrics.extend(timed(name, function, timeout_seconds, frame, net, initial_marking, final_marking, **kwargs))
    output = {
        "schema_version": 1,
        "run_id": stable_id("classical", {"dataset_id": dataset["id"], "model_id": args.model_id}),
        "dataset_id": dataset["id"],
        "model_id": args.model_id,
        "model_path": str(model_path),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "pm4py_version": pm4py.__version__,
        "metrics": metrics,
    }
    destination = PROJECT_ROOT / "results" / "raw" / "classical" / f"{args.model_id}.json"
    atomic_write_json(destination, output)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
