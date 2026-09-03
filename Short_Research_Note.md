# Short Research Note: Controlled Evaluation of Language-Mass Precision

## Summary

The notebook evaluates **Language-Mass Precision (LMP)** on controlled witness tests. The goal is not to benchmark discovery algorithms on real-life logs, but to check whether LMP behaves as an exact model-language precision measure when the relevant language relations are known by construction.

LMP is a quotient-based measure. It instantiates the monotone language-quotient framework with a fixed, full-support probability mass over traces. The quotient is:

\[
\mathrm{LMP}_\mu(L,M)=
\frac{\mu(\widetilde L\cap\mathcal L(M))}
     {\mu(\mathcal L(M))}.
\]

The prior \(\mu\) is a reference measure, not an empirical frequency distribution and not a stochastic model of the process. Its role is to assign finite mass to finite and infinite model languages.

## Main findings

The controlled experiments support five conclusions.

1. **LMP separates precision from fitness.** A model can be perfectly precise with respect to the behavior it allows and still fail to fit all traces in the log.
2. **LMP follows model-language inclusion.** In the A2 tests, the exact-language model receives score 1, while a strictly larger fitting model receives a lower score.
3. **LMP strongly penalizes flower-like overgeneralization.** Exact full-language denominators matter; bounded playout overestimates precision for infinite languages because it omits tail mass.
4. **LMP is invariant under visible model-language equivalence.** Structurally different models with the same visible language receive the same LMP score.
5. **LMP is distinct from stochastic conformance.** Two models may have the same visible language but induce different simulation-derived trace probabilities. LMP is invariant under the former; stochastic similarities may depend on the latter.

## A2 decoy stress test

The most revealing model-inclusion experiment is the decoy stress test. Model \(M_1\) has exactly the log language, but its Petri-net structure contains dead visible branches. Model \(M_2\) is structurally cleaner but admits a strictly larger language.

| Metric | \(M_1\) decoy model | \(M_2\) larger clean model |
|---|---:|---:|
| LMP geometric | 1.0000 | 0.8696 |
| LMP power-law | 1.0000 | 0.8705 |
| PM4Py token-based precision | 0.3125 | 0.6667 |
| PM4Py alignment precision | 0.3125 | 0.7143 |
| PM4Py footprint precision | 0.3125 | 0.5000 |

This is evidence that LMP measures model-language precision, while replay-based precision can be influenced by local enabled behavior and structural features of the Petri net.

## Trace-level attribution of imprecision

Because LMP uses an additive trace measure, imprecision decomposes exactly:

\[
1-\mathrm{LMP}_\mu(L,M)=
\sum_{\sigma\in\mathcal L(M)\setminus\widetilde L}
\frac{\mu(\sigma)}{\mu(\mathcal L(M))}.
\]

Each unobserved-but-allowed trace has a concrete share of total imprecision. For example, if the observed traces have total mass 0.50 and three unobserved traces have masses 0.10, 0.08, and 0.02, the model-language mass is 0.70, LMP is 0.50/0.70 = 0.714, and the three unseen traces contribute 0.10/0.70, 0.08/0.70, and 0.02/0.70 to total imprecision.

This attribution is relative to the declared prior. It should not be interpreted as a ground-truth process probability.

## Flower model and exact denominators

The flower model has language \(\Sigma^*\). With normalized priors, the exact denominator is \(\mu(\Sigma^*)=1\). Bounded playout should therefore be treated as an approximation for the flower language.

For the geometric prior with \(\lambda=0.7\), the bounded \(K=3\) flower score is approximately 0.0021, while the exact score is 0.001608. For the power-law prior with \(\alpha=2\), the bounded value is approximately 0.0007 and the exact value is approximately 0.000594.

The correction strengthens the methodological point: LMP is defined on the full model language. Bounded enumeration is a computational approximation and must be reported as such.

## Prior sensitivity

The prior is part of the metric. It should be fixed before comparison and reported with the result. The notebook includes helper functions for calibrating a default prior from the median trace length and then sweeping over plausible values.

For language-inclusion cases, every fixed full-support prior preserves the required ordering. For non-inclusion-related model languages, different priors may legitimately induce different rankings because they place different mass on different trace lengths and activities.

## Stochastic-semantics A4 test

The stochastic-semantics A4 experiment compares two models with the same visible language but different internal branching structures. LMP assigns score 1 to both because the visible model language is the same and the log contains all four variants.

Language-derived stochastic similarities are also equal when they derive probabilities from the same visible language. However, simulation-derived stochastic similarities differ because random simulation over enabled transitions induces different trace distributions. This shows that model-language equivalence and stochastic equivalence are different notions.

## Computational interpretation

Once a bounded or finite-state language representation is available, LMP itself is cheap to compute. The bottleneck is often language generation or symbolic language representation, not the quotient. For a deterministic finite automaton and a geometric prior, exact denominator computation can be reduced to a linear system. For power-law priors, the length term is not memoryless, so bounded or length-aware summation with tail control is needed.

## Scope

The experiments are controlled by design. They are appropriate for testing axiomatic and semantic behavior because the relevant language relations are known. They do not establish that LMP is empirically superior as a discovery-quality indicator on real-life logs. Such validation requires a separate benchmark with public logs, discovery algorithms, and task-level or human criteria.
