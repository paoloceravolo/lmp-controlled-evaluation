#!/usr/bin/env python3
"""Section 7 RQ2 prior-sensitivity sweep for one (dataset, model).

Builds the reachability graph and DFA once, then reuses them (and the
membership result for every distinct variant, which is prior-independent)
across the full relative-horizon and absolute parameter grids -- a sweep only
recomputes denominator/numerator mass arithmetic, per experiments.MD Section 7.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

import _bootstrap  # noqa: F401
from lmp_real.automaton import accepts, build_reachability_graph, determinize
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_json, canonical_json, dataset_path, find_dataset, load_config, stable_id
from lmp_real.denominator import CERT_FINITE_SUM, CERT_SPARSE_SOLVE, geometric_denominator, lmp_interval, power_law_denominator, uniform_label_mass
from lmp_real.logs import load_event_table, variant_counts
from lmp_real.priors import alpha_from_median_length, horizon_grid, lambda_from_median_length, trace_log_mass

ABSOLUTE_LAMBDA = (0.70, 0.80, 0.90, 0.95, 0.98, 0.99)
ABSOLUTE_ALPHA = (1.1, 1.2, 1.5, 2.0, 3.0, 5.0)


def grid_configs(median_length: float) -> list[dict]:
    configs = []
    for h in horizon_grid(median_length):
        configs.append({"prior": "geometric", "parameter": lambda_from_median_length(h), "grid": "relative_horizon", "horizon": h})
        configs.append({"prior": "power_law", "parameter": alpha_from_median_length(h), "grid": "relative_horizon", "horizon": h})
    for lam in ABSOLUTE_LAMBDA:
        configs.append({"prior": "geometric", "parameter": lam, "grid": "absolute", "horizon": None})
    for alpha in ABSOLUTE_ALPHA:
        configs.append({"prior": "power_law", "parameter": alpha, "grid": "absolute", "horizon": None})
    return configs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RQ2 prior-sensitivity grid for one discovered model.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_config(args.config)
    dataset = find_dataset(config, args.dataset)

    profile_path = PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset['id']}.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    alphabet_size = profile["activities"]
    median_length = profile["variant_length_median"]
    alphabet_hash = stable_id("alphabet", sorted(profile["activity_labels"]))

    model_path = PROJECT_ROOT / "work" / "models" / dataset["id"] / args.model_id / "model.pnml"
    net, initial_marking, final_marking = pm4py.read_pnml(str(model_path))

    frame = load_event_table(dataset_path(config, dataset), dataset)
    variants = list(variant_counts(frame, dataset).keys())

    execution = config.get("execution", {})
    graph = build_reachability_graph(
        net,
        initial_marking,
        final_marking,
        state_limit=execution.get("reachability_state_limit", 200_000),
        time_limit_seconds=execution.get("reachability_time_limit_seconds", 300),
    )
    if graph.status != "ok":
        results = [{"status": graph.status, "reachability_states": graph.state_count}]
        _write(dataset["id"], args.model_id, median_length, alphabet_hash, results)
        print("automaton build failed:", graph.status)
        return 0

    dfa = determinize(
        graph,
        state_limit=execution.get("determinization_state_limit", 200_000),
        time_limit_seconds=execution.get("determinization_time_limit_seconds", 300),
    )
    if dfa.status != "ok":
        results = [{"status": dfa.status, "reachability_states": graph.state_count}]
        _write(dataset["id"], args.model_id, median_length, alphabet_hash, results)
        print("determinization failed:", dfa.status)
        return 0

    label_mass = uniform_label_mass(dfa, alphabet_size)
    accepted_variants = [trace for trace in variants if accepts(dfa, trace)]

    results = []
    for cfg in grid_configs(median_length):
        prior, parameter = cfg["prior"], cfg["parameter"]
        started = time.perf_counter()
        if prior == "geometric":
            denominator = geometric_denominator(dfa, alphabet_size, lam=parameter, label_mass=label_mass)
        else:
            denominator = power_law_denominator(dfa, alphabet_size, alpha=parameter, label_mass=label_mass)

        log_masses = [trace_log_mass(trace, alphabet_size, prior, parameter) for trace in accepted_variants]
        if log_masses:
            peak = max(log_masses)
            log_numerator_mass = peak + math.log(math.fsum(math.exp(v - peak) for v in log_masses))
            numerator_mass = math.exp(log_numerator_mass)
        else:
            log_numerator_mass, numerator_mass = float("-inf"), 0.0

        lower_bound, upper_bound = lmp_interval(numerator_mass, denominator)
        exact = denominator.certification in (CERT_SPARSE_SOLVE, CERT_FINITE_SUM)
        results.append({
            "prior": prior,
            "parameter": parameter,
            "grid": cfg["grid"],
            "horizon": cfg["horizon"],
            "status": "ok",
            "exact": exact,
            "score": lower_bound if exact else None,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "numerator_mass": numerator_mass,
            "log_numerator_mass": log_numerator_mass,
            "denominator_lower": denominator.lower,
            "denominator_upper": denominator.upper,
            "certification": denominator.certification,
            "runtime_s": time.perf_counter() - started,
        })

    _write(dataset["id"], args.model_id, median_length, alphabet_hash, results, dfa_states=dfa.state_count, accepted_variant_count=len(accepted_variants))
    print(f"{len(results)} grid points computed")
    return 0


def _write(dataset_id, model_id, median_length, alphabet_hash, results, **extra):
    output = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "model_id": model_id,
        "median_length": median_length,
        "alphabet_hash": alphabet_hash,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        **extra,
    }
    destination = PROJECT_ROOT / "results" / "raw" / "sensitivity" / f"{model_id}.json"
    atomic_write_json(destination, output)


if __name__ == "__main__":
    raise SystemExit(main())
