import math

import pytest
from pm4py.objects.petri_net.obj import Marking, PetriNet
from pm4py.objects.petri_net.utils import petri_utils

from lmp_real.automaton import (
    accepts,
    build_reachability_graph,
    determinize,
    is_acyclic,
    max_accepted_length,
    productive_states,
)
from lmp_real.denominator import (
    CERT_FINITE_SUM,
    CERT_INTERVAL,
    CERT_SPARSE_SOLVE,
    bounded_length_masses,
    geometric_denominator,
    lmp_interval,
    power_law_denominator,
    uniform_label_mass,
)
from lmp_real.priors import alpha_from_median_length, lambda_from_median_length, trace_mass


def _place(net, name):
    place = PetriNet.Place(name)
    net.places.add(place)
    return place


def _transition(net, name, label):
    transition = PetriNet.Transition(name, label)
    net.transitions.add(transition)
    return transition


def _dfa_for(net, im, fm):
    graph = build_reachability_graph(net, im, fm)
    assert graph.status == "ok"
    dfa = determinize(graph)
    assert dfa.status == "ok"
    return graph, dfa


def flower_model(activities):
    net = PetriNet("flower")
    p = _place(net, "p")
    for activity in activities:
        t = _transition(net, f"t_{activity}", activity)
        petri_utils.add_arc_from_to(p, t, net)
        petri_utils.add_arc_from_to(t, p, net)
    im, fm = Marking(), Marking()
    im[p] = 1
    fm[p] = 1
    return net, im, fm


def sequential_model(labels, silent_prefix=False):
    net = PetriNet("sequential")
    places = [_place(net, f"p{i}") for i in range(len(labels) + 1)]
    if silent_prefix:
        extra = _place(net, "p_pre")
        tau = _transition(net, "tau", None)
        petri_utils.add_arc_from_to(extra, tau, net)
        petri_utils.add_arc_from_to(tau, places[0], net)
        start_place = extra
    else:
        start_place = places[0]
    for i, label in enumerate(labels):
        t = _transition(net, f"t{i}", label)
        petri_utils.add_arc_from_to(places[i], t, net)
        petri_utils.add_arc_from_to(t, places[i + 1], net)
    im, fm = Marking(), Marking()
    im[start_place] = 1
    fm[places[-1]] = 1
    return net, im, fm


def branching_finite_model():
    """Language {('a', 'b'), ('a', 'c')}."""
    net = PetriNet("branch")
    p0, p1, p2 = _place(net, "p0"), _place(net, "p1"), _place(net, "p2")
    ta = _transition(net, "ta", "a")
    petri_utils.add_arc_from_to(p0, ta, net)
    petri_utils.add_arc_from_to(ta, p1, net)
    tb = _transition(net, "tb", "b")
    petri_utils.add_arc_from_to(p1, tb, net)
    petri_utils.add_arc_from_to(tb, p2, net)
    tc = _transition(net, "tc", "c")
    petri_utils.add_arc_from_to(p1, tc, net)
    petri_utils.add_arc_from_to(tc, p2, net)
    im, fm = Marking(), Marking()
    im[p0] = 1
    fm[p2] = 1
    return net, im, fm


def xor_skip_model():
    """Language {('b',), ('a', 'b')}: p0 optionally emits 'a' (or a silent
    skip) before mandatory 'b'."""
    net = PetriNet("xor_skip")
    p0, p1, p2 = _place(net, "p0"), _place(net, "p1"), _place(net, "p2")
    ta = _transition(net, "ta", "a")
    petri_utils.add_arc_from_to(p0, ta, net)
    petri_utils.add_arc_from_to(ta, p1, net)
    tau = _transition(net, "tau", None)
    petri_utils.add_arc_from_to(p0, tau, net)
    petri_utils.add_arc_from_to(tau, p1, net)
    tb = _transition(net, "tb", "b")
    petri_utils.add_arc_from_to(p1, tb, net)
    petri_utils.add_arc_from_to(tb, p2, net)
    im, fm = Marking(), Marking()
    im[p0] = 1
    fm[p2] = 1
    return net, im, fm


def looping_model():
    """Language {a^n : n >= 0}: self-loop on 'a' with a silent exit."""
    net = PetriNet("loop")
    p0, p1 = _place(net, "p0"), _place(net, "p1")
    ta = _transition(net, "ta", "a")
    petri_utils.add_arc_from_to(p0, ta, net)
    petri_utils.add_arc_from_to(ta, p0, net)
    tau = _transition(net, "tau", None)
    petri_utils.add_arc_from_to(p0, tau, net)
    petri_utils.add_arc_from_to(tau, p1, net)
    im, fm = Marking(), Marking()
    im[p0] = 1
    fm[p1] = 1
    return net, im, fm


def test_flower_denominator_equals_one_for_both_normalized_priors():
    activities = ["a", "b", "c"]
    net, im, fm = flower_model(activities)
    _, dfa = _dfa_for(net, im, fm)
    alphabet_size = len(activities)

    geo = geometric_denominator(dfa, alphabet_size, lam=0.85)
    assert geo.certification == CERT_SPARSE_SOLVE
    assert math.isclose(geo.exact, 1.0, abs_tol=1e-9)

    pwl = power_law_denominator(dfa, alphabet_size, alpha=2.5)
    assert pwl.certification == CERT_INTERVAL
    assert pwl.lower <= 1.0 <= pwl.upper + 1e-9
    assert pwl.upper - pwl.lower < 1e-3


def test_controlled_finite_model_denominator_equals_explicit_language_sum():
    net, im, fm = branching_finite_model()
    _, dfa = _dfa_for(net, im, fm)
    alphabet_size = 5
    lam = 0.8

    geo = geometric_denominator(dfa, alphabet_size, lam=lam)
    assert geo.certification == CERT_FINITE_SUM
    expected = trace_mass(("a", "b"), alphabet_size, "geometric", lam) + trace_mass(
        ("a", "c"), alphabet_size, "geometric", lam
    )
    assert math.isclose(geo.exact, expected, rel_tol=1e-9)

    alpha = 2.0
    pwl = power_law_denominator(dfa, alphabet_size, alpha=alpha)
    assert pwl.certification == CERT_FINITE_SUM
    expected_pwl = trace_mass(("a", "b"), alphabet_size, "power_law", alpha) + trace_mass(
        ("a", "c"), alphabet_size, "power_law", alpha
    )
    assert math.isclose(pwl.exact, expected_pwl, rel_tol=1e-9)


def test_epsilon_nfa_membership_agrees_with_known_accepted_and_rejected_traces():
    net, im, fm = xor_skip_model()
    _, dfa = _dfa_for(net, im, fm)

    assert accepts(dfa, ("b",))
    assert accepts(dfa, ("a", "b"))
    assert not accepts(dfa, ("a",))
    assert not accepts(dfa, ())
    assert not accepts(dfa, ("b", "b"))
    assert not accepts(dfa, ("c",))


def test_bounded_denominator_masses_are_monotone_in_k():
    net, im, fm = looping_model()
    _, dfa = _dfa_for(net, im, fm)
    label_mass = uniform_label_mass(dfa, alphabet_size=4)
    lam = 0.9

    masses = bounded_length_masses(dfa, label_mass, max_k=40)
    running = 0.0
    d_k_series = []
    for n, mass in enumerate(masses):
        running += (1.0 - lam) * lam**n * mass
        d_k_series.append(running)
    assert all(b >= a - 1e-15 for a, b in zip(d_k_series, d_k_series[1:]))


def test_certified_intervals_nest_and_contain_the_exact_geometric_result():
    net, im, fm = looping_model()
    _, dfa = _dfa_for(net, im, fm)
    alphabet_size = 4
    lam = 0.9
    label_mass = uniform_label_mass(dfa, alphabet_size)

    exact = geometric_denominator(dfa, alphabet_size, lam=lam).exact

    masses = bounded_length_masses(dfa, label_mass, max_k=60)
    intervals = []
    running = 0.0
    for k in range(len(masses)):
        running += (1.0 - lam) * lam**k * masses[k]
        tail = lam ** (k + 1)
        intervals.append((running, running + tail))

    for lower, upper in intervals:
        assert lower - 1e-12 <= exact <= upper + 1e-12

    for (lower_a, upper_a), (lower_b, upper_b) in zip(intervals, intervals[1:]):
        assert lower_b >= lower_a - 1e-15
        assert upper_b <= upper_a + 1e-15


def test_language_equivalent_controlled_models_have_identical_denominators():
    net_a, im_a, fm_a = sequential_model(["a", "b"], silent_prefix=False)
    net_b, im_b, fm_b = sequential_model(["a", "b"], silent_prefix=True)
    graph_a, dfa_a = _dfa_for(net_a, im_a, fm_a)
    graph_b, dfa_b = _dfa_for(net_b, im_b, fm_b)

    assert graph_a.state_count != graph_b.state_count

    for prior_fn, param in ((geometric_denominator, 0.75), (power_law_denominator, 2.0)):
        result_a = prior_fn(dfa_a, alphabet_size=6, **({"lam": param} if prior_fn is geometric_denominator else {"alpha": param}))
        result_b = prior_fn(dfa_b, alphabet_size=6, **({"lam": param} if prior_fn is geometric_denominator else {"alpha": param}))
        assert math.isclose(result_a.exact, result_b.exact, rel_tol=1e-9)


def test_numerator_bounded_by_denominator_within_tolerance():
    net, im, fm = branching_finite_model()
    _, dfa = _dfa_for(net, im, fm)
    alphabet_size = 5
    lam = 0.8
    variants = [("a", "b"), ("a", "c"), ("a", "d")]

    accepted = [trace for trace in variants if accepts(dfa, trace)]
    assert accepted == [("a", "b"), ("a", "c")]
    numerator = math.fsum(trace_mass(trace, alphabet_size, "geometric", lam) for trace in accepted)

    denominator = geometric_denominator(dfa, alphabet_size, lam=lam)
    assert 0.0 <= numerator <= denominator.exact + 1e-12
    assert denominator.exact <= 1.0 + 1e-12

    lower, upper = lmp_interval(numerator, denominator)
    assert lower <= upper
    assert math.isclose(lower, upper, rel_tol=1e-9)


def test_ranking_group_has_identical_alphabet_and_prior_hashes():
    median_length = 12.0
    lam_a = lambda_from_median_length(median_length)
    lam_b = lambda_from_median_length(median_length)
    alpha_a = alpha_from_median_length(median_length)
    alpha_b = alpha_from_median_length(median_length)
    assert lam_a == lam_b
    assert alpha_a == alpha_b


def test_power_law_deterministic_interval_contains_true_mass_for_cyclic_model():
    net, im, fm = looping_model()
    _, dfa = _dfa_for(net, im, fm)
    result = power_law_denominator(dfa, alphabet_size=4, alpha=3.0)
    assert result.certification == CERT_INTERVAL
    assert result.lower <= result.upper
    assert result.upper - result.lower <= 1e-3


def test_reachability_reports_state_limit_instead_of_a_silently_partial_automaton():
    net, im, fm = branching_finite_model()
    graph = build_reachability_graph(net, im, fm, state_limit=1)
    assert graph.status == "reachability_state_limit"

    dfa = determinize(graph)
    assert dfa.status == "reachability_state_limit"
    with pytest.raises(ValueError):
        accepts(dfa, ("a", "b"))
