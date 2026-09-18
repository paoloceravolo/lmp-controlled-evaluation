#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

import _bootstrap  # noqa: F401
from lmp_real.automaton import accepts, build_reachability_graph, determinize
from lmp_real.common import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    atomic_write_json,
    canonical_json,
    dataset_path,
    find_dataset,
    find_job,
    load_config,
    stable_id,
)
from lmp_real.denominator import (
    CERT_FINITE_SUM,
    CERT_SPARSE_SOLVE,
    geometric_denominator,
    lmp_interval,
    power_law_denominator,
    uniform_label_mass,
)
from lmp_real.logs import load_event_table, variant_counts
from lmp_real.priors import trace_log_mass


class _Timeout(Exception):
    pass


def _with_timeout(seconds, function, *args, **kwargs):
    if not seconds:
        return function(*args, **kwargs)
    previous = signal.getsignal(signal.SIGALRM)

    def handler(_signum, _frame):
        raise _Timeout(f"lmp computation exceeded {seconds} seconds")

    try:
        signal.signal(signal.SIGALRM, handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        return function(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _compute(job, dataset, config):
    model_path = PROJECT_ROOT / "work" / "models" / dataset["id"] / job["model_id"] / "model.pnml"
    net, initial_marking, final_marking = pm4py.read_pnml(str(model_path))

    profile_path = PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset['id']}.json"
    with profile_path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    alphabet_size = profile["activities"]
    if alphabet_size <= 0:
        return {"status": "invalid_alphabet", "error_type": "InvalidAlphabet", "error": "profile reports zero activities"}

    frame = load_event_table(dataset_path(config, dataset), dataset)
    counts = variant_counts(frame, dataset)

    graph = build_reachability_graph(net, initial_marking, final_marking)
    if graph.status != "ok":
        return {"status": graph.status, "reachability_states": graph.state_count}
    dfa = determinize(graph)
    if dfa.status != "ok":
        return {"status": dfa.status, "reachability_states": graph.state_count}

    prior = job["prior"]
    parameter = job["parameter"]
    label_mass = uniform_label_mass(dfa, alphabet_size)
    if prior == "geometric":
        denominator = geometric_denominator(dfa, alphabet_size, lam=parameter, label_mass=label_mass, reachability_states=graph.state_count)
    elif prior == "power_law":
        denominator = power_law_denominator(dfa, alphabet_size, alpha=parameter, label_mass=label_mass, reachability_states=graph.state_count)
    else:
        raise ValueError(f"Unknown prior: {prior}")

    accepted_variants = [trace for trace in counts if accepts(dfa, trace)]
    log_masses = [trace_log_mass(trace, alphabet_size, prior, parameter) for trace in accepted_variants]
    if log_masses:
        peak = max(log_masses)
        log_numerator_mass = peak + math.log(math.fsum(math.exp(value - peak) for value in log_masses))
        numerator_mass = math.exp(log_numerator_mass)
    else:
        log_numerator_mass = float("-inf")
        numerator_mass = 0.0

    if not (denominator.lower - 1e-6 <= denominator.upper + 1e-6):
        return {"status": "numerical_validation_failed", "error_type": "IntervalInverted"}
    if not (-1e-6 <= numerator_mass <= denominator.upper + 1e-6):
        return {"status": "numerical_validation_failed", "error_type": "NumeratorExceedsDenominator"}
    if not (-1e-9 <= denominator.lower and denominator.upper <= 1.0 + 1e-6):
        return {"status": "numerical_validation_failed", "error_type": "DenominatorOutOfRange"}

    lower_bound, upper_bound = lmp_interval(numerator_mass, denominator)
    exact = denominator.certification in (CERT_SPARSE_SOLVE, CERT_FINITE_SUM)

    return {
        "status": "ok",
        "exact": exact,
        "score": lower_bound if exact else None,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "numerator_mass": numerator_mass,
        "log_numerator_mass": log_numerator_mass,
        "denominator_estimate": denominator.exact if denominator.exact is not None else (denominator.lower + denominator.upper) / 2.0,
        "denominator_lower": denominator.lower,
        "denominator_upper": denominator.upper,
        "enumeration_k": denominator.truncation_k,
        "tail_bound": (denominator.upper - denominator.lower) if not exact else 0.0,
        "reachability_states": graph.state_count,
        "dfa_states": dfa.state_count,
        "certification": denominator.certification,
        "residual": denominator.residual,
        "alphabet_size": alphabet_size,
        "accepted_variant_count": len(accepted_variants),
        "observed_variant_count": len(counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one lmp_default-manifest job: build the automaton and compute LMP.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--timeout-seconds", type=int)
    args = parser.parse_args()
    config = load_config(args.config)
    manifest = PROJECT_ROOT / "work" / "manifests" / "lmp_default.jsonl"
    job = find_job(manifest, args.job_id)
    if not job.get("ready", True):
        raise SystemExit(f"Job is blocked: {job.get('blocked_reason')}")
    dataset = find_dataset(config, job["dataset_id"])
    timeout_seconds = args.timeout_seconds or int(config["execution"]["metric_timeout_seconds"])

    profile_path = PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset['id']}.json"
    with profile_path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    alphabet_hash = stable_id("alphabet", sorted(profile["activity_labels"]))

    started = time.perf_counter()
    try:
        payload = _with_timeout(timeout_seconds, _compute, job, dataset, config)
    except _Timeout as exc:
        payload = {"status": "metric_timeout", "error_type": "Timeout", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a scientific failure is a terminal job outcome, not a crash
        payload = {"status": "numerical_validation_failed", "error_type": type(exc).__name__, "error": str(exc)}
    runtime_seconds = time.perf_counter() - started

    output = {
        "schema_version": 1,
        "run_id": job["job_id"],
        "dataset_id": dataset["id"],
        "model_id": job["model_id"],
        "sample_id": None,
        "sample_fraction": None,
        "sample_seed": None,
        "metric": f"lmp_{job['prior']}",
        "metric_params_json": canonical_json({"prior": job["prior"], "parameter": job["parameter"], "calibration_basis": job["calibration_basis"]}),
        "fitness_filter": None,
        "runtime_s": runtime_seconds,
        "core_runtime_s": runtime_seconds,
        "peak_rss_mb": None,
        "alphabet_hash": alphabet_hash,
        "prior_hash": stable_id("prior", {"prior": job["prior"], "parameter": job["parameter"]}),
        "tool_version": pm4py.__version__,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    destination = PROJECT_ROOT / "results" / "raw" / "lmp" / f"{job['job_id']}.json"
    atomic_write_json(destination, output)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
