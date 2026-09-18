#!/usr/bin/env python3
"""RQ2's third, not-yet-tested dimension: sensitivity to the *activity*
prior (uniform vs. a Laplace-smoothed empirical activity prior), holding the
trace-length prior family and parameter fixed at the primary calibrated
geometric lambda. Section 5 lists the Laplace-smoothed prior as a secondary
sensitivity-only measure.

Reuses each model's automaton once (built here, not persisted elsewhere).
The uniform-prior LMP score for each model is already available in
results/raw/lmp/*.json and is reused rather than recomputed.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pm4py

import _bootstrap  # noqa: F401
from lmp_real.automaton import accepts, build_reachability_graph, determinize
from lmp_real.common import DEFAULT_CONFIG, PROJECT_ROOT, atomic_write_json, dataset_path, find_dataset, load_config
from lmp_real.denominator import geometric_denominator, uniform_label_mass
from lmp_real.logs import load_event_table, variant_counts
from lmp_real.priors import lambda_from_median_length

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")
LAPLACE_DELTA = 1.0


def laplace_label_mass(frame, dataset, alphabet: list[str]) -> dict[str, float]:
    activity = dataset["activity"]
    counts = frame[activity].value_counts().to_dict()
    total = sum(counts.values())
    n = len(alphabet)
    return {
        label: (counts.get(label, 0) + LAPLACE_DELTA) / (total + LAPLACE_DELTA * n)
        for label in alphabet
    }


def general_trace_log_mass(trace, prior: str, parameter: float, label_mass: dict[str, float]) -> float:
    """Like lmp_real.priors.trace_log_mass but with an arbitrary per-symbol
    activity prior instead of assuming uniform 1/|alphabet|."""
    length = len(trace)
    if prior == "geometric":
        length_log_mass = math.log1p(-parameter) + length * math.log(parameter)
    else:
        raise ValueError(f"Unsupported prior for activity-prior sensitivity: {prior}")
    symbol_log_mass = sum(math.log(label_mass[symbol]) for symbol in trace)
    return length_log_mass + symbol_log_mass


def compute_lmp(dfa, alphabet_size, variants, prior, parameter, label_mass):
    denom = geometric_denominator(dfa, alphabet_size, lam=parameter, label_mass=label_mass)
    if denom.status != "ok":
        return {"status": denom.status}
    accepted = [t for t in variants if accepts(dfa, t)]
    if not accepted:
        return {"status": "ok", "score": 0.0, "certification": denom.certification, "accepted_variants": 0}
    log_masses = [general_trace_log_mass(t, prior, parameter, label_mass) for t in accepted]
    peak = max(log_masses)
    numerator = math.exp(peak + math.log(math.fsum(math.exp(v - peak) for v in log_masses)))
    score = numerator / denom.lower if denom.exact else None
    return {
        "status": "ok",
        "score": score,
        "lower_bound": numerator / denom.upper if denom.upper > 0 else 0.0,
        "upper_bound": numerator / denom.lower if denom.lower > 0 else float("inf"),
        "exact": denom.exact,
        "certification": denom.certification,
        "accepted_variants": len(accepted),
    }


def main() -> int:
    config = load_config(DEFAULT_CONFIG)
    execution = config.get("execution", {})

    for dataset_id in IN_SCOPE_DATASETS:
        dataset = find_dataset(config, dataset_id)
        profile = json.loads((PROJECT_ROOT / "results" / "raw" / "profiles" / f"{dataset_id}.json").read_text())
        alphabet_size = profile["activities"]
        alphabet = profile["activity_labels"]
        median_length = profile["variant_length_median"]
        parameter = lambda_from_median_length(median_length)

        frame = load_event_table(dataset_path(config, dataset), dataset)
        variants = list(variant_counts(frame, dataset).keys())
        laplace_mass = laplace_label_mass(frame, dataset, alphabet)
        uniform_mass_dict = {label: 1.0 / alphabet_size for label in alphabet}

        results = []
        started = time.perf_counter()
        for model_dir in sorted((PROJECT_ROOT / "work" / "models" / dataset_id).glob("*/")):
            model_id = model_dir.name
            net, im, fm = pm4py.read_pnml(str(model_dir / "model.pnml"))
            graph = build_reachability_graph(
                net, im, fm,
                state_limit=execution.get("reachability_state_limit", 200_000),
                time_limit_seconds=execution.get("reachability_time_limit_seconds", 300),
            )
            if graph.status != "ok":
                results.append({"model_id": model_id, "status": graph.status})
                continue
            dfa = determinize(
                graph, state_limit=execution.get("determinization_state_limit", 200_000),
                time_limit_seconds=execution.get("determinization_time_limit_seconds", 300),
            )
            if dfa.status != "ok":
                results.append({"model_id": model_id, "status": dfa.status})
                continue

            # uniform_label_mass(dfa,...) restricts to labels the model actually
            # uses; build the matching restriction for laplace so both priors
            # are compared over the same edge set.
            model_laplace_mass = {label: laplace_mass[label] for label in dfa.alphabet if label in laplace_mass}
            model_uniform_mass = {label: uniform_mass_dict[label] for label in dfa.alphabet if label in uniform_mass_dict}

            uniform_result = compute_lmp(dfa, alphabet_size, variants, "geometric", parameter, model_uniform_mass)
            laplace_result = compute_lmp(dfa, alphabet_size, variants, "geometric", parameter, model_laplace_mass)
            results.append({
                "model_id": model_id,
                "status": "ok",
                "uniform": uniform_result,
                "laplace": laplace_result,
            })

        output = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "prior": "geometric",
            "prior_parameter": parameter,
            "laplace_delta": LAPLACE_DELTA,
            "alphabet_size": alphabet_size,
            "runtime_s": time.perf_counter() - started,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
        }
        destination = PROJECT_ROOT / "results" / "raw" / "sensitivity" / f"activity_prior_{dataset_id}.json"
        atomic_write_json(destination, output)
        n_ok = sum(1 for r in results if r["status"] == "ok")
        print(f"{destination}: {n_ok}/{len(results)} models usable")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
