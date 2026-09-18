#!/usr/bin/env python3
"""RQ3 finite-support stability analysis (Section 7) over
results/raw/sampling/*.json.

Reports, per dataset and fraction: mean absolute score deviation from the
full-log result, Kendall tau-b to the full ranking, top-3/top-5 overlap,
pairwise reversal rate, and 5th/95th percentile intervals over replicates.
"""
from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations

from scipy.stats import kendalltau

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")


def percentile(values, q):
    if not values:
        return float("nan")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def main() -> int:
    directory = PROJECT_ROOT / "results" / "raw" / "sampling"

    for dataset_id in IN_SCOPE_DATASETS:
        path = directory / f"{dataset_id}.json"
        if not path.is_file():
            print(f"{dataset_id}: no sampling data yet")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        print("=" * 100)
        print(f"{dataset_id}  (prior={d['prior']}, param={d['prior_parameter']:.4f}, "
              f"{d['n_full_cases']} cases, {d['n_full_variants']} variants, "
              f"{sum(1 for m in d['models'] if m['status']=='ok')}/{len(d['models'])} models usable)")
        print("=" * 100)

        # full-log (fraction=1.0) scores per model, averaged over replicates
        # (should be replicate-invariant since fraction=1.0 always uses every case)
        full_scores = defaultdict(list)
        by_fraction = defaultdict(lambda: defaultdict(dict))  # fraction -> replicate -> model -> mid_score
        deviations = defaultdict(list)  # fraction -> [abs deviations]
        coverage = defaultdict(list)

        for r in d["results"]:
            mid = (r["score_lower"] + r["score_upper"]) / 2.0
            by_fraction[r["fraction"]][r["replicate"]][r["model_id"]] = mid
            if r["fraction"] == 1.0:
                full_scores[r["model_id"]].append(mid)
            coverage[r["fraction"]].append(r["variant_coverage"])

        full_ref = {m: sum(v) / len(v) for m, v in full_scores.items()}
        models = sorted(full_ref)
        if len(models) < 3:
            print("  fewer than 3 usable models -- skipping ranking statistics")
            continue
        full_vals = [full_ref[m] for m in models]
        full_top3 = {m for m, _ in sorted(full_ref.items(), key=lambda kv: -kv[1])[:3]}
        full_top5 = {m for m, _ in sorted(full_ref.items(), key=lambda kv: -kv[1])[: min(5, len(models))]}

        for fraction in d["fractions"]:
            taus, top3_overlaps, top5_overlaps, reversal_rates = [], [], [], []
            for replicate, scores in by_fraction[fraction].items():
                if set(scores) != set(models):
                    continue
                vals = [scores[m] for m in models]
                tau, _ = kendalltau(full_vals, vals)
                taus.append(tau)

                top3 = {m for m, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:3]}
                top3_overlaps.append(len(full_top3 & top3) / 3)
                top5 = {m for m, _ in sorted(scores.items(), key=lambda kv: -kv[1])[: min(5, len(models))]}
                top5_overlaps.append(len(full_top5 & top5) / len(full_top5))

                total = discordant = 0
                for a, b in combinations(models, 2):
                    total += 1
                    sample_sign = (scores[a] > scores[b]) - (scores[a] < scores[b])
                    full_sign = (full_ref[a] > full_ref[b]) - (full_ref[a] < full_ref[b])
                    if sample_sign != full_sign and sample_sign != 0 and full_sign != 0:
                        discordant += 1
                reversal_rates.append(discordant / total if total else float("nan"))

                for m in models:
                    deviations[fraction].append(abs(scores[m] - full_ref[m]))

            mean_tau = sum(taus) / len(taus) if taus else float("nan")
            mean_top3 = sum(top3_overlaps) / len(top3_overlaps) if top3_overlaps else float("nan")
            mean_top5 = sum(top5_overlaps) / len(top5_overlaps) if top5_overlaps else float("nan")
            mean_reversal = sum(reversal_rates) / len(reversal_rates) if reversal_rates else float("nan")
            devs = deviations[fraction]
            p5, p50, p95 = percentile(devs, 0.05), percentile(devs, 0.50), percentile(devs, 0.95)
            mean_cov = sum(coverage[fraction]) / len(coverage[fraction])
            print(
                f"  fraction={fraction:.2f}  variant_coverage={mean_cov:.3f}  "
                f"tau_b={mean_tau:+.3f}  top3_overlap={mean_top3:.2f}  top5_overlap={mean_top5:.2f}  "
                f"pairwise_reversal_rate={mean_reversal:.3f}  "
                f"abs_dev[p5,p50,p95]=[{p5:.2e},{p50:.2e},{p95:.2e}]"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
