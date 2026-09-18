#!/usr/bin/env python3
"""Section 7 RQ3 finite-support stability sweep for one dataset.

Uses fixed, already-discovered models (never rediscovers), a fixed full-log
alphabet, and a fixed prior parameter (the same primary geometric lambda used
for the calibrated lmp_default jobs). For each of 10 deterministic case
permutations (replicates), takes nested prefixes at {10,25,50,75,100}% of
cases and recomputes only the LMP numerator against each model's already-
built automaton and *fixed* full-log denominator -- the denominator never
depends on observed support, so it is computed once per model and reused
across every replicate/fraction.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

import _bootstrap  # noqa: F401
from lmp_real.automaton import accepts, build_reachability_graph, determinize
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_json, dataset_path, find_dataset, load_config
from lmp_real.denominator import geometric_denominator, uniform_label_mass
from lmp_real.logs import load_event_table
from lmp_real.priors import lambda_from_median_length, trace_log_mass

FRACTIONS = (0.10, 0.25, 0.50, 0.75, 1.00)


def build_case_traces(frame, dataset) -> dict[str, tuple[str, ...]]:
    case_id = dataset["case_id"]
    activity = dataset["activity"]
    traces = {}
    for case, case_frame in frame.groupby(case_id, sort=False):
        traces[case] = tuple(case_frame[activity].tolist())
    return traces


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RQ3 finite-support stability sweep for one dataset.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_config(args.config)
    dataset = find_dataset(config, args.dataset)
    global_seed = config["random_seed"]

    profile_path = PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset['id']}.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    alphabet_size = profile["activities"]
    median_length = profile["variant_length_median"]
    prior_parameter = lambda_from_median_length(median_length)

    frame = load_event_table(dataset_path(config, dataset), dataset)
    case_traces = build_case_traces(frame, dataset)
    case_ids = sorted(case_traces)
    full_log_variants = set(case_traces.values())
    n_full_variants = len(full_log_variants)

    execution = config.get("execution", {})
    models = []
    for model_dir in sorted((PROJECT_ROOT / "work" / "models" / dataset["id"]).glob("*/")):
        model_id = model_dir.name
        net, initial_marking, final_marking = pm4py.read_pnml(str(model_dir / "model.pnml"))
        graph = build_reachability_graph(
            net, initial_marking, final_marking,
            state_limit=execution.get("reachability_state_limit", 200_000),
            time_limit_seconds=execution.get("reachability_time_limit_seconds", 300),
        )
        if graph.status != "ok":
            models.append({"model_id": model_id, "status": graph.status})
            continue
        dfa = determinize(
            graph, state_limit=execution.get("determinization_state_limit", 200_000),
            time_limit_seconds=execution.get("determinization_time_limit_seconds", 300),
        )
        if dfa.status != "ok":
            models.append({"model_id": model_id, "status": dfa.status})
            continue
        label_mass = uniform_label_mass(dfa, alphabet_size)
        denom = geometric_denominator(dfa, alphabet_size, lam=prior_parameter, label_mass=label_mass)
        if denom.status != "ok":
            models.append({"model_id": model_id, "status": denom.status})
            continue
        models.append({
            "model_id": model_id, "status": "ok", "dfa": dfa,
            "denom_lower": denom.lower, "denom_upper": denom.upper,
        })

    started = time.perf_counter()
    replicate_results = []
    for replicate in range(args.replicates):
        rng = random.Random(global_seed * 1000 + replicate)
        permuted = case_ids[:]
        rng.shuffle(permuted)
        n_cases = len(permuted)

        for fraction in FRACTIONS:
            n_sample = max(1, math.ceil(fraction * n_cases))
            sample_cases = permuted[:n_sample]
            sample_variants = {case_traces[c] for c in sample_cases}
            variant_coverage = len(sample_variants) / n_full_variants if n_full_variants else 0.0

            for model in models:
                if model["status"] != "ok":
                    continue
                dfa = model["dfa"]
                accepted = [t for t in sample_variants if accepts(dfa, t)]
                if accepted:
                    log_masses = [trace_log_mass(t, alphabet_size, "geometric", prior_parameter) for t in accepted]
                    peak = max(log_masses)
                    log_numerator = peak + math.log(math.fsum(math.exp(v - peak) for v in log_masses))
                    numerator = math.exp(log_numerator)
                else:
                    numerator = 0.0
                denom_lower, denom_upper = model["denom_lower"], model["denom_upper"]
                lower = numerator / denom_upper if denom_upper > 0 else 0.0
                upper = numerator / denom_lower if denom_lower > 0 else float("inf")
                replicate_results.append({
                    "model_id": model["model_id"],
                    "replicate": replicate,
                    "fraction": fraction,
                    "n_sample_cases": n_sample,
                    "n_sample_variants": len(sample_variants),
                    "variant_coverage": variant_coverage,
                    "observed_prior_mass": numerator,
                    "score_lower": lower,
                    "score_upper": upper,
                })

    output = {
        "schema_version": 1,
        "dataset_id": dataset["id"],
        "prior": "geometric",
        "prior_parameter": prior_parameter,
        "median_length": median_length,
        "n_full_cases": len(case_ids),
        "n_full_variants": n_full_variants,
        "replicates": args.replicates,
        "fractions": list(FRACTIONS),
        "models": [{"model_id": m["model_id"], "status": m["status"]} for m in models],
        "runtime_s": time.perf_counter() - started,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "results": replicate_results,
    }
    destination = PROJECT_ROOT / "results" / "raw" / "sampling" / f"{dataset['id']}.json"
    atomic_write_json(destination, output)
    print(f"{destination}: {len(replicate_results)} rows, {sum(1 for m in models if m['status']=='ok')}/{len(models)} models usable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
