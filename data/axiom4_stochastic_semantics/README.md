# Axiom 4 and Stochastic Semantics by Simulation

This experiment demonstrates that language equivalence and stochastic equivalence are different notions.

The two models have the same visible language:

\[
\mathcal L(M_{direct})=\mathcal L(M_{tau})
\]

but they have different internal branching structures. Therefore, when model probabilities are estimated by random simulation, they can induce different probability distributions over the same visible traces.

## Event log

File:

- `axiom4_stochastic_log.csv`

Observed variants, with balanced frequencies:

1. `<start, assess, approve, notify, close>`
2. `<start, assess, approve, close>`
3. `<start, assess, request_info, approve, notify, close>`
4. `<start, assess, manual_review, approve, close>`

## Model 1: direct equal-branch model

File:

- `model_direct_equal_branches.pnml`

This model enumerates the four visible variants as direct complete branches. Under uniform simulation over enabled transitions, the four traces are expected to have approximately equal probabilities.

## Model 2: silent-routing model with unequal simulation probabilities

File:

- `model_tau_unequal_simulation_probabilities.pnml`

This model generates the same visible language but with silent routing choices.

After `assess`, it makes a silent choice among:

- the main branch;
- the `request_info` branch;
- the `manual_review` branch.

Inside the main branch, it makes another silent choice between `notify` and skip-`notify`.

Thus, under uniform transition simulation, expected probabilities are approximately:

- `<start, assess, approve, notify, close>`: 1/6
- `<start, assess, approve, close>`: 1/6
- `<start, assess, request_info, approve, notify, close>`: 1/3
- `<start, assess, manual_review, approve, close>`: 1/3

The visible language is unchanged, but the stochastic behavior is different.

## Expected result

LMP and language-derived stochastic metrics should be equal for the two models.

Simulation-derived stochastic metrics may differ because the model-induced trace probabilities differ.
