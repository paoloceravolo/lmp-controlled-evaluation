from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from scipy.special import logsumexp

from lmp_real.automaton import (
    DeterministicAutomaton,
    Trace,
    accepts,
    build_reachability_graph,
    determinize,
)
from lmp_real.denominator import DenominatorResult, geometric_denominator, power_law_denominator
from lmp_real.priors import trace_log_mass

EXACT_CERTIFICATIONS = {"full_language_sparse_solve", "full_language_finite_sum"}


def dfa_from_net(
    net: Any,
    initial_marking: Any,
    final_marking: Any,
    reachability_state_limit: int = 200_000,
    reachability_time_limit_seconds: float = 120.0,
    determinization_state_limit: int = 200_000,
    determinization_time_limit_seconds: float = 120.0,
) -> DeterministicAutomaton:
    graph = build_reachability_graph(
        net,
        initial_marking,
        final_marking,
        state_limit=reachability_state_limit,
        time_limit_seconds=reachability_time_limit_seconds,
    )
    return determinize(
        graph,
        state_limit=determinization_state_limit,
        time_limit_seconds=determinization_time_limit_seconds,
    )


@dataclass(frozen=True)
class NumeratorResult:
    numerator_mass: float
    log_numerator_mass: float
    accepted_variants: int
    rejected_variants: int


def compute_numerator(
    dfa: DeterministicAutomaton,
    variants: list[Trace],
    alphabet_size: int,
    prior: str,
    parameter: float,
) -> NumeratorResult:
    """Batch-test membership of every distinct variant and sum accepted prior mass.

    Variant frequencies do not enter LMP (Section 6.2); each distinct variant
    contributes at most once. Log-space accumulation avoids underflow for long
    accepted traces.
    """
    accepted_log_masses = []
    accepted = 0
    rejected = 0
    for trace in variants:
        if accepts(dfa, trace):
            accepted += 1
            accepted_log_masses.append(trace_log_mass(trace, alphabet_size, prior, parameter))
        else:
            rejected += 1

    if not accepted_log_masses:
        return NumeratorResult(0.0, float("-inf"), accepted, rejected)

    log_mass = float(logsumexp(accepted_log_masses))
    linear_mass = math.exp(log_mass) if log_mass > -700.0 else 0.0
    return NumeratorResult(linear_mass, log_mass, accepted, rejected)


def compute_lmp(
    net: Any,
    initial_marking: Any,
    final_marking: Any,
    variants: list[Trace],
    alphabet_size: int,
    prior: str,
    parameter: float,
    reachability_state_limit: int = 200_000,
    reachability_time_limit_seconds: float = 120.0,
    determinization_state_limit: int = 200_000,
    determinization_time_limit_seconds: float = 120.0,
) -> dict[str, Any]:
    """Run the full real-log LMP pipeline for one model and one prior configuration."""
    dfa = dfa_from_net(
        net,
        initial_marking,
        final_marking,
        reachability_state_limit=reachability_state_limit,
        reachability_time_limit_seconds=reachability_time_limit_seconds,
        determinization_state_limit=determinization_state_limit,
        determinization_time_limit_seconds=determinization_time_limit_seconds,
    )

    if dfa.status != "ok":
        return _failure_record(dfa.status, dfa.state_count)

    numerator = compute_numerator(dfa, variants, alphabet_size, prior, parameter)

    if prior == "geometric":
        denom: DenominatorResult = geometric_denominator(dfa, alphabet_size, parameter)
    elif prior == "power_law":
        denom = power_law_denominator(dfa, alphabet_size, parameter)
    else:
        raise ValueError(f"Unknown prior: {prior}")

    if denom.status != "ok":
        record = _failure_record(denom.status, dfa.state_count)
        record["numerator_mass"] = numerator.numerator_mass
        record["log_numerator_mass"] = numerator.log_numerator_mass
        return record

    exact = denom.certification in EXACT_CERTIFICATIONS
    tail_bound = None if exact else max(denom.upper - denom.lower, 0.0)

    if exact and denom.lower > 0.0:
        score = numerator.numerator_mass / denom.lower
        lower_bound = upper_bound = score
    elif denom.upper > 0.0:
        lower_bound = numerator.numerator_mass / denom.upper
        upper_bound = numerator.numerator_mass / denom.lower if denom.lower > 0.0 else float("inf")
        score = None
    else:
        lower_bound = upper_bound = score = 0.0

    return {
        "status": "ok",
        "score": score,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "exact": exact,
        "certification": denom.certification,
        "numerator_mass": numerator.numerator_mass,
        "log_numerator_mass": numerator.log_numerator_mass,
        "accepted_variants": numerator.accepted_variants,
        "rejected_variants": numerator.rejected_variants,
        "denominator_estimate": denom.lower if exact else None,
        "denominator_lower": denom.lower,
        "denominator_upper": denom.upper,
        "enumeration_k": denom.truncation_k,
        "tail_bound": tail_bound,
        "dfa_states": denom.dfa_states,
    }


def _failure_record(status: str, dfa_states: int) -> dict[str, Any]:
    return {
        "status": status,
        "score": None,
        "lower_bound": None,
        "upper_bound": None,
        "exact": False,
        "certification": "none",
        "numerator_mass": None,
        "log_numerator_mass": None,
        "denominator_estimate": None,
        "denominator_lower": None,
        "denominator_upper": None,
        "enumeration_k": None,
        "tail_bound": None,
        "dfa_states": dfa_states,
    }
