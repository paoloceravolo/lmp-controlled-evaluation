from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.special import zeta

from lmp_real.automaton import DeterministicAutomaton, is_acyclic, max_accepted_length, productive_states
from lmp_real.priors import length_tail_mass

CERT_SPARSE_SOLVE = "full_language_sparse_solve"
CERT_FINITE_SUM = "full_language_finite_sum"
CERT_INTERVAL = "deterministic_interval"
CERT_QUADRATURE = "quadrature_estimate_with_envelope"
CERT_NONE = "none"


def uniform_label_mass(dfa: DeterministicAutomaton, alphabet_size: int) -> dict[str, float]:
    if alphabet_size <= 0:
        raise ValueError("alphabet_size must be positive")
    return {label: 1.0 / alphabet_size for label in dfa.alphabet}


def _mass_matrix(dfa: DeterministicAutomaton, label_mass: dict[str, float]) -> sp.csr_matrix:
    """Sparse A with A[q, r] = sum of pi(a) over labels a with delta(q, a) = r
    (Section 6.3). Labels absent from ``label_mass`` (a full-log alphabet
    letter this model never produces) contribute nothing and are not an
    error: that mass simply never returns to any state, correctly modeling
    the trace leaving the model's language forever."""
    n = dfa.state_count
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for state, moves in enumerate(dfa.transitions):
        for label, target in moves.items():
            mass = label_mass.get(label)
            if mass:
                rows.append(state)
                cols.append(target)
                data.append(mass)
    matrix = sp.coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()
    matrix.sum_duplicates()
    return matrix


def _accept_vector(dfa: DeterministicAutomaton) -> np.ndarray:
    vector = np.zeros(dfa.state_count)
    for state in dfa.accepting:
        vector[state] = 1.0
    return vector


def bounded_length_masses(dfa: DeterministicAutomaton, label_mass: dict[str, float], max_k: int) -> list[float]:
    """p_n = probability that a random word with iid symbols drawn from
    ``label_mass`` and length exactly n is accepted, for n = 0..max_k."""
    matrix = _mass_matrix(dfa, label_mass)
    accept = _accept_vector(dfa)
    state_vector = np.zeros(dfa.state_count)
    state_vector[dfa.initial] = 1.0
    masses = [float(state_vector @ accept)]
    transpose = matrix.transpose().tocsr()
    for _ in range(max_k):
        state_vector = transpose @ state_vector
        masses.append(float(state_vector @ accept))
    return masses


@dataclass
class DenominatorResult:
    status: str
    certification: str
    lower: float
    upper: float
    exact: float | None = None
    residual: float | None = None
    truncation_k: int | None = None
    reachability_states: int = 0
    dfa_states: int = 0
    diagnostics: dict = field(default_factory=dict)


def geometric_denominator(
    dfa: DeterministicAutomaton,
    alphabet_size: int,
    lam: float,
    label_mass: dict[str, float] | None = None,
    width_tolerance: float = 1e-6,
    max_k: int = 4096,
    residual_tol: float = 1e-8,
    reachability_states: int = 0,
) -> DenominatorResult:
    if dfa.status != "ok":
        return DenominatorResult(status=dfa.status, certification=CERT_NONE, lower=0.0, upper=1.0)
    if not 0.0 < lam < 1.0:
        raise ValueError("geometric lambda must be in (0, 1)")
    label_mass = label_mass if label_mass is not None else uniform_label_mass(dfa, alphabet_size)

    productive = productive_states(dfa)
    acyclic = is_acyclic(dfa, productive) if productive else True

    matrix = _mass_matrix(dfa, label_mass)
    accept = _accept_vector(dfa)
    n = dfa.state_count
    identity = sp.identity(n, format="csr")
    system = (identity - lam * matrix).tocsc()
    rhs = (1.0 - lam) * accept
    solution = spla.spsolve(system, rhs)
    residual = float(np.linalg.norm(system @ solution - rhs))
    exact = float(solution[dfa.initial])

    diagnostics = {"residual": residual, "acyclic_productive_language": acyclic}

    if acyclic:
        max_len = max_accepted_length(dfa, productive) if productive else 0
        masses = bounded_length_masses(dfa, label_mass, max_len)
        weights = [(1.0 - lam) * lam**n for n in range(max_len + 1)]
        finite_sum = float(np.dot(masses, weights))
        diagnostics["finite_sum"] = finite_sum
        diagnostics["max_accepted_length"] = max_len
        diagnostics["sparse_solve"] = exact
        return DenominatorResult(
            status="ok",
            certification=CERT_FINITE_SUM,
            lower=finite_sum,
            upper=finite_sum,
            exact=finite_sum,
            residual=residual,
            truncation_k=max_len,
            reachability_states=reachability_states,
            dfa_states=n,
            diagnostics=diagnostics,
        )

    if residual <= residual_tol and -1e-9 <= exact <= 1.0 + 1e-9:
        return DenominatorResult(
            status="ok",
            certification=CERT_SPARSE_SOLVE,
            lower=exact,
            upper=exact,
            exact=exact,
            residual=residual,
            reachability_states=reachability_states,
            dfa_states=n,
            diagnostics=diagnostics,
        )

    # Fall back to a certified truncation interval when the solve does not
    # validate cleanly (Section 6.3: D_K <= D <= D_K + lambda^(K+1)).
    k = 8
    while k <= max_k:
        masses = bounded_length_masses(dfa, label_mass, k)
        d_k = math.fsum((1.0 - lam) * lam**n * masses[n] for n in range(k + 1))
        tail = lam ** (k + 1)
        if tail <= width_tolerance:
            diagnostics["sparse_solve"] = exact
            return DenominatorResult(
                status="ok",
                certification=CERT_INTERVAL,
                lower=d_k,
                upper=d_k + tail,
                exact=exact,
                residual=residual,
                truncation_k=k,
                reachability_states=reachability_states,
                dfa_states=n,
                diagnostics=diagnostics,
            )
        k *= 2
    diagnostics["sparse_solve"] = exact
    return DenominatorResult(
        status="ok",
        certification=CERT_INTERVAL,
        lower=d_k,
        upper=d_k + tail,
        exact=exact,
        residual=residual,
        truncation_k=k // 2,
        reachability_states=reachability_states,
        dfa_states=n,
        diagnostics=diagnostics,
    )


def power_law_denominator(
    dfa: DeterministicAutomaton,
    alphabet_size: int,
    alpha: float,
    label_mass: dict[str, float] | None = None,
    width_tolerance: float = 1e-6,
    max_k: int = 4096,
    reachability_states: int = 0,
) -> DenominatorResult:
    if dfa.status != "ok":
        return DenominatorResult(status=dfa.status, certification=CERT_NONE, lower=0.0, upper=1.0)
    if alpha <= 1.0:
        raise ValueError("power-law alpha must be greater than 1")
    label_mass = label_mass if label_mass is not None else uniform_label_mass(dfa, alphabet_size)

    productive = productive_states(dfa)
    acyclic = is_acyclic(dfa, productive) if productive else True
    normalizer = float(zeta(alpha, 1.0))

    def rho(length: int) -> float:
        return (length + 1) ** (-alpha) / normalizer

    if acyclic:
        max_len = max_accepted_length(dfa, productive) if productive else 0
        masses = bounded_length_masses(dfa, label_mass, max_len)
        exact = math.fsum(rho(n) * masses[n] for n in range(max_len + 1))
        return DenominatorResult(
            status="ok",
            certification=CERT_FINITE_SUM,
            lower=exact,
            upper=exact,
            exact=exact,
            truncation_k=max_len,
            reachability_states=reachability_states,
            dfa_states=dfa.state_count,
            diagnostics={"max_accepted_length": max_len},
        )

    k = 8
    while k <= max_k:
        masses = bounded_length_masses(dfa, label_mass, k)
        d_k = math.fsum(rho(n) * masses[n] for n in range(k + 1))
        tail = length_tail_mass(k, "power_law", alpha)
        if tail <= width_tolerance:
            return DenominatorResult(
                status="ok",
                certification=CERT_INTERVAL,
                lower=d_k,
                upper=d_k + tail,
                truncation_k=k,
                reachability_states=reachability_states,
                dfa_states=dfa.state_count,
                diagnostics={},
            )
        k *= 2
    return DenominatorResult(
        status="ok",
        certification=CERT_INTERVAL,
        lower=d_k,
        upper=d_k + tail,
        truncation_k=k // 2,
        reachability_states=reachability_states,
        dfa_states=dfa.state_count,
        diagnostics={},
    )


def lmp_interval(numerator: float, denominator: DenominatorResult) -> tuple[float, float]:
    """[N/D_U, N/D_L] per Section 6.4; collapses to a point value when the
    denominator is exact (lower == upper)."""
    if denominator.upper <= 0:
        return (0.0, 0.0)
    lower = numerator / denominator.upper
    upper = numerator / denominator.lower if denominator.lower > 0 else float("inf")
    return (lower, upper)
