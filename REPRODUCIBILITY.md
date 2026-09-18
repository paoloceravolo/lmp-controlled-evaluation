# Reproducing the real-log evaluation

The paper's real-log evaluation (Section 6.1, Table 4) is backed by three
directories:

- **`real_data/`** – which public event logs were used, their DOIs, and a
  script to fetch and verify them.
- **`core/`** – the LMP engine and the scripts that turn those logs into
  discovered models, classical PM4Py baselines, and LMP scores.
- **`real_data_results/`** – the resulting measurements (raw per-model JSON
  and the aggregated CSV) plus a short script to recompute Table 4 from them.

Quickest path to checking a number in the paper: read
`real_data_results/README.md` and query `aggregated/metrics_long.csv`
directly, no need to re-run discovery or PM4Py. To reproduce from the logs
themselves, start from `real_data/README.md` and then `core/README.md`.

The controlled (synthetic) experiments in Tables 1-3 are covered separately
by the notebook repository cited in the paper.
