# LMP implementation

This is the code behind the paper: the LMP computation engine itself, plus
the scripts used to run process discovery, compute the classical PM4Py
baselines, and produce the sensitivity analyses in Section 6/7. Paired with
`real_data/` (inputs) and `real_data_results/` (outputs), it reproduces the
real-log evaluation end to end.

## Layout

```
src/lmp_real/
  automaton.py     reachability graph construction, determinization, trace membership
  denominator.py   exact geometric-prior denominator (sparse linear solve) and
                   bounded power-law denominator with certified tail bounds
  priors.py        geometric and power-law trace-mass priors, median-length calibration
  lmp_engine.py     ties the above together: builds a model's DFA, computes LMP
                   under a given prior, reports the certification status
  logs.py          XES loading, variant extraction, log profiling
  common.py        shared config loading and path resolution

scripts/
  discover_model.py                  runs one discovery job (Inductive/Heuristics/alpha)
  compute_classical_metrics.py       PM4Py token-based and alignment precision/fitness
  compile_automaton.py               runs one LMP job (builds the automaton, computes the score)
  compute_prior_sensitivity.py       length- and activity-prior sweeps
  compute_activity_prior_sensitivity.py
  compute_lmp_stability.py           finite-support (nested sampling) sensitivity
  compute_bpi2012_alignment_rescue.py  targeted retry for the slow BPI 2012 alignments
  profile_log.py                     per-dataset case/variant/length statistics
  aggregate_metrics.py               joins raw per-job results into metrics_long.csv
  aggregate_profiles.py              joins per-dataset profiles into dataset_profiles.csv
  analyze_rq1.py / analyze_rq2.py / analyze_rq3.py / analyze_activity_prior.py
                                      the statistics behind Table 4 and the Discussion section
  build_manifests.py / build_metric_manifests.py
                                      expand the config grid (datasets x algorithms x
                                      hyperparameters x priors) into a job list
  claim_job.py / finish_job.py / release_job.py
                                      a small file-based job queue, used to spread the
                                      ~350 discovery/metric/LMP jobs across worker processes
  validate_environment.py            checks PM4Py/Python versions match requirements.txt
  validate_snapshot.py               the integrity checks behind snapshot_v1.json

tests/
  test_automaton.py   automaton construction, determinization, and exact-LMP regression cases
  test_priors.py       prior normalization and calibration
  test_manifest.py     job-manifest generation
```

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export LMP_VEXG_DATA_ROOT=/path/to/real_data   # see real_data/README.md
python3 scripts/validate_environment.py

pytest -q
```

`results/` here is a symlink to `../real_data_results`, so every script that
reads or writes `PROJECT_ROOT / "results" / ...` transparently operates on the
staged, archived data — e.g. `validate_snapshot.py` runs against it directly
with no copying:

```bash
PYTHONPATH=src python3 scripts/validate_snapshot.py
```

`work/` is different: it holds the discovered PNML files and job-queue
bookkeeping, which are regenerable build artifacts rather than archived
results, so they're gitignored and not staged. It gets created fresh the
first time you run `build_manifests.py` / `discover_model.py` / a full
pipeline pass from scratch. `validate_snapshot.py`'s coverage check reflects
this: it derives "which models were discovered" from the classical-metric
records in `results/`, not from `work/models/` on disk, so it validates the
archived snapshot on its own without requiring a from-scratch rerun first.

To regenerate one dataset's profile and discover its models:

```bash
python3 scripts/profile_log.py --dataset road_fines
python3 scripts/build_manifests.py
python3 scripts/discover_model.py --manifest work/manifests/discovery.jsonl --worker-id local
```

To recompute LMP for a discovered model:

```bash
python3 scripts/compile_automaton.py --model-id <model-id> --prior geometric
```

`claim_job.py`/`finish_job.py`/`release_job.py` implement a small file-based
job queue: each takes a `--worker-id`, so the same manifest can be split
across several parallel processes without two workers picking up the same
job.

## Notes on reproducing exact scores

- LMP is deterministic given a model language, a prior, and its parameters;
  re-running `compile_automaton.py` on the same model reproduces the same
  score to floating-point precision.
- PM4Py's discovery output is *structurally* deterministic (same places,
  transitions, arcs, and parameters) but not byte-identical: it assigns
  internal node/arc identifiers from Python object ids and fresh UUIDs on
  each run. Compare discovered models by structural counts and parameters,
  not by diffing the PNML file.
- The reachability/DFA-state budget (200,000 states, 300 seconds) is set in
  `config/experiments.json` under `execution`. Raising it does not change
  which models fail for Heuristics Miner and the alpha-algorithm — see
  `real_data_results/README.md` for why.
- `execution.max_memory_gb` (64) and `execution.bpi2012_alignment_timeout_seconds`
  (5400, i.e. 90 minutes) match the resource protocol reported in the paper.
  `compute_bpi2012_alignment_rescue.py --timeout-seconds` defaults to the
  latter; pass a smaller value for a quick smoke test.
- `alphabet_hash` is the hash of the dataset's sorted activity-label list
  (via `stable_id("alphabet", sorted(profile["activity_labels"]))`), computed
  the same way in `compile_automaton.py` and `compute_prior_sensitivity.py`.
  An earlier version of `compile_automaton.py` hashed the dataset id instead,
  which produced a value with the same shape but a different meaning; the
  staged LMP records under `real_data_results/raw/lmp/` have already been
  corrected to the current convention.
- `compute_classical_metrics.py` embeds its own `run_id` in each output
  record. `aggregate_metrics.py` prefers that field and only falls back to
  the `work/manifests/classical.jsonl` lookup for older records that predate
  it, so aggregation no longer silently depends on an unstaged manifest.
