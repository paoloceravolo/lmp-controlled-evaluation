# Complex Axiom 4 Silent-Routing Experiment

This folder contains a richer Axiom 4 test case.

Axiom 4 requires that language-equivalent models receive the same precision:

\[
\mathcal L(M_1)=\mathcal L(M_2) \Rightarrow precision(L,M_1)=precision(L,M_2).
\]

## Log

File: `axiom4_complex_log.csv`

The log observes six variants, repeated twice:

- `<start, assess, approve, notify, close>`
- `<start, assess, approve, close>`
- `<start, assess, request_info, approve, notify, close>`
- `<start, assess, manual_review, approve, close>`
- `<start, assess, reject, close>`
- `<start, assess, request_info, manual_review, reject, close>`

## Model 1: direct visible choices

File: `model_direct_complex_choices.pnml`

This model has no silent routing transitions. It represents the model language as a direct union of complete visible branches.

## Model 2: silent optional routing

File: `model_silent_optional_routing.pnml`

This model uses silent transitions to encode skipped optional activities:

- skip `request_info`;
- skip `manual_review`;
- skip `notify` on approved cases.

## Shared model language

Both models accept the same twelve visible traces:

- `<start, assess, approve, close>`
- `<start, assess, reject, close>`
- `<start, assess, approve, notify, close>`
- `<start, assess, manual_review, approve, close>`
- `<start, assess, manual_review, reject, close>`
- `<start, assess, request_info, approve, close>`
- `<start, assess, request_info, reject, close>`
- `<start, assess, manual_review, approve, notify, close>`
- `<start, assess, request_info, approve, notify, close>`
- `<start, assess, request_info, manual_review, approve, close>`
- `<start, assess, request_info, manual_review, reject, close>`
- `<start, assess, request_info, manual_review, approve, notify, close>`

The log observes only a subset of this language. Therefore LMP should be equal for the two models, but the value need not be 1.
