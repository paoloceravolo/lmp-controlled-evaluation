#!/usr/bin/env python3
"""RQ1 agreement/divergence analysis (Section 8 statistical contract) from the
long-form metric aggregate. Not a frozen-snapshot analysis (P4 hasn't run) --
this is a working view over the current in-progress results.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from itertools import combinations

from scipy.stats import kendalltau, spearmanr

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")
BASELINE_METRICS = ("alignment_precision", "token_precision")
FITNESS_METRIC = "alignment_fitness.average_trace_fitness"
LMP_METRIC = "lmp_geometric"
FITNESS_THRESHOLDS = (0.95, 0.90, 0.99)
MIN_ELIGIBLE = 5


def load_rows():
    path = PROJECT_ROOT / "results" / "aggregated" / "metrics_long.csv"
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_model_table(rows):
    """(dataset_id, model_id) -> dict of the fields we need."""
    table = defaultdict(dict)
    for row in rows:
        key = (row["dataset_id"], row["model_id"])
        metric = row["metric"]
        if metric == LMP_METRIC and row["status"] == "ok":
            table[key]["lmp_exact"] = row["exact"] == "True"
            table[key]["lmp_score"] = float(row["score"]) if row["score"] else None
            table[key]["lmp_lower"] = float(row["lower_bound"]) if row["lower_bound"] else None
            table[key]["lmp_upper"] = float(row["upper_bound"]) if row["upper_bound"] else None
        if metric in BASELINE_METRICS and row["status"] == "ok":
            table[key][metric] = float(row["score"])
        if metric == FITNESS_METRIC and row["status"] == "ok":
            table[key]["fitness"] = float(row["score"])
    return table


def lmp_ranking_value(record):
    """Section 6.5: only exact scores or certified intervals with width <=1e-6
    are ranking-eligible. Returns the scalar to rank on, or None."""
    if not record.get("lmp_exact"):
        lower, upper = record.get("lmp_lower"), record.get("lmp_upper")
        if lower is None or upper is None or (upper - lower) > 1e-6:
            return None
        return (lower + upper) / 2.0
    return record.get("lmp_score")


def eligible_pairs(table, dataset, baseline_metric, fitness_threshold=None):
    """fitness_threshold=None means no fitness filter at all (the Section 5
    all-model appendix view, not the primary eligible population)."""
    pairs = []
    for (ds, model_id), record in table.items():
        if ds != dataset:
            continue
        lmp_value = lmp_ranking_value(record)
        baseline_value = record.get(baseline_metric)
        fitness = record.get("fitness")
        if lmp_value is None or baseline_value is None:
            continue
        if fitness_threshold is not None:
            if fitness is None or fitness < fitness_threshold:
                continue
        pairs.append((model_id, lmp_value, baseline_value))
    return pairs


def pareto_front(table, dataset, baseline_metric):
    """Models non-dominated in (fitness, precision) space -- no other model
    has both fitness >= and precision >= (with at least one strictly >)."""
    points = []
    for (ds, model_id), record in table.items():
        if ds != dataset:
            continue
        fitness = record.get("fitness")
        precision = record.get(baseline_metric)
        if fitness is None or precision is None:
            continue
        points.append((model_id, fitness, precision))

    front = []
    for model_id, fitness, precision in points:
        dominated = any(
            (of >= fitness and op >= precision) and (of > fitness or op > precision)
            for om, of, op in points
            if om != model_id
        )
        if not dominated:
            front.append((model_id, fitness, precision))
    return sorted(front, key=lambda p: -p[1])


def top_k_overlap(pairs, lmp_vals, baseline_vals, k):
    if len(pairs) < k:
        return None
    lmp_top = {model for model, _ in sorted(zip((p[0] for p in pairs), lmp_vals), key=lambda x: -x[1])[:k]}
    base_top = {model for model, _ in sorted(zip((p[0] for p in pairs), baseline_vals), key=lambda x: -x[1])[:k]}
    return len(lmp_top & base_top) / k


def pairwise_concordance(lmp_vals, baseline_vals):
    concordant = discordant = tied = 0
    for (a_lmp, a_base), (b_lmp, b_base) in combinations(zip(lmp_vals, baseline_vals), 2):
        lmp_sign = (a_lmp > b_lmp) - (a_lmp < b_lmp)
        base_sign = (a_base > b_base) - (a_base < b_base)
        if lmp_sign == 0 or base_sign == 0:
            tied += 1
        elif lmp_sign == base_sign:
            concordant += 1
        else:
            discordant += 1
    return concordant, discordant, tied


def largest_displacement(pairs, lmp_vals, baseline_vals):
    models = [p[0] for p in pairs]
    lmp_rank = {m: r for r, m in enumerate(sorted(models, key=lambda m: -lmp_vals[models.index(m)]), start=1)}
    base_rank = {m: r for r, m in enumerate(sorted(models, key=lambda m: -baseline_vals[models.index(m)]), start=1)}
    return max(abs(lmp_rank[m] - base_rank[m]) for m in models)


def main() -> int:
    rows = load_rows()
    table = build_model_table(rows)

    print("=" * 100)
    print("RQ1: LMP (geometric) vs. classical baselines, Section 8 statistical contract")
    print("Working view over current results -- NOT a frozen P4 snapshot.")
    print("=" * 100)

    def report(pairs, label):
        n = len(pairs)
        if n < MIN_ELIGIBLE:
            print(f"{dataset:12} vs {baseline_metric:20} n={n:2d}  insufficient_models  [{label}]")
            return
        lmp_vals = [p[1] for p in pairs]
        base_vals = [p[2] for p in pairs]
        tau, tau_p = kendalltau(lmp_vals, base_vals)
        rho, rho_p = spearmanr(lmp_vals, base_vals)
        concordant, discordant, tied = pairwise_concordance(lmp_vals, base_vals)
        top3 = top_k_overlap(pairs, lmp_vals, base_vals, 3)
        top5 = top_k_overlap(pairs, lmp_vals, base_vals, 5)
        displacement = largest_displacement(pairs, lmp_vals, base_vals)
        print(
            f"{dataset:12} vs {baseline_metric:20} n={n:2d}  "
            f"tau={tau:+.3f}(p={tau_p:.3f})  rho={rho:+.3f}(p={rho_p:.3f})  "
            f"concordant={concordant} discordant={discordant} tied={tied}  "
            f"top3={top3}  top5={top5}  max_displacement={displacement}  [{label}]"
        )

    for threshold in FITNESS_THRESHOLDS:
        label = "PRIMARY" if threshold == 0.95 else "robustness"
        print(f"\n--- fitness >= {threshold} ({label}) ---")
        for dataset in IN_SCOPE_DATASETS:
            for baseline_metric in BASELINE_METRICS:
                report(eligible_pairs(table, dataset, baseline_metric, threshold), f"fitness>={threshold}")

    print("\n" + "=" * 100)
    print("Section 5 appendix view: ALL models, no fitness filter")
    print("=" * 100)
    for dataset in IN_SCOPE_DATASETS:
        for baseline_metric in BASELINE_METRICS:
            report(eligible_pairs(table, dataset, baseline_metric, None), "all-model, unfiltered")

    print("\n" + "=" * 100)
    print("Fitness-precision Pareto fronts (non-dominated models per dataset/baseline)")
    print("=" * 100)
    for dataset in IN_SCOPE_DATASETS:
        for baseline_metric in BASELINE_METRICS:
            front = pareto_front(table, dataset, baseline_metric)
            print(f"\n{dataset} vs {baseline_metric} ({len(front)} non-dominated models):")
            for model_id, fitness, precision in front:
                print(f"    {model_id:20} fitness={fitness:.4f}  precision={precision:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
