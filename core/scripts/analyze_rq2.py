#!/usr/bin/env python3
"""RQ2 prior-sensitivity analysis (Section 7) over results/raw/sensitivity/*.json.

Reports, per dataset and prior family: Kendall tau-b against the calibrated
(h=m) ranking, rank-reversal frequency, per-model score range, top-3/top-5
retention, and certified-ordering rate.
"""
from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations

from scipy.stats import kendalltau

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")


def load_records():
    """dataset_id -> (grid, prior, parameter) -> {model_id: (lower, upper, exact)}"""
    directory = PROJECT_ROOT / "results" / "raw" / "sensitivity"
    by_dataset = defaultdict(dict)
    for path in sorted(directory.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        dataset_id = d["dataset_id"]
        model_id = d["model_id"]
        for r in d.get("results", []):
            if r["status"] != "ok":
                continue
            key = (r["grid"], r["prior"], round(r["parameter"], 6))
            by_dataset[dataset_id].setdefault(key, {})[model_id] = (r["lower_bound"], r["upper_bound"], r["exact"])
    return by_dataset


def rank_from_bounds(values):
    return {model: (lo + hi) / 2.0 for model, (lo, hi, _exact) in values.items()}


def certified_ordering_rate(values):
    models = list(values)
    if len(models) < 2:
        return float("nan")
    total = certified = 0
    for a, b in combinations(models, 2):
        lo_a, hi_a, _ = values[a]
        lo_b, hi_b, _ = values[b]
        total += 1
        if lo_a > hi_b or lo_b > hi_a:
            certified += 1
    return certified / total if total else float("nan")


def main() -> int:
    by_dataset = load_records()

    for dataset_id in IN_SCOPE_DATASETS:
        grids = by_dataset.get(dataset_id, {})
        if not grids:
            print(f"{dataset_id}: no sensitivity data yet")
            continue
        print("=" * 100)
        print(dataset_id)
        print("=" * 100)

        for prior in ("geometric", "power_law"):
            relative_keys = sorted((k for k in grids if k[0] == "relative_horizon" and k[1] == prior), key=lambda k: k[2])
            absolute_keys = sorted((k for k in grids if k[0] == "absolute" and k[1] == prior), key=lambda k: k[2])
            all_keys = relative_keys + absolute_keys
            if not all_keys:
                continue

            print(f"\n--- {prior} ---")
            rankings = {}
            for key in all_keys:
                values = grids[key]
                rankings[key] = rank_from_bounds(values)
                rate = certified_ordering_rate(values)
                print(f"  grid={key[0]:16} param={key[2]:.4f}  n={len(values):2d}  certified_ordering_rate={rate:.2f}")

            if len(relative_keys) >= 3:
                reference_key = relative_keys[len(relative_keys) // 2]
                reference = rankings[reference_key]
                models = sorted(reference)
                ref_vals = [reference[m] for m in models]

                print(f"\n  Kendall tau-b vs calibrated (h=1.0m, param={reference_key[2]:.4f}):")
                taus = []
                for key in all_keys:
                    ranking = rankings[key]
                    if set(ranking) != set(models):
                        continue
                    vals = [ranking[m] for m in models]
                    tau, p = kendalltau(ref_vals, vals)
                    taus.append(tau)
                    marker = "  <- reference" if key == reference_key else ""
                    print(f"    param={key[2]:.4f} ({key[0]:16}) tau={tau:+.3f} (p={p:.3f}){marker}")

                reversals = sum(1 for t in taus if t is not None and t < 0.999)
                print(f"\n  Rank reversal frequency (tau<1.0): {reversals}/{len(taus)}")

                model_ranges = {}
                for model in models:
                    vals = [rankings[key][model] for key in all_keys if model in rankings[key]]
                    model_ranges[model] = (min(vals), max(vals))
                widest = max(model_ranges.items(), key=lambda kv: kv[1][1] - kv[1][0])
                print(f"  Widest per-model score range across grid: {widest[0]} [{widest[1][0]:.3e}, {widest[1][1]:.3e}]")

                for k in (3, 5):
                    if len(models) < k:
                        continue
                    ref_top = {m for m, _ in sorted(reference.items(), key=lambda kv: -kv[1])[:k]}
                    retentions = []
                    for key in all_keys:
                        if key == reference_key:
                            continue
                        ranking = rankings[key]
                        if set(ranking) != set(models):
                            continue
                        top = {m for m, _ in sorted(ranking.items(), key=lambda kv: -kv[1])[:k]}
                        retentions.append(len(ref_top & top) / k)
                    if retentions:
                        print(f"  top-{k} retention (mean over grid): {sum(retentions)/len(retentions):.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
