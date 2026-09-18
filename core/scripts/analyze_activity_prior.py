#!/usr/bin/env python3
"""Analysis for the activity-prior sensitivity sweep: Kendall tau-b between
the uniform-activity-prior ranking and the Laplace-smoothed-empirical
ranking, per dataset, plus per-model score ratio."""
from __future__ import annotations

import json

from scipy.stats import kendalltau

import _bootstrap  # noqa: F401
from lmp_real.common import PROJECT_ROOT

IN_SCOPE_DATASETS = ("road_fines", "sepsis", "bpi_2012")


def main() -> int:
    for dataset_id in IN_SCOPE_DATASETS:
        path = PROJECT_ROOT / "results" / "raw" / "sensitivity" / f"activity_prior_{dataset_id}.json"
        if not path.is_file():
            print(f"{dataset_id}: no data yet")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        print("=" * 100)
        print(f"{dataset_id}  (prior_parameter={d['prior_parameter']:.4f}, laplace_delta={d['laplace_delta']})")
        print("=" * 100)

        uniform_scores, laplace_scores = {}, {}
        for r in d["results"]:
            if r["status"] != "ok":
                continue
            u, l = r["uniform"], r["laplace"]
            if u.get("score") is None or l.get("score") is None:
                continue
            uniform_scores[r["model_id"]] = u["score"]
            laplace_scores[r["model_id"]] = l["score"]
            ratio = l["score"] / u["score"] if u["score"] > 0 else float("inf")
            print(f"  {r['model_id']:20} uniform={u['score']:.4e}  laplace={l['score']:.4e}  ratio={ratio:.3f}")

        models = sorted(set(uniform_scores) & set(laplace_scores))
        if len(models) >= 3:
            tau, p = kendalltau([uniform_scores[m] for m in models], [laplace_scores[m] for m in models])
            print(f"\n  Kendall tau-b (uniform vs laplace ranking), n={len(models)}: tau={tau:+.3f} (p={p:.3f})")
        else:
            print(f"\n  fewer than 3 models with both scores (n={len(models)}) -- skipping tau-b")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
