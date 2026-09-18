# Real-log evaluation results

This is the output side of Section 6.1 / Table 4 in the paper: everything
needed to check the numbers reported for the three real event logs (Road
Traffic Fine Management, Sepsis Cases, BPI Challenge 2012) without rerunning
the full pipeline. `core/` is the code that produced these files from the
logs in `real_data/`.

## Layout

```
aggregated/metrics_long.csv          one row per (dataset, model, metric) measurement
aggregated/snapshots/snapshot_v1.json  integrity checks run on this CSV before it was used for the paper
aggregated/snapshots/snapshot_v2.json  the same checks, rerun after the fixes noted below
table4_real_log_summary.csv          Table 4 recomputed directly from metrics_long.csv
raw/discovery/*.json                 the 27 discovered Petri nets (9 per dataset): algorithm, hyperparameters, net size
raw/classical/*.json                 PM4Py token-based/alignment precision and fitness, per model
raw/lmp/*.json                       LMP geometric and power-law results, per model (54 files = 27 models x 2 priors)
raw/sensitivity/*.json               prior-sensitivity sweep per model (length prior and activity prior grids)
raw/sampling/*.json                  finite-support sensitivity, one file per dataset (10/25/50/75/100% nested samples, 10 replicates each)
```

`metrics_long.csv` also carries the columns behind bounded LMP (`lower_bound`,
`upper_bound`, `tail_bound`, `enumeration_k`) and the automaton size at
computation time (`reachability_states`, `dfa_states`), so a failed run can be
told apart from a run that never reached the reported precision.

## Checking Table 4

```bash
python3 core/scripts/aggregate_metrics.py --help   # regenerates metrics_long.csv from raw/
```

or, to just recompute the summary table from the CSV already here:

```python
python3 - <<'PY'
import csv, statistics as st

rows = list(csv.DictReader(open("real_data_results/aggregated/metrics_long.csv")))

def ok_scores(dataset, metric):
    return [float(r["score"]) for r in rows
            if r["dataset_id"] == dataset and r["metric"] == metric
            and r["status"] == "ok" and not r.get("sample_fraction")]

for ds in ["road_fines", "sepsis", "bpi_2012"]:
    lmp = ok_scores(ds, "lmp_geometric")
    tok = ok_scores(ds, "token_precision")
    print(ds, "exact LMP:", len(lmp), "/9",
          "token precision median:", round(st.median(tok), 3),
          "LMP median:", round(st.median(lmp), 3))
PY
```

This should reproduce `table4_real_log_summary.csv` exactly (see caveat
below).

## Why some models are missing

Not every model has an LMP or alignment-precision score, and this is
reported rather than papered over, per the "timeouts and state-limit
violations are reported explicitly, not replaced by estimates" policy in the
paper's Section 6.1.

- **LMP**: 17/27 models complete exactly (6/9 Road Fines, 6/9 Sepsis, 5/9
  BPI 2012). The 10 that don't are every Heuristics Miner and every
  alpha-algorithm model; every Inductive Miner model completes. This lines up
  with what Inductive Miner guarantees by construction (block-structured,
  bounded concurrency) and what the other two algorithms don't, so the
  pattern is structural, not incidental. `raw/lmp/*.json` records
  `status: "reachability_state_limit"` for these.
- **Alignment-based precision/fitness**: available for 19/27 models
  (8/9 Road Fines, 7/9 Sepsis, 4/9 BPI 2012); one Alpha Miner model is
  additionally rejected as an unsound net before alignment is even attempted.
- **Token-based precision/fitness**: available for all 27/27 models.

## Fixes applied after the first pass

Two issues surfaced when someone actually tried to run the validator against
this data instead of just reading it:

- `alphabet_hash` for the `lmp_geometric`/`lmp_power_law` rows originally
  hashed the dataset id rather than the actual sorted activity alphabet
  (unlike the sensitivity-sweep files, which always hashed the alphabet).
  Same field name, two different meanings. Recomputed here to the one
  convention now used everywhere; see `core/README.md`.
- `raw/classical/*.json` didn't carry their own `run_id`, so regenerating
  `metrics_long.csv` from these files depended on a job manifest that was
  never staged. Backfilled `run_id` into all 27 classical records from the
  existing `metrics_long.csv` mapping; `core/scripts/compute_classical_metrics.py`
  now writes it going forward.

`snapshot_v2.json` is `validate_snapshot.py` rerun after both fixes,
confirming the corrected data still passes every integrity check.

## A rounding discrepancy worth knowing about

`table4_real_log_summary.csv` reports Sepsis's LMP (geometric) maximum as
**0.003**, computed directly from `aggregated/metrics_long.csv`
(`model-b2bd3a9b076f`, 0.0034538...). The current paper draft prints this
cell as 0.004. The underlying raw value is unchanged either way and doesn't
affect any ranking or conclusion in the paper, but the displayed digit should
be corrected to 0.003 to match the data on the next revision.
