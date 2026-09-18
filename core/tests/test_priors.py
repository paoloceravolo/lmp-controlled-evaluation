import math

from lmp_real.priors import (
    alpha_from_median_length,
    lambda_from_median_length,
    length_tail_mass,
    power_law_length_cdf,
    trace_mass,
)


def test_geometric_calibration_places_half_mass_at_or_below_median():
    median_length = 8
    parameter = lambda_from_median_length(median_length)
    cdf = 1.0 - parameter ** (median_length + 1)
    assert math.isclose(cdf, 0.5, rel_tol=1e-12)


def test_power_law_calibration_places_half_mass_at_or_below_median():
    parameter = alpha_from_median_length(8)
    assert math.isclose(power_law_length_cdf(8, parameter), 0.5, rel_tol=1e-8)


def test_tail_mass_matches_geometric_identity():
    assert math.isclose(length_tail_mass(3, "geometric", 0.7), 0.7**4)


def test_trace_mass_is_uniform_within_a_length():
    assert trace_mass(("a", "a"), 3, "geometric", 0.8) == trace_mass(("b", "c"), 3, "geometric", 0.8)
