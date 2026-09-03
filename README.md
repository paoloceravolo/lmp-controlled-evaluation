# LMP Controlled Evaluation Notebook

This package contains the controlled evaluation notebook for **Language-Mass Precision (LMP)**.

LMP is a quotient-based model-language precision measure. It instantiates the monotone language-quotient view with a fixed, full-support probability mass over traces. The prior is a reference measure, not an empirical frequency model and not a stochastic execution semantics of the process model.

## Main notebook

- `LMP_Controlled_Evaluation.ipynb`

The notebook contains controlled witness tests for:

1. precision versus fitness;
2. model-language inclusion;
3. flower-model overgeneralization;
4. model-language equivalence;
5. adding fitting log behavior;
6. prior sensitivity;
7. separation from stochastic similarities;
8. trace-level imprecision attribution.

The experiments are intentionally controlled rather than real-log discovery benchmarks. Their purpose is to test semantic behavior in cases where the relevant language relations are known.

## Results

The `results/` directory contains exported CSV files using the LMP terminology. The most relevant files are:

- `metric_comparison_results.csv`: full metric output;
- `axiom_diagnostics.csv`: axiom-order and equality diagnostics;
- `axiom2_decoy_summary.csv`: compact table for the decoy stress test;
- `axiom3_flower_exact_lmp.csv`: exact versus bounded flower-model values;
- `lmp_parameter_sensitivity.csv`: geometric and power-law parameter sweep;
- `prior_non_inclusion_counterexample.csv`: small example where non-inclusion-related rankings depend on the prior;
- `lmp_imprecision_attribution_example.csv`: example of trace-level attribution of imprecision.

## Dependencies

The notebook uses PM4Py for PNML loading, playout, and classical precision/fitness metrics. It uses pandas and SciPy for tabulation and stochastic similarity fallbacks. RapidFuzz and POT are optional accelerators.

Install the core dependencies with:

```bash
pip install -r requirements.txt
```

## Terminology

Earlier drafts used the name LMP. This package uses the final terminology from the paper: **Language-Mass Precision (LMP)**. Any remaining reference to LMP should be treated as obsolete.
