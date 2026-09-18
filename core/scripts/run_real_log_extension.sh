#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p results/logs

for dataset in road_fines sepsis bpi_2012; do
  python3 scripts/compute_lmp_stability.py --dataset "$dataset" --replicates 10 \
    > "results/logs/stability_${dataset}.log" 2>&1 &
done

wait
python3 scripts/compute_activity_prior_sensitivity.py \
  > results/logs/activity_prior_sensitivity.log 2>&1
